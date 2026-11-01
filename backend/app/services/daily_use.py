from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import Asset
from app.models import Account
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import DataSourceConnection
from app.models import ExportArtifact
from app.models import InvestmentConstitution
from app.models import InvestmentThesis
from app.models import LocalUserConfig
from app.models import OrderIntent
from app.models import OrderDraft
from app.models import OperationalEvent
from app.models import PlaybookUpdateProposal
from app.models import Position
from app.models import PostTradeReview
from app.models import Reminder
from app.models import RiskCheck
from app.models import RiskBudget
from app.models import ScheduledJob
from app.models import WatchlistItem
from app.models import WorkflowReviewTask
from app.schemas.core import contains_secret_config_key
from app.services.data_sources import DataSourceService
from app.services.data_catalog import DataCatalogService
from app.services.demo_seed import DemoSeedService
from app.services.demo_seed import DEMO_USER_ID
from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.core.config import get_settings
from app.core.config import Settings


DEFAULT_EXPORT_SECTIONS = [
    "watchlist",
    "reminders",
    "local_config",
    "scheduled_jobs",
    "data_sources",
    "theses",
    "order_drafts",
    "reviews",
    "playbook_proposals",
]


class DailyUseError(ValueError):
    pass


class DailyUseService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def _workspace_position_statement(self, *, user_id: str):
        """Keep daily-use decisions inside the active data workspace.

        Simulation uses the single official demo account. This prevents
        historical integration-test accounts from being aggregated into a
        user's daily portfolio while leaving CSV/read-only multi-account
        workspaces unchanged.
        """
        statement = select(Position)
        config = self.db.scalar(
            select(LocalUserConfig).where(
                LocalUserConfig.user_id == user_id,
                LocalUserConfig.config_key == "local_start",
            ).limit(1)
        )
        state = config.value_json if config is not None else {}
        if state.get("data_mode") == "simulation":
            demo_account_id = self.db.scalar(
                select(Account.id).where(Account.name == "demo_primary_paper_account").limit(1)
            )
            if demo_account_id:
                statement = statement.where(Position.account_id == demo_account_id)
        return statement

    def onboarding_status(self, *, user_id: str = "default-user") -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        config = self.db.scalar(
            select(LocalUserConfig)
            .where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == "founder_onboarding")
            .limit(1)
        )
        state = config.value_json if config is not None else {}
        discipline = self._investment_discipline_status(user_id=user_id)
        required = [
            "workspace_goal",
            "risk_boundary_acknowledged",
            "read_only_data_plan",
            "investment_discipline",
            "daily_review_time",
            "first_daily_open",
        ]
        completed = [
            key
            for key in required
            if (
                (key == "investment_discipline" and discipline["status"] == "ready")
                or (bool(state.get(key)) and (key != "risk_boundary_acknowledged" or state.get(key) is True))
            )
        ]
        missing = [key for key in required if key not in completed]
        step_details = onboarding_step_details(completed)
        next_step = next((step for step in step_details if step["status"] != "ready"), None)
        return {
            "user_id": user_id,
            "status": "ready" if not missing else "incomplete",
            "generated_at": now,
            "required_steps": required,
            "completed_steps": completed,
            "missing_steps": missing,
            "completion_pct": round((len(completed) / len(required)) * 100),
            "step_details": step_details,
            "next_step": next_step,
            "state": {**state, "investment_discipline": discipline},
            "next_actions": onboarding_next_actions(missing),
            "execution_available": False,
        }

    def local_start_status(self, *, user_id: str = "default-user") -> dict[str, Any]:
        onboarding = self.onboarding_status(user_id=user_id)
        config = self.db.scalar(
            select(LocalUserConfig).where(
                LocalUserConfig.user_id == user_id,
                LocalUserConfig.config_key == "local_start",
            ).limit(1)
        )
        state = config.value_json if config is not None else {}
        demo = DemoSeedService(self.db).build_status()
        initialized = bool(state.get("initialized"))
        setup_tasks = self._local_start_setup_tasks(user_id=user_id, state=state, demo_seeded=demo.seeded)
        ready = onboarding["status"] == "ready" and initialized and not setup_tasks
        beta_gate = self._beta_entry_gate(user_id=user_id)
        return {
            "user_id": user_id,
            "status": "ready" if ready else ("needs_data" if initialized else "needs_setup"),
            "initialized": initialized,
            "data_mode": state.get("data_mode"),
            "demo_seeded": demo.seeded,
            "mode_changed_at": state.get("mode_changed_at"),
            "mode_history": list(state.get("mode_history") or []),
            "simulation_data_user_id": state.get("simulation_data_user_id") or DEMO_USER_ID,
            "simulation_excluded_from_real_evidence": state.get("simulation_excluded_from_real_evidence", True),
            "beta_entry_gate": beta_gate,
            "onboarding": onboarding,
            "setup_tasks": setup_tasks,
            "next_route": setup_tasks[0]["route"] if setup_tasks else state.get("next_route") or "/?module=overview",
            "execution_available": False,
        }

    def initialize_local_start(self, *, user_id: str = "default-user", payload: dict[str, Any]) -> dict[str, Any]:
        if contains_secret_config_key(payload):
            raise DailyUseError("local start must use secret references, never inline credentials")
        data_mode = str(payload.get("data_mode") or "simulation")
        if data_mode not in {"simulation", "csv", "read_only"}:
            raise DailyUseError("data_mode must be simulation, csv, or read_only")
        if payload.get("risk_boundary_acknowledged") is not True:
            raise DailyUseError("risk boundary acknowledgement is required")
        beta_gate = self._beta_entry_gate(user_id=user_id)
        if beta_gate["required"] and beta_gate["status"] != "ready":
            raise DailyUseError("current private Beta terms, privacy policy, risk disclosure, and ICP eligibility must be accepted before first-run setup")

        existing_config = self.db.scalar(select(LocalUserConfig).where(
            LocalUserConfig.user_id == user_id,
            LocalUserConfig.config_key == "local_start",
        ).limit(1))
        existing_state = dict(existing_config.value_json or {}) if existing_config is not None else {}
        previous_mode = existing_state.get("data_mode")
        mode_changed = bool(existing_state.get("initialized") and previous_mode and previous_mode != data_mode)
        if mode_changed and payload.get("mode_change_confirmation") != "SWITCH_DATA_MODE":
            raise DailyUseError("changing data mode requires SWITCH_DATA_MODE confirmation")

        if data_mode == "simulation":
            DemoSeedService(self.db).seed()
        from app.services.product_completion import ProductCompletionService

        ProductCompletionService(self.db).initialize_daily_loop(actor=AuthenticatedUser(
            user_id=user_id,
            role="owner",
            permissions=ROLE_PERMISSIONS["owner"],
            auth_required=False,
            token_configured=False,
        ))
        discipline = self.ensure_default_investment_discipline(user_id=user_id)
        next_route = {
            "simulation": "/?module=overview",
            "csv": "/?module=settings&tab=data&setup=csv",
            "read_only": "/?module=settings&tab=data&setup=read_only",
        }[data_mode]
        self.update_onboarding(
            user_id=user_id,
            state={
                "workspace_goal": str(payload.get("workspace_goal") or "daily_investment_review"),
                "risk_boundary_acknowledged": payload.get("risk_boundary_acknowledged") is True,
                "read_only_data_plan": data_mode,
                "investment_discipline": discipline["status"] == "ready",
                "daily_review_time": str(payload.get("daily_review_time") or "20:30"),
                "first_daily_open": True,
            },
        )
        changed_at = datetime.now(timezone.utc)
        mode_history = list(existing_state.get("mode_history") or [])
        if not mode_history or mode_changed:
            mode_history.append({
                "from": previous_mode,
                "to": data_mode,
                "changed_at": changed_at.isoformat(),
                "confirmed": not mode_changed or payload.get("mode_change_confirmation") == "SWITCH_DATA_MODE",
                "demo_data_scope": DEMO_USER_ID if data_mode == "simulation" else None,
            })
        self.upsert_local_config(
            config_key="local_start",
            user_id=user_id,
            value_json={
                **existing_state,
                "initialized": True,
                "data_mode": data_mode,
                "next_route": next_route,
                "initialized_at": existing_state.get("initialized_at") or changed_at.isoformat(),
                "mode_changed_at": changed_at.isoformat() if mode_changed else existing_state.get("mode_changed_at"),
                "mode_history": mode_history[-20:],
                "simulation_data_user_id": DEMO_USER_ID,
                "simulation_excluded_from_real_evidence": True,
                "execution_available": False,
            },
            description="Local self-use startup state.",
        )
        daily_review = self.db.scalar(select(Reminder).where(Reminder.user_id == user_id, Reminder.reminder_type == "daily_review").limit(1))
        if daily_review is None:
            self.create_reminder(
                user_id=user_id,
                title="完成今日投资检查",
                reminder_type="daily_review",
                due_at=datetime.now(timezone.utc),
                recurrence_json={"frequency": "weekdays"},
                priority="high",
                payload_json={"route": "/?module=overview&focus=today_queue"},
            )
        else:
            daily_review.status = "pending"
            daily_review.due_at = datetime.now(timezone.utc)
            daily_review.completed_at = None
            self.db.commit()
        self._audit(
            "daily_use.data_mode_changed" if mode_changed else "daily_use.local_start_initialized",
            "LocalUserConfig",
            "local_start",
            {"user_id": user_id, "previous_mode": previous_mode, "data_mode": data_mode, "confirmed": True, "simulation_excluded_from_real_evidence": True},
        )
        return self.local_start_status(user_id=user_id)

    def _beta_entry_gate(self, *, user_id: str) -> dict[str, Any]:
        required = bool(self.settings.managed_auth_required and self.settings.managed_auth_invitation_required)
        if not required:
            return {"required": False, "status": "not_required", "blockers": []}
        from app.services.beta_analytics import BetaAnalyticsService
        from app.services.privacy_center import PrivacyCenterService

        profile = self.db.scalar(select(LocalUserConfig).where(
            LocalUserConfig.user_id == user_id,
            LocalUserConfig.config_key == BetaAnalyticsService.PROFILE_KEY,
        ).limit(1))
        value = dict(profile.value_json or {}) if profile else {}
        blockers = []
        if not value.get("qualified"):
            blockers.append("private_beta_icp_not_qualified")
        if not (value.get("private_beta_consent") and value.get("risk_disclosure_acknowledged")):
            blockers.append("private_beta_consent_or_risk_ack_missing")
        if value.get("beta_terms_version") != BetaAnalyticsService.TERMS_VERSION:
            blockers.append("private_beta_terms_version_stale")
        if value.get("privacy_policy_version") != PrivacyCenterService.POLICY_VERSION:
            blockers.append("privacy_policy_version_stale")
        return {
            "required": True,
            "status": "ready" if not blockers else "blocked",
            "blockers": blockers,
            "beta_terms_version": BetaAnalyticsService.TERMS_VERSION,
            "privacy_policy_version": PrivacyCenterService.POLICY_VERSION,
        }

    def ensure_default_investment_discipline(self, *, user_id: str = "default-user") -> dict[str, Any]:
        constitution = self.db.scalar(
            select(InvestmentConstitution)
            .where(InvestmentConstitution.user_id == user_id, InvestmentConstitution.is_active.is_(True))
            .order_by(InvestmentConstitution.updated_at.desc(), InvestmentConstitution.id.desc())
            .limit(1)
        )
        if constitution is None:
            constitution = InvestmentConstitution(
                user_id=user_id,
                version="local-v1",
                name="Local Default Discipline",
                investment_style="disciplined_manual_review",
                allowed_markets=["US", "Crypto"],
                forbidden_assets=[],
                forbidden_actions=["LIVE_EXECUTION", "AUTO_APPROVAL", "WITHDRAWAL", "WALLET_SIGNING", "DEX_SWAP"],
                max_single_position_pct=0.25,
                max_asset_class_pct=0.8,
                max_crypto_pct=0.25,
                max_single_exchange_pct=0.5,
                max_daily_loss_pct=0.02,
                max_monthly_drawdown_pct=0.08,
                leverage_allowed=False,
                derivatives_allowed=False,
                auto_execution_allowed=False,
                human_approval_required=True,
                cooldown_rules_json={"min_minutes_between_actions": 30, "local_self_use": True},
                is_active=True,
            )
            self.db.add(constitution)
            self.db.flush()
            self._audit(
                "daily_use.default_investment_discipline_created",
                "InvestmentConstitution",
                constitution.id,
                {"user_id": user_id, "execution_available": False},
            )

        # Keep explicit budgets for every asset type the product can create
        # from the default holdings. In particular, ETFs must not depend on
        # whichever thesis happens to be listed first in the UI.
        for asset_class in ["stock", "equity", "etf", "crypto"]:
            existing_budget = self.db.scalar(
                select(RiskBudget)
                .where(
                    RiskBudget.user_id == user_id,
                    RiskBudget.constitution_id == constitution.id,
                    RiskBudget.asset_class == asset_class,
                    RiskBudget.account_id.is_(None),
                )
                .limit(1)
            )
            if existing_budget is not None:
                continue
            self.db.add(RiskBudget(
                user_id=user_id,
                constitution_id=constitution.id,
                account_id=None,
                asset_class=asset_class,
                max_allocation_pct=0.25 if asset_class == "crypto" else 0.8,
                max_loss_pct=0.08,
                max_order_notional=10_000,
                max_leverage=1,
                rebalance_threshold_pct=0.05,
            ))
        self.db.commit()
        return self._investment_discipline_status(user_id=user_id)

    def scheduler_status(self, *, user_id: str = "default-user") -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        settings = get_settings()
        jobs = list(self.db.scalars(
            select(ScheduledJob)
            .where(ScheduledJob.job_type.like("product_%"))
            .order_by(ScheduledJob.created_at.asc(), ScheduledJob.id.asc())
        ).all())
        health = scheduler_health_status(jobs, now=now)
        job_payloads = [scheduled_job_payload(job, now=now) for job in jobs]
        next_run_values = [
            datetime.fromisoformat(str(job["next_run_at"]))
            for job in job_payloads
            if job.get("next_run_at")
        ]
        next_run_at = min(next_run_values, default=None)
        return {
            "user_id": user_id,
            "status": "running" if any(job.status == "active" for job in jobs) else "not_configured",
            "active_jobs": sum(1 for job in jobs if job.status == "active"),
            "last_run_at": max((job.last_run_at for job in jobs if job.last_run_at is not None), default=None),
            "next_run_at": next_run_at.isoformat() if next_run_at else None,
            "health_status": health["status"],
            "health_label": health["label"],
            "health_detail": health["detail"],
            "verified_jobs": health["verified_jobs"],
            "stale_after_hours": health["stale_after_hours"],
            "runtime_loop_enabled": settings.runtime_scheduler_enabled,
            "runtime_poll_seconds": settings.runtime_scheduler_poll_seconds,
            "continuity_label": scheduler_continuity_label(
                runtime_enabled=settings.runtime_scheduler_enabled,
                status=health["status"],
                active_jobs=sum(1 for job in jobs if job.status == "active"),
            ),
            "continuity_detail": scheduler_continuity_detail(
                runtime_enabled=settings.runtime_scheduler_enabled,
                poll_seconds=settings.runtime_scheduler_poll_seconds,
                health_detail=health["detail"],
            ),
            "jobs": job_payloads,
            "execution_available": False,
        }

    def run_scheduler_tick(self, *, user_id: str = "default-user", action: str | None = None) -> dict[str, Any]:
        from app.services.product_completion import ProductCompletionService
        from app.services.workflow_review import WorkflowDeepReviewService

        actor = AuthenticatedUser(
            user_id=user_id,
            role="owner",
            permissions=ROLE_PERMISSIONS["owner"],
            auth_required=False,
            token_configured=False,
        )
        ProductCompletionService(self.db).initialize_daily_loop(actor=actor)
        packet = ProductCompletionService(self.db).scheduler_tick(actor=actor, action=action)
        automatic_reviews = WorkflowDeepReviewService(self.db).sync_automatic_tasks(user_id=user_id)
        return {
            **packet,
            "automatic_reviews": automatic_reviews,
            "scheduler": self.scheduler_status(user_id=user_id),
            "queue": self.action_queue(user_id=user_id, limit=10),
            "execution_available": False,
        }

    def workspace_status(self, *, user_id: str = "default-user") -> dict[str, Any]:
        local_start = self.local_start_status(user_id=user_id)
        scheduler = self.scheduler_status(user_id=user_id)
        freshness = DataSourceService(self.db).freshness_overview()
        queue = self.action_queue(user_id=user_id, limit=5)
        data_mode = local_start.get("data_mode")
        setup_tasks = local_start.get("setup_tasks") or []
        data_ready = False if setup_tasks else (bool(local_start.get("demo_seeded")) if data_mode == "simulation" else freshness["overall_status"] != "block")
        checks = [
            {
                "key": "workspace",
                "label": "工作台",
                "status": "ready" if local_start["initialized"] else "action_required",
                "detail": "首次设置已完成" if local_start["initialized"] else "完成首次启动设置",
                "route": "/?module=overview",
            },
            {
                "key": "data",
                "label": "数据",
                "status": "ready" if data_ready else "action_required",
                "detail": local_data_detail(data_mode=data_mode, freshness=freshness),
                "route": "/?module=settings&tab=data",
            },
            {
                "key": "investment_discipline",
                "label": "投资纪律",
                "status": "ready" if local_start["onboarding"]["state"].get("investment_discipline", {}).get("status") == "ready" else "action_required",
                "detail": (
                    "投资纪律和基础风险预算已就绪"
                    if local_start["onboarding"]["state"].get("investment_discipline", {}).get("status") == "ready"
                    else "先建立投资纪律和风险预算，计划才能通过风险闸门"
                ),
                "route": "/?module=investment_logic&tab=constitution",
            },
            {
                "key": "scheduler",
                "label": "自动提醒",
                "status": "ready" if scheduler["status"] == "running" else "action_required",
                "detail": (
                    f"{scheduler['active_jobs']} 个任务运行中"
                    if scheduler["status"] == "running"
                    else "需要初始化每日调度"
                ),
                "route": "/?module=settings&tab=preferences",
            },
        ]
        ready_count = sum(1 for check in checks if check["status"] == "ready")
        return {
            "user_id": user_id,
            "status": "ready" if ready_count == len(checks) else "action_required",
            "ready_count": ready_count,
            "total_count": len(checks),
            "data_mode": data_mode,
            "queue_count": queue["total_actions"],
            "primary_action": queue["actions"][0] if queue["actions"] else None,
            "checks": checks,
            "execution_available": False,
        }

    def self_use_readiness(self, *, user_id: str = "default-user") -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        local_start = self.local_start_status(user_id=user_id)
        onboarding = local_start["onboarding"]
        workspace = self.workspace_status(user_id=user_id)
        scheduler = self.scheduler_status(user_id=user_id)
        queue = self.action_queue(user_id=user_id, limit=5)
        daily_close = self.db.scalar(
            select(LocalUserConfig)
            .where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == "daily_close_latest")
            .limit(1)
        )
        thesis_count = self._count(
            select(func.count())
            .select_from(InvestmentThesis)
            .where(InvestmentThesis.user_id == user_id, InvestmentThesis.status.in_(["active", "monitoring"]))
        )
        position_count = self._count(select(func.count()).select_from(Position))
        risk_action_count = self.action_queue(user_id=user_id, limit=200, source="portfolio_risk")["total_actions"]
        data_mode = local_start.get("data_mode")
        setup_tasks = list(local_start.get("setup_tasks") or [])
        checks = [
            {
                "key": "onboarding",
                "label": "首次启动",
                "status": "ready" if local_start["initialized"] and onboarding["status"] == "ready" else "action_required",
                "detail": "首次启动 6 步已完成" if onboarding["status"] == "ready" else f"还缺：{onboarding['next_step']['label'] if onboarding.get('next_step') else '首次启动向导'}",
                "route": "/?module=settings",
                "weight": 18,
            },
            {
                "key": "data",
                "label": "数据模式",
                "status": "ready" if workspace["checks"][1]["status"] == "ready" else "action_required",
                "detail": workspace["checks"][1]["detail"],
                "route": "/?module=settings&tab=data",
                "weight": 16,
            },
            {
                "key": "investment_discipline",
                "label": "投资纪律",
                "status": "ready" if onboarding["state"].get("investment_discipline", {}).get("status") == "ready" else "action_required",
                "detail": onboarding["state"].get("investment_discipline", {}).get("detail", "建立投资纪律和风险预算后，计划才能进入五道闸门。"),
                "route": "/?module=investment_logic&tab=constitution",
                "weight": 8,
            },
            {
                "key": "scheduler",
                "label": "持续提醒",
                "status": "ready" if scheduler["health_status"] == "verified" else "action_required",
                "detail": scheduler["health_detail"],
                "route": "/?module=settings&tab=preferences",
                "weight": 12,
            },
            {
                "key": "today_queue",
                "label": "Today Queue",
                "status": "ready" if queue["total_actions"] >= 0 else "action_required",
                "detail": f"{queue['total_actions']} 项待处理；可完成、延期、忽略或分派" if queue["total_actions"] else "队列已清空，可进入收盘复盘",
                "route": "/?module=overview&focus=today_queue",
                "weight": 14,
            },
            {
                "key": "investment_workflow",
                "label": "投资工作流",
                "status": "ready" if thesis_count > 0 or position_count == 0 else "action_required",
                "detail": f"已有 {thesis_count} 条有效 Thesis" if thesis_count > 0 else "至少给一个主要持仓补 Thesis",
                "route": "/?module=holdings",
                "weight": 14,
            },
            {
                "key": "risk_review",
                "label": "风险处理",
                "status": "ready" if risk_action_count == 0 else "action_required",
                "detail": "没有待处理组合风险项" if risk_action_count == 0 else f"{risk_action_count} 个组合风险项需要人工复核",
                "route": "/?module=risk",
                "weight": 10,
            },
            {
                "key": "daily_close",
                "label": "收盘复盘",
                "status": "ready" if daily_close is not None and not is_older_than(daily_close.updated_at, now=now, delta=timedelta(days=2)) else "action_required",
                "detail": "最近 2 天已保存收盘复盘" if daily_close is not None else "保存一次今天结论和明天第一步",
                "route": "/?module=trade_journal&tab=daily_close",
                "weight": 8,
            },
            {
                "key": "safety_boundary",
                "label": "安全边界",
                "status": "ready",
                "detail": "当前仍禁止自动实盘、提现、wallet signing、DEX swap、自动审批和绕过 gates",
                "route": "/?module=settings&tab=security",
                "weight": 6,
            },
        ]
        ready_weight = sum(int(check["weight"]) for check in checks if check["status"] == "ready")
        progress_pct = min(92, ready_weight)
        if data_mode == "read_only" and setup_tasks:
            progress_pct = min(progress_pct, 82)
        if data_mode in {"simulation", "csv"} and local_start["initialized"]:
            progress_pct = max(progress_pct, 70)
        next_check = next((check for check in checks if check["status"] != "ready"), None)
        external_blockers = [
            "真实 Binance read-only snapshot 与 quality report 仍需私有环境运行",
            "真实 LLM 长期 eval、生产 Auth/RBAC、云 Secret Manager、监控、Broker Sandbox 和 Controlled Pilot 仍未实证",
        ]
        return {
            "user_id": user_id,
            "generated_at": now,
            "status": "locally_usable" if progress_pct >= 85 else "needs_setup" if progress_pct < 55 else "usable_with_gaps",
            "progress_pct": progress_pct,
            "remaining_pct": max(0, 100 - progress_pct),
            "mode": "local_self_use",
            "data_mode": data_mode,
            "summary": (
                "本地自用主链路已基本可操作"
                if progress_pct >= 85
                else "本地自用主链路仍有关键设置缺口"
            ),
            "next_action": {
                "label": next_check["label"] if next_check else "保存收盘复盘",
                "detail": next_check["detail"] if next_check else "当前主链路可用，建议保存今天结论和明天第一步。",
                "route": next_check["route"] if next_check else "/?module=trade_journal&tab=daily_close",
            },
            "checks": checks,
            "external_blockers": external_blockers,
            "execution_available": False,
        }

    def investment_workflow_status(self, *, user_id: str = "default-user") -> dict[str, Any]:
        """Read-only status for the local holdings -> thesis -> plan -> risk path."""
        now = datetime.now(timezone.utc)
        positions = list(self.db.scalars(self._workspace_position_statement(user_id=user_id).order_by(Position.updated_at.desc(), Position.id.desc())).all())
        theses = list(self.db.scalars(
            select(InvestmentThesis)
            .where(InvestmentThesis.user_id == user_id)
            .order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc())
        ).all())
        intents = list(self.db.scalars(
            select(OrderIntent)
            .where(OrderIntent.investment_thesis_id.is_not(None))
            .order_by(OrderIntent.created_at.desc(), OrderIntent.id.desc())
        ).all())
        intent_ids = [intent.id for intent in intents]
        risk_checks = list(self.db.scalars(
            select(RiskCheck)
            .where(RiskCheck.order_intent_id.in_(intent_ids))
            .order_by(RiskCheck.created_at.desc(), RiskCheck.id.desc())
        ).all()) if intent_ids else []
        drafts = list(self.db.scalars(
            select(OrderDraft)
            .where(OrderDraft.order_intent_id.in_(intent_ids))
            .order_by(OrderDraft.created_at.desc(), OrderDraft.id.desc())
        ).all()) if intent_ids else []

        position_asset_ids = {position.asset_id for position in positions}
        active_thesis_asset_ids = {thesis.asset_id for thesis in theses if thesis.status in {"active", "monitoring"}}
        missing_asset_ids = sorted(asset_id for asset_id in position_asset_ids if asset_id not in active_thesis_asset_ids)
        latest_thesis = next((thesis for thesis in theses if thesis.status in {"active", "monitoring"}), theses[0] if theses else None)
        latest_intent = intents[0] if intents else None
        latest_risk = risk_checks[0] if risk_checks else None
        latest_draft = drafts[0] if drafts else None

        steps = [
            {
                "key": "holdings",
                "label": "持仓",
                "status": "ready" if positions else "action_required",
                "detail": f"已读取 {len(positions)} 个持仓" if positions else "先导入持仓或初始化模拟数据",
                "route": "/?module=settings&tab=data" if not positions else "/?module=holdings",
                "action_label": "导入持仓" if not positions else "打开持仓",
            },
            {
                "key": "thesis",
                "label": "Thesis",
                "status": "ready" if active_thesis_asset_ids and not missing_asset_ids else "action_required",
                "detail": (
                    f"已有 {len(active_thesis_asset_ids)} 个资产有 Thesis"
                    if active_thesis_asset_ids and not missing_asset_ids
                    else f"{len(missing_asset_ids)} 个持仓缺 Thesis"
                    if positions
                    else "导入持仓后再补投资理由"
                ),
                "route": (
                    f"/?module=holdings&asset={missing_asset_ids[0]}&create_thesis=1"
                    if missing_asset_ids
                    else f"/?module=investment_logic&focus_thesis={latest_thesis.id}"
                    if latest_thesis
                    else "/?module=holdings"
                ),
                "action_label": "补 Thesis" if missing_asset_ids or not latest_thesis else "打开 Thesis",
            },
            {
                "key": "plan",
                "label": "计划",
                "status": "ready" if latest_intent else "action_required",
                "detail": "已有 Thesis 生成的人工计划" if latest_intent else "从有效 Thesis 生成人工计划",
                "route": (
                    f"/?module=order_drafts&intent={latest_intent.id}"
                    if latest_intent
                    else f"/?module=investment_logic&focus_thesis={latest_thesis.id}&plan=1"
                    if latest_thesis
                    else "/?module=investment_logic"
                ),
                "action_label": "打开计划" if latest_intent else "生成计划",
            },
            {
                "key": "risk_review",
                "label": "风险审查",
                "status": "ready" if latest_risk else "action_required",
                "detail": (
                    f"最近风险审查：{latest_risk.status}"
                    if latest_risk
                    else "计划生成后必须先跑风险预检"
                ),
                "route": (
                    f"/?module=order_drafts&intent={latest_intent.id}&review=risk"
                    if latest_intent
                    else "/?module=risk"
                ),
                "action_label": "打开风险审查",
            },
            {
                "key": "approval_draft",
                "label": "审批草稿",
                "status": "ready" if latest_draft else "action_required",
                "detail": (
                    f"最近草稿：{latest_draft.approval_status}"
                    if latest_draft
                    else "风险和闸门通过后再生成审批草稿"
                ),
                "route": (
                    f"/?module=order_drafts&draft={latest_draft.id}&intent={latest_draft.order_intent_id}"
                    if latest_draft
                    else f"/?module=order_drafts&intent={latest_intent.id}&review=risk"
                    if latest_intent
                    else "/?module=order_drafts"
                ),
                "action_label": "打开审批草稿" if latest_draft else "准备审批草稿",
            },
        ]
        ready_count = sum(1 for step in steps if step["status"] == "ready")
        next_step = next((step for step in steps if step["status"] != "ready"), steps[-1])
        return {
            "user_id": user_id,
            "generated_at": now,
            "status": "ready_for_local_loop" if ready_count == len(steps) else "action_required",
            "ready_count": ready_count,
            "total_count": len(steps),
            "progress_pct": round((ready_count / len(steps)) * 100),
            "next_action": next_step,
            "steps": steps,
            "latest": {
                "thesis_id": latest_thesis.id if latest_thesis else None,
                "order_intent_id": latest_intent.id if latest_intent else None,
                "risk_check_id": latest_risk.id if latest_risk else None,
                "order_draft_id": latest_draft.id if latest_draft else None,
            },
            "safe_boundary": "只会推进持仓理由、人工计划、风险审查和人工审批；不会自动实盘、自动审批或绕过 gates。",
            "execution_available": False,
        }

    def local_handoff_packet(self, *, user_id: str = "default-user") -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        readiness = self.self_use_readiness(user_id=user_id)
        local_start = self.local_start_status(user_id=user_id)
        workspace = self.workspace_status(user_id=user_id)
        scheduler = self.scheduler_status(user_id=user_id)
        queue = self.action_queue(user_id=user_id, limit=5)
        packet = {
            "user_id": user_id,
            "generated_at": now,
            "packet_type": "local_self_use_handoff",
            "status": readiness["status"],
            "progress_pct": readiness["progress_pct"],
            "remaining_pct": readiness["remaining_pct"],
            "summary": readiness["summary"],
            "data_mode": readiness["data_mode"],
            "next_action": readiness["next_action"],
            "checks": readiness["checks"],
            "workspace": {
                "status": workspace["status"],
                "ready_count": workspace["ready_count"],
                "total_count": workspace["total_count"],
                "queue_count": workspace["queue_count"],
                "primary_action": workspace["primary_action"],
            },
            "onboarding": {
                "status": local_start["onboarding"]["status"],
                "completion_pct": local_start["onboarding"].get("completion_pct"),
                "missing_steps": local_start["onboarding"].get("missing_steps", []),
                "next_step": local_start["onboarding"].get("next_step"),
            },
            "scheduler": {
                "status": scheduler["status"],
                "health_status": scheduler["health_status"],
                "health_label": scheduler["health_label"],
                "health_detail": scheduler["health_detail"],
                "active_jobs": scheduler["active_jobs"],
                "verified_jobs": scheduler["verified_jobs"],
                "last_run_at": scheduler["last_run_at"],
            },
            "today_queue": {
                "total_actions": queue["total_actions"],
                "high_priority_count": queue["high_priority_count"],
                "actions": queue["actions"][:5],
            },
            "local_commands": [
                {
                    "label": "启动后端",
                    "command": "cd backend && DATABASE_URL='sqlite+pysqlite:////Users/lizekai/Documents/交易系统/ai-trading-os/.local-self-use.sqlite' .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000",
                },
                {
                    "label": "启动前端",
                    "command": "cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3001",
                },
                {
                    "label": "健康检查",
                    "command": "curl -s http://127.0.0.1:8000/health",
                },
                {
                    "label": "本地自用回归",
                    "command": "cd frontend && APP_BASE_URL=http://127.0.0.1:3001 API_BASE_URL=http://127.0.0.1:8000 npm run test:local-self-use",
                },
            ],
            "safe_boundaries": [
                "不会自动实盘",
                "不会 wallet signing",
                "不会 withdrawal",
                "不会 DEX swap",
                "不会自动审批",
                "不会绕过 gates",
                "真实 Binance、LLM、Auth、Secret Manager、Broker Sandbox 和 Controlled Pilot 仍需独立实证",
            ],
            "external_blockers": readiness["external_blockers"],
            "contains_secrets": False,
            "execution_available": False,
            "production_capability": False,
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="local_self_use_handoff",
            format="json",
            status="ready",
            payload_json=serializable_packet(packet),
            summary_json={
                "progress_pct": readiness["progress_pct"],
                "status": readiness["status"],
                "next_action": readiness["next_action"],
                "contains_secrets": False,
                "execution_available": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        artifact.payload_json = serializable_packet(packet)
        self._audit("daily_use.local_handoff_packet_created", "ExportArtifact", artifact.id, artifact.summary_json)
        self.db.commit()
        return serializable_packet(packet)

    def update_onboarding(self, *, user_id: str = "default-user", state: dict[str, Any]) -> dict[str, Any]:
        if contains_secret_config_key(state):
            raise DailyUseError("onboarding state must not contain inline secrets")
        existing = dict(self.onboarding_status(user_id=user_id)["state"])
        existing.pop("investment_discipline", None)
        updated = {
            **existing,
            **state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "execution_available": False,
        }
        has_base_onboarding_inputs = all([
            bool(updated.get("workspace_goal")),
            updated.get("risk_boundary_acknowledged") is True,
            bool(updated.get("read_only_data_plan")),
            bool(updated.get("daily_review_time")),
        ])
        if has_base_onboarding_inputs and self._investment_discipline_status(user_id=user_id)["status"] != "ready":
            self.ensure_default_investment_discipline(user_id=user_id)
        base_steps_ready = all([
            has_base_onboarding_inputs,
            self._investment_discipline_status(user_id=user_id)["status"] == "ready" or updated.get("investment_discipline") is True,
        ])
        should_run_first_open = base_steps_ready and not bool(updated.get("first_daily_open"))
        if should_run_first_open:
            updated["first_daily_open"] = True
        self.upsert_local_config(
            config_key="founder_onboarding",
            user_id=user_id,
            value_json=updated,
            description="Founder daily-use onboarding state.",
        )
        self._audit("daily_use.onboarding_updated", "LocalUserConfig", "founder_onboarding", {"user_id": user_id})
        if should_run_first_open:
            self.daily_open(user_id=user_id)
        result = self.onboarding_status(user_id=user_id)
        if result["status"] == "ready":
            self._record_verified_activation(user_id=user_id, event_name="onboarding_completed")
            self.db.commit()
        return result

    def daily_open(self, *, user_id: str = "default-user") -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        overview = self.overview(user_id=user_id)
        # overview embeds a raw ORM ExportArtifact for internal consumers;
        # replace it with a JSON-safe summary before persisting the packet.
        last_export = overview.get("last_export")
        overview = {
            **overview,
            "last_export": (
                {"id": last_export.id, "export_type": last_export.export_type, "created_at": last_export.created_at}
                if last_export is not None
                else None
            ),
        }
        queue = self.action_queue(user_id=user_id, limit=10)
        packet = {
            "user_id": user_id,
            "opened_at": now,
            "status": "open",
            "overview": overview,
            "queue_summary": {
                "total_actions": queue["total_actions"],
                "due_count": queue["due_count"],
                "high_priority_count": queue["high_priority_count"],
            },
            "top_actions": queue["actions"][:5],
            "next_action": queue["actions"][0]["next_action"] if queue["actions"] else "创建或复查第一项只读任务。",
            "execution_available": False,
        }
        self.upsert_local_config(
            config_key="daily_open_latest",
            user_id=user_id,
            value_json=serializable_packet(packet),
            description="Latest founder daily open packet.",
        )
        record = ExportArtifact(
            user_id=user_id,
            export_type="daily_open_record",
            format="json",
            status="open",
            payload_json=serializable_packet(packet),
            summary_json={"opened_at": now.isoformat(), "due_count": queue["due_count"], "high_priority_count": queue["high_priority_count"]},
            file_path=None,
        )
        self.db.add(record)
        self.db.flush()
        self._record_verified_activation(user_id=user_id, event_name="daily_open")
        earliest_open = self.db.scalar(
            select(func.min(ExportArtifact.created_at)).where(
                ExportArtifact.user_id == user_id,
                ExportArtifact.export_type == "daily_open_record",
            )
        )
        if earliest_open is not None and earliest_open.tzinfo is None:
            earliest_open = earliest_open.replace(tzinfo=timezone.utc)
        if earliest_open is not None and earliest_open <= now - timedelta(days=7):
            self._record_verified_activation(user_id=user_id, event_name="weekly_return")
        self._audit("daily_use.daily_opened", "ExportArtifact", record.id, {"user_id": user_id})
        self.db.commit()
        return packet

    def _record_verified_activation(self, *, user_id: str, event_name: str) -> None:
        event_type = f"activation.{event_name}"
        existing = self.db.scalar(
            select(OperationalEvent.id).where(
                OperationalEvent.user_id == user_id,
                OperationalEvent.event_type == event_type,
                OperationalEvent.source == "daily_use",
            ).limit(1)
        )
        if existing is not None:
            return
        self.db.add(OperationalEvent(
            user_id=user_id,
            event_type=event_type,
            severity="info",
            source="daily_use",
            message=f"Verified workflow activation: {event_name}",
            status="closed",
            payload_json={"verified_business_event": True, "execution_available": False},
        ))

    def daily_close(self, *, user_id: str = "default-user", review_json: dict[str, Any] | None = None) -> dict[str, Any]:
        if contains_secret_config_key(review_json or {}):
            raise DailyUseError("daily close review must not contain inline secrets")
        now = datetime.now(timezone.utc)
        queue = self.action_queue(user_id=user_id, limit=20)
        packet = {
            "user_id": user_id,
            "closed_at": now,
            "status": "closed",
            "review_json": review_json or {},
            "queue_summary": {
                "remaining_actions": queue["total_actions"],
                "high_priority_count": queue["high_priority_count"],
            },
            "carry_forward_actions": queue["actions"][:5],
            "next_action": "下次开盘检查会从未解决的高优先级事项继续。"
            if queue["actions"]
            else "今日队列已清空，请继续保持只读数据与本地备份正常。",
            "execution_available": False,
        }
        self.upsert_local_config(
            config_key="daily_close_latest",
            user_id=user_id,
            value_json=serializable_packet(packet),
            description="Latest founder daily close packet.",
        )
        record = ExportArtifact(
            user_id=user_id,
            export_type="daily_close_record",
            format="json",
            status="closed",
            payload_json=serializable_packet(packet),
            summary_json={"closed_at": now.isoformat(), "remaining_actions": queue["total_actions"], "high_priority_count": queue["high_priority_count"]},
            file_path=None,
        )
        self.db.add(record)
        self.db.flush()
        self._audit("daily_use.daily_closed", "ExportArtifact", record.id, {"user_id": user_id})
        self.db.commit()
        return packet

    def daily_history(self, *, user_id: str = "default-user", limit: int = 30) -> dict[str, Any]:
        records = list(
            self.db.scalars(
                select(ExportArtifact)
                .where(ExportArtifact.user_id == user_id, ExportArtifact.export_type.in_(["daily_open_record", "daily_close_record"]))
                .order_by(ExportArtifact.created_at.desc())
                .limit(max(1, min(limit, 200)))
            ).all()
        )
        return {
            "user_id": user_id,
            "count": len(records),
            "records": [
                {
                    "id": record.id,
                    "kind": "open" if record.export_type == "daily_open_record" else "close",
                    "created_at": record.created_at,
                    "summary": record.summary_json,
                }
                for record in records
            ],
            "execution_available": False,
        }

    def drilldown(self, *, queue_item_id: str, user_id: str = "default-user") -> dict[str, Any]:
        queue = self.action_queue(user_id=user_id, limit=200)
        queue_item = next((item for item in queue["actions"] if item["id"] == queue_item_id), None)
        if queue_item is None:
            raise DailyUseError("queue item not found")
        evidence: list[dict[str, Any]] = []
        entity_type = queue_item.get("related_entity_type")
        entity_id = queue_item.get("related_entity_id")
        if entity_type == "Reminder" and entity_id:
            reminder = self.db.get(Reminder, entity_id)
            if reminder is not None:
                evidence.append({"type": "reminder", "payload": reminder_payload(reminder)})
        elif entity_type == "WatchlistItem" and entity_id:
            item = self.db.get(WatchlistItem, entity_id)
            if item is not None:
                evidence.append({"type": "watchlist_item", "payload": watchlist_payload(item)})
                if item.investment_thesis_id:
                    thesis = self.db.get(InvestmentThesis, item.investment_thesis_id)
                    if thesis is not None:
                        evidence.append({"type": "investment_thesis", "payload": thesis_payload(thesis)})
        elif entity_type == "Position" and entity_id:
            position = self.db.get(Position, entity_id)
            if position is not None:
                evidence.append({"type": "position", "payload": position_payload(position)})
                asset = self.db.get(Asset, position.asset_id)
                if asset is not None:
                    evidence.append({"type": "asset", "payload": asset_payload(asset)})
                    theses = list(
                        self.db.scalars(
                            select(InvestmentThesis)
                            .where(
                                InvestmentThesis.asset_id == asset.id,
                                InvestmentThesis.status.in_(["active", "monitoring"]),
                            )
                            .order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc())
                            .limit(3)
                        ).all()
                    )
                    evidence.extend({"type": "investment_thesis", "payload": thesis_payload(thesis)} for thesis in theses)
        elif queue_item_id.startswith("data:"):
            dataset_type = queue_item_id.split(":", 1)[1]
            freshness = DataSourceService(self.db).freshness_overview()
            evidence.extend(
                {"type": "data_freshness", "payload": item}
                for item in freshness["items"]
                if item["dataset_type"] == dataset_type
            )
        elif queue_item_id == "backup:local_manifest":
            latest = self.db.scalar(
                select(ExportArtifact)
                .where(ExportArtifact.user_id == user_id)
                .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
                .limit(1)
            )
            evidence.append({"type": "latest_export", "payload": export_payload(latest) if latest else None})
        return {
            "user_id": user_id,
            "queue_item": queue_item,
            "evidence": evidence,
            "next_actions": [
                queue_item["next_action"],
                "Keep this drilldown read-only; any trade-related action must go through thesis, risk, behavior, approval, and audit gates.",
            ],
            "execution_available": False,
        }

    def overview(self, *, user_id: str = "default-user") -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        watchlist_count = self._count(select(func.count()).select_from(WatchlistItem).where(WatchlistItem.user_id == user_id, WatchlistItem.is_active.is_(True)))
        active_reminders_count = self._count(select(func.count()).select_from(Reminder).where(Reminder.user_id == user_id, Reminder.status.in_(["pending", "snoozed"])))
        due_reminders_count = len(self._pending_due_reminders(user_id=user_id, now=now, limit=1000))
        scheduled_jobs_count = self._count(select(func.count()).select_from(ScheduledJob))
        last_export = self.db.scalar(
            select(ExportArtifact)
            .where(ExportArtifact.user_id == user_id)
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        backup_recommended = last_export is None or is_older_than(last_export.created_at, now=now, delta=timedelta(days=7))
        return {
            "user_id": user_id,
            "watchlist_count": watchlist_count,
            "active_reminders_count": active_reminders_count,
            "due_reminders_count": due_reminders_count,
            "scheduled_jobs_count": scheduled_jobs_count,
            "last_export": last_export,
            "backup_recommended": backup_recommended,
            "execution_available": False,
        }

    def action_queue(
        self,
        *,
        user_id: str = "default-user",
        limit: int = 20,
        source: str | None = None,
        priority: str | None = None,
        action_type: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        actions: list[dict[str, Any]] = []
        scan_limit = max(limit, 100)
        resolutions = self._queue_resolutions(user_id=user_id)

        due_reminders = self._pending_due_reminders(user_id=user_id, now=now, limit=scan_limit)
        for reminder in due_reminders:
            actions.append(
                {
                    "id": f"reminder:{reminder.id}",
                    "action_type": "complete_reminder",
                    "priority": normalize_priority(reminder.priority),
                    "title": reminder.title,
                    "detail": f"Due {reminder.due_at.isoformat() if reminder.due_at else 'now'}",
                    "status": "open",
                    "source": "portfolio_risk" if reminder.reminder_type == "portfolio_risk" else "reminders",
                    "related_entity_type": "Reminder",
                    "related_entity_id": reminder.id,
                    "due_at": reminder.due_at,
                    "created_at": reminder.created_at,
                    "next_action": (
                        "打开风险终端，检查时序证据并记录人工复核结论。"
                        if reminder.reminder_type == "portfolio_risk"
                        else "查看提醒上下文，然后完成、延期或忽略。"
                    ),
                    "execution_available": False,
                }
            )

        local_start = self.local_start_status(user_id=user_id)
        for task in local_start.get("setup_tasks", []):
            actions.append(
                {
                    "id": task["id"],
                    "action_type": task["action_type"],
                    "priority": "high",
                    "title": task["title"],
                    "detail": task["detail"],
                    "status": "open",
                    "source": "local_start",
                    "related_entity_type": "LocalUserConfig",
                    "related_entity_id": "local_start",
                    "due_at": None,
                    "created_at": now,
                    "next_action": task["next_action"],
                    "route": task["route"],
                    "action_label": task["action_label"],
                    "guidance_steps": task["guidance_steps"],
                    "evidence_status": task.get("evidence_status"),
                    "execution_available": False,
                }
            )

        high_watchlist = self._high_priority_watchlist(user_id=user_id, limit=scan_limit)
        for item in high_watchlist[: max(0, scan_limit - len(actions))]:
            actions.append(
                {
                    "id": f"watchlist:{item.id}",
                    "action_type": "review_watchlist",
                    "priority": "high",
                    "title": f"复查 {item.symbol} Thesis",
                    "detail": item.notes or "High-priority watchlist item.",
                    "status": "open",
                    "source": "watchlist",
                    "related_entity_type": "WatchlistItem",
                    "related_entity_id": item.id,
                    "due_at": None,
                    "created_at": item.created_at,
                    "next_action": "决策前先更新 Thesis、失效条件和最新只读数据。",
                    "execution_available": False,
                }
            )

        freshness = DataSourceService(self.db).freshness_overview()
        for item in freshness["items"]:
            if item["status"] not in {"missing", "stale", "blocked"}:
                continue
            freshness_priority = "high" if item["status"] == "blocked" else "normal"
            label = dataset_display_label(str(item["dataset_type"]), fallback=str(item["label"]))
            actions.append(
                {
                    "id": f"data:{item['dataset_type']}",
                    "action_type": "refresh_data",
                    "priority": freshness_priority,
                    "title": f"更新{label}",
                    "detail": f"{label}当前状态：{freshness_status_label(item['status'])}。",
                    "status": "open",
                    "source": "data_freshness",
                    "related_entity_type": "DataSnapshot",
                    "related_entity_id": item["snapshot_id"],
                    "due_at": None,
                    "created_at": item["latest_as_of"],
                    "next_action": item["next_action"],
                    "execution_available": False,
                }
            )

        for item in self._portfolio_risk_actions(user_id=user_id):
            actions.append(item)

        for item in self._thesis_coverage_actions(user_id=user_id):
            actions.append(item)

        review_tasks = list(
            self.db.scalars(
                select(WorkflowReviewTask)
                .where(
                    WorkflowReviewTask.user_id == user_id,
                    WorkflowReviewTask.status.in_(["open", "in_progress"]),
                    WorkflowReviewTask.item_type.in_(["thesis_monitor_due", "post_trade_review_pending"]),
                )
                .order_by(WorkflowReviewTask.due_at.asc(), WorkflowReviewTask.created_at.asc())
                .limit(scan_limit)
            ).all()
        )
        for task in review_tasks:
            is_thesis = task.item_type == "thesis_monitor_due"
            actions.append(
                {
                    "id": f"workflow:{task.id}",
                    "action_type": "record_thesis_checkpoint" if is_thesis else "complete_post_trade_review",
                    "priority": normalize_priority(task.priority),
                    "title": task.title,
                    "detail": task.detail,
                    "status": task.status,
                    "source": "thesis_checkpoint" if is_thesis else "post_trade_review",
                    "related_entity_type": task.related_entity_type,
                    "related_entity_id": task.related_entity_id,
                    "due_at": task.due_at,
                    "created_at": task.created_at,
                    "next_action": task.payload_json.get("next_action") or "Open the review workspace and record a human verdict.",
                    "route": "/?module=investment_logic&tab=thesis" if is_thesis else "/?module=post_trade_review",
                    "execution_available": False,
                }
            )

        daily_overview = self.overview(user_id=user_id)
        if daily_overview["backup_recommended"]:
            actions.append(
                {
                    "id": "backup:local_manifest",
                    "action_type": "create_backup_manifest",
                    "priority": "normal",
                    "title": "创建本地备份清单",
                    "detail": "最近 7 天没有新的本地备份清单。",
                    "status": "open",
                    "source": "backup",
                    "related_entity_type": "ExportArtifact",
                    "related_entity_id": daily_overview["last_export"].id if daily_overview["last_export"] else None,
                    "due_at": None,
                    "created_at": daily_overview["last_export"].created_at if daily_overview["last_export"] else None,
                    "next_action": "更改数据连接或扩大使用范围前，先生成本地备份清单。",
                    "execution_available": False,
                }
            )

        if source:
            actions = [item for item in actions if item["source"] == source]
        if priority:
            actions = [item for item in actions if item["priority"] == priority]
        if action_type:
            actions = [item for item in actions if item["action_type"] == action_type]

        actions = [item for item in actions if self._queue_item_visible(item["id"], resolutions=resolutions, now=now)]

        actions.sort(key=lambda item: (priority_rank(item["priority"]), source_rank(str(item.get("source") or "")), queue_time(item.get("due_at") or item.get("created_at"), now), item["title"]))
        actions = [present_queue_action(item) for item in actions]
        total_open_count = len(actions)
        actions = actions[:limit]
        return {
            "user_id": user_id,
            "generated_at": now,
            "total_actions": total_open_count,
            "due_count": sum(1 for item in actions if item["due_at"] is not None and queue_time(item["due_at"], now) <= now),
            "high_priority_count": sum(1 for item in actions if item["priority"] == "high"),
            "execution_available": False,
            "actions": actions,
        }

    def apply_queue_action(
        self,
        *,
        queue_item_id: str,
        user_id: str = "default-user",
        action: str,
        assignee_id: str | None = None,
        snooze_minutes: int = 60,
    ) -> dict[str, Any]:
        if action not in {"complete", "snooze", "dismiss", "assign"}:
            raise DailyUseError("action must be complete, snooze, dismiss, or assign")
        if action == "assign" and not str(assignee_id or "").strip():
            raise DailyUseError("assignee_id is required when assigning a queue item")
        if snooze_minutes < 5 or snooze_minutes > 10080:
            raise DailyUseError("snooze_minutes must be between 5 and 10080")

        now = datetime.now(timezone.utc)
        if queue_item_id.startswith("reminder:"):
            reminder = self._reminder(queue_item_id.split(":", 1)[1])
            if reminder.user_id != user_id:
                raise DailyUseError("queue item not found")
            if action == "complete":
                reminder.status = "done"
                reminder.completed_at = now
            elif action == "dismiss":
                reminder.status = "dismissed"
            elif action == "snooze":
                reminder.status = "snoozed"
                reminder.due_at = now + timedelta(minutes=snooze_minutes)
            else:
                reminder.payload_json = {**(reminder.payload_json or {}), "assignee_id": assignee_id}
            self.db.flush()

        resolutions = self._queue_resolutions(user_id=user_id)
        resolutions[queue_item_id] = {
            "action": action,
            "assignee_id": assignee_id,
            "updated_at": now.isoformat(),
            "hidden_until": (now + timedelta(minutes=snooze_minutes)).isoformat() if action == "snooze" else None,
        }
        self.upsert_local_config(
            config_key="today_queue_resolutions",
            user_id=user_id,
            value_json=resolutions,
            description="User-controlled Today Queue resolutions.",
        )
        self._audit("daily_use.queue_action_applied", "TodayQueueItem", queue_item_id, {"action": action, "assignee_id": assignee_id})
        queue = self.action_queue(user_id=user_id)
        return {
            "queue_item_id": queue_item_id,
            "action": action,
            "assignee_id": assignee_id,
            "message": queue_action_message(action=action, has_next=bool(queue["actions"])),
            "next_item": queue["actions"][0] if queue["actions"] else None,
            "queue": queue,
            "execution_available": False,
        }

    def apply_queue_batch_action(
        self,
        *,
        queue_item_ids: list[str],
        user_id: str = "default-user",
        action: str,
        assignee_id: str | None = None,
        snooze_minutes: int = 60,
    ) -> dict[str, Any]:
        item_ids = list(dict.fromkeys(str(item_id).strip() for item_id in queue_item_ids if str(item_id).strip()))
        if not item_ids:
            raise DailyUseError("queue_item_ids must contain at least one item")
        if len(item_ids) > 20:
            raise DailyUseError("batch actions are limited to 20 queue items")
        if action not in {"complete", "snooze", "dismiss", "assign"}:
            raise DailyUseError("action must be complete, snooze, dismiss, or assign")
        if action == "assign" and not str(assignee_id or "").strip():
            raise DailyUseError("assignee_id is required when assigning queue items")
        if snooze_minutes < 5 or snooze_minutes > 10080:
            raise DailyUseError("snooze_minutes must be between 5 and 10080")

        visible_ids = {item["id"] for item in self.action_queue(user_id=user_id, limit=200)["actions"]}
        missing = [item_id for item_id in item_ids if item_id not in visible_ids]
        if missing:
            raise DailyUseError(f"queue items are not currently visible: {', '.join(missing[:3])}")

        results = [
            self.apply_queue_action(
                queue_item_id=item_id,
                user_id=user_id,
                action=action,
                assignee_id=assignee_id,
                snooze_minutes=snooze_minutes,
            )
            for item_id in item_ids
        ]
        queue = self.action_queue(user_id=user_id)
        self._audit(
            "daily_use.queue_batch_action_applied",
            "TodayQueueBatch",
            f"{user_id}:{action}",
            {"action": action, "queue_item_ids": item_ids, "count": len(item_ids), "assignee_id": assignee_id},
        )
        self.db.commit()
        return {
            "action": action,
            "processed_count": len(results),
            "queue_item_ids": item_ids,
            "message": f"已批量处理 {len(results)} 项，剩余 {queue['total_actions']} 项。",
            "next_item": queue["actions"][0] if queue["actions"] else None,
            "queue": queue,
            "execution_available": False,
        }

    def run_queue_item(self, *, queue_item_id: str, user_id: str = "default-user", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        queue = self.action_queue(user_id=user_id, limit=200)
        queue_item = next((item for item in queue["actions"] if item["id"] == queue_item_id), None)
        if queue_item is None:
            raise DailyUseError("queue item not found")

        if queue_item["action_type"] == "refresh_data" and queue_item_id.startswith("data:"):
            result = self._run_data_refresh_task(
                dataset_type=queue_item_id.split(":", 1)[1],
                user_id=user_id,
                payload=payload or {},
            )
        elif queue_item["action_type"] == "create_backup_manifest" and queue_item_id == "backup:local_manifest":
            artifact = self.create_backup_manifest(user_id=user_id)
            result = {
                "status": "completed",
                "message": "本地备份清单已生成。",
                "artifact_id": artifact.id,
                "summary": artifact.summary_json,
                "route": f"/?module=settings&tab=preferences&artifact={artifact.id}",
                "next_steps": ["需要恢复或迁移时，先下载并核对这份备份清单。"],
            }
        elif queue_item["action_type"] == "prepare_binance_readonly_evidence" and queue_item_id == "local_start:binance_evidence_preflight":
            result = self._run_binance_evidence_preflight_task(user_id=user_id, route=queue_item["route"])
        elif queue_item["action_type"] == "run_binance_private_readonly_sync" and queue_item_id == "local_start:binance_private_sync":
            result = self._run_binance_private_sync_task(user_id=user_id, route=queue_item["route"])
        else:
            result = {
                "status": "manual_required",
                "message": "这项任务需要人工判断，已为你准备好对应入口。",
                "route": queue_item["route"],
                "next_steps": queue_item["guidance_steps"],
            }

        if result["status"] == "completed":
            resolved = self.apply_queue_action(
                queue_item_id=queue_item_id,
                user_id=user_id,
                action="complete",
            )
            return {
                **result,
                "queue_item_id": queue_item_id,
                "queue": resolved["queue"],
                "next_item": resolved["next_item"],
                "execution_available": False,
            }

        return {
            **result,
            "queue_item_id": queue_item_id,
            "queue": self.action_queue(user_id=user_id),
            "next_item": queue["actions"][0] if queue["actions"] else None,
            "execution_available": False,
        }

    def _run_binance_evidence_preflight_task(self, *, user_id: str, route: str) -> dict[str, Any]:
        evidence = self._binance_readonly_evidence_state(user_id=user_id)
        return {
            "status": "manual_required",
            "message": "需要先生成 Binance 只读预检包，并保存脱敏权限截图与提现关闭证明。",
            "route": route,
            "artifact_id": evidence.get("preflight_artifact_id"),
            "summary": {
                "provider": "binance_spot_readonly",
                "evidence_status": evidence,
                "missing_evidence": self._binance_missing_evidence(evidence),
                "external_api_called": False,
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
            },
            "next_steps": [
                "确认 Binance Key 只有只读权限，不包含交易、提现或转账权限。",
                "上传或填写脱敏权限截图引用与提现关闭证明引用。",
                "生成并下载预检包后，Today Queue 会进入私有只读同步步骤。",
            ],
        }

    def _run_binance_private_sync_task(self, *, user_id: str, route: str) -> dict[str, Any]:
        evidence = self._binance_readonly_evidence_state(user_id=user_id)
        preflight_payload = self._latest_binance_preflight_payload(user_id=user_id)
        endpoints = dict(preflight_payload.get("private_verification_endpoints") or {})
        if not endpoints:
            endpoints = {
                "sync_account": "/data-sources/connections/{connection_id}/sync-account",
                "phase_private_verify": "/phase-development/real-readonly-data-proof/binance-private-verify",
            }
        return {
            "status": "manual_required",
            "message": "需要在你的私有环境运行 Binance 只读同步；Today Queue 不会直接调用 Binance。",
            "route": route,
            "artifact_id": evidence.get("preflight_artifact_id"),
            "snapshot_id": evidence.get("snapshot_id"),
            "quality_report_id": evidence.get("quality_report_id"),
            "summary": {
                "provider": "binance_spot_readonly",
                "evidence_status": evidence,
                "missing_evidence": self._binance_missing_evidence(evidence),
                "private_verification_endpoints": endpoints,
                "external_api_called": False,
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
            },
            "next_steps": [
                "确认提现关闭证明仍有效，Key 仍为只读。",
                "在私有环境运行只读账户同步，保存 snapshot 和 quality report。",
                "下载 audit packet，核对无交易、无提现、无签名能力后回到 Today Queue。",
            ],
        }

    def _latest_binance_preflight_payload(self, *, user_id: str) -> dict[str, Any]:
        preflight = self.db.scalar(
            select(ExportArtifact)
            .where(
                ExportArtifact.user_id == user_id,
                ExportArtifact.export_type == "binance_readonly_evidence_preflight",
            )
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        return dict(preflight.payload_json or {}) if preflight is not None else {}

    @staticmethod
    def _binance_missing_evidence(evidence: dict[str, Any]) -> list[str]:
        missing = []
        if not evidence.get("preflight_ready"):
            missing.append("Binance 只读预检包")
        if not evidence.get("snapshot_ready"):
            missing.append("真实只读 snapshot")
        if not evidence.get("quality_report_ready"):
            missing.append("quality report")
        return missing

    def _queue_resolutions(self, *, user_id: str) -> dict[str, Any]:
        config = self.db.scalar(select(LocalUserConfig).where(
            LocalUserConfig.user_id == user_id,
            LocalUserConfig.config_key == "today_queue_resolutions",
        ).limit(1))
        return dict(config.value_json or {}) if config is not None else {}

    @staticmethod
    def _queue_item_visible(queue_item_id: str, *, resolutions: dict[str, Any], now: datetime) -> bool:
        resolution = resolutions.get(queue_item_id)
        if not isinstance(resolution, dict):
            return True
        action = resolution.get("action")
        if action in {"complete", "dismiss"}:
            return False
        if action == "snooze":
            hidden_until = resolution.get("hidden_until")
            if hidden_until:
                try:
                    return datetime.fromisoformat(str(hidden_until)) <= now
                except ValueError:
                    return True
        return True

    def list_watchlist(self, *, user_id: str = "default-user", active_only: bool = True, limit: int = 100) -> list[WatchlistItem]:
        query = select(WatchlistItem).where(WatchlistItem.user_id == user_id)
        if active_only:
            query = query.where(WatchlistItem.is_active.is_(True))
        return list(self.db.scalars(db_order(query, WatchlistItem).limit(limit)).all())

    def create_watchlist_item(self, **payload: Any) -> WatchlistItem:
        if contains_secret_config_key(payload.get("alert_rules_json") or {}):
            raise DailyUseError("alert_rules_json must not contain inline secrets")
        symbol = str(payload["symbol"]).upper().strip()
        if not symbol:
            raise DailyUseError("symbol is required")

        user_id = str(payload.get("user_id") or "default-user")
        existing = self.db.scalar(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol)
            .order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
            .limit(1)
        )
        asset = self._asset_for(symbol=symbol, asset_id=payload.get("asset_id"))
        if existing is not None:
            existing.is_active = True
            existing.asset_id = asset.id if asset is not None else payload.get("asset_id") or existing.asset_id
            existing.investment_thesis_id = payload.get("investment_thesis_id") or existing.investment_thesis_id
            existing.name = payload.get("name") or (asset.name if asset is not None else existing.name)
            existing.asset_type = payload.get("asset_type") or (asset.asset_type if asset is not None else existing.asset_type)
            existing.market = payload.get("market") or (asset.market if asset is not None else existing.market)
            existing.priority = payload.get("priority") or existing.priority
            existing.alert_rules_json = payload.get("alert_rules_json") or existing.alert_rules_json
            existing.notes = payload.get("notes") if payload.get("notes") is not None else existing.notes
            item = existing
            action = "watchlist_item.reactivated"
        else:
            item = WatchlistItem(
                user_id=user_id,
                asset_id=asset.id if asset is not None else payload.get("asset_id"),
                investment_thesis_id=payload.get("investment_thesis_id"),
                symbol=symbol,
                name=payload.get("name") or (asset.name if asset is not None else None),
                asset_type=payload.get("asset_type") or (asset.asset_type if asset is not None else "stock"),
                market=payload.get("market") or (asset.market if asset is not None else "US"),
                priority=payload.get("priority") or "normal",
                alert_rules_json=payload.get("alert_rules_json") or {},
                notes=payload.get("notes"),
                is_active=True,
            )
            self.db.add(item)
            action = "watchlist_item.created"
        self.db.flush()
        self._audit(action, "WatchlistItem", item.id, {"symbol": item.symbol, "execution_available": False})
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_watchlist_item(self, item_id: str, **payload: Any) -> WatchlistItem:
        item = self._watchlist_item(item_id)
        if contains_secret_config_key(payload.get("alert_rules_json") or {}):
            raise DailyUseError("alert_rules_json must not contain inline secrets")
        for field in ["investment_thesis_id", "name", "priority", "alert_rules_json", "notes", "is_active"]:
            if field in payload and payload[field] is not None:
                setattr(item, field, payload[field])
        self.db.flush()
        self._audit("watchlist_item.updated", "WatchlistItem", item.id, {"symbol": item.symbol})
        self.db.commit()
        self.db.refresh(item)
        return item

    def deactivate_watchlist_item(self, item_id: str) -> WatchlistItem:
        item = self._watchlist_item(item_id)
        item.is_active = False
        self.db.flush()
        self._audit("watchlist_item.deactivated", "WatchlistItem", item.id, {"symbol": item.symbol})
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_reminders(self, *, user_id: str = "default-user", status: str | None = None, limit: int = 100) -> list[Reminder]:
        query = select(Reminder).where(Reminder.user_id == user_id)
        if status:
            query = query.where(Reminder.status == status)
        return list(
            self.db.scalars(
                query.order_by(Reminder.due_at.is_(None), Reminder.due_at.asc(), Reminder.created_at.desc(), Reminder.id.desc()).limit(limit)
            ).all()
        )

    def create_reminder(self, **payload: Any) -> Reminder:
        if contains_secret_config_key(payload.get("recurrence_json") or {}) or contains_secret_config_key(payload.get("payload_json") or {}):
            raise DailyUseError("reminder payload must not contain inline secrets")
        reminder = Reminder(
            user_id=str(payload.get("user_id") or "default-user"),
            title=str(payload["title"]),
            reminder_type=str(payload.get("reminder_type") or "manual"),
            related_entity_type=payload.get("related_entity_type"),
            related_entity_id=payload.get("related_entity_id"),
            due_at=payload.get("due_at"),
            recurrence_json=payload.get("recurrence_json") or {},
            priority=payload.get("priority") or "normal",
            status="pending",
            payload_json=payload.get("payload_json") or {},
        )
        self.db.add(reminder)
        self.db.flush()
        self._audit("reminder.created", "Reminder", reminder.id, {"reminder_type": reminder.reminder_type, "execution_available": False})
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def update_reminder(self, reminder_id: str, **payload: Any) -> Reminder:
        reminder = self._reminder(reminder_id)
        if contains_secret_config_key(payload.get("recurrence_json") or {}) or contains_secret_config_key(payload.get("payload_json") or {}):
            raise DailyUseError("reminder payload must not contain inline secrets")
        for field in ["title", "due_at", "recurrence_json", "priority", "status", "payload_json"]:
            if field in payload and payload[field] is not None:
                setattr(reminder, field, payload[field])
        if reminder.status == "done" and reminder.completed_at is None:
            reminder.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        self._audit("reminder.updated", "Reminder", reminder.id, {"status": reminder.status})
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def complete_reminder(self, reminder_id: str) -> Reminder:
        reminder = self._reminder(reminder_id)
        reminder.status = "done"
        reminder.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        self._audit("reminder.completed", "Reminder", reminder.id, {"reminder_type": reminder.reminder_type})
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def cleanup_local_test_artifacts(self, *, user_id: str = "default-user", dry_run: bool = False) -> dict[str, Any]:
        reminders = list(
            self.db.scalars(
                select(Reminder)
                .where(Reminder.user_id == user_id, Reminder.status.in_(["pending", "snoozed"]))
                .order_by(Reminder.created_at.desc())
                .limit(1000)
            ).all()
        )
        matched = [item for item in reminders if is_e2e_artifact(item.title, item.payload_json)]
        if not dry_run:
            now = datetime.now(timezone.utc)
            for item in matched:
                item.status = "dismissed"
                item.completed_at = now
            self.db.flush()
            self._audit(
                "daily_use.local_test_artifacts_cleaned",
                "Reminder",
                "e2e_artifacts",
                {"user_id": user_id, "dismissed_reminders": len(matched), "execution_available": False},
            )
            self.db.commit()
        queue = self.action_queue(user_id=user_id, limit=5)
        return {
            "user_id": user_id,
            "dry_run": dry_run,
            "matched_reminders": len(matched),
            "dismissed_reminders": 0 if dry_run else len(matched),
            "remaining_actions": queue["total_actions"],
            "next_item": queue["actions"][0] if queue["actions"] else None,
            "message": "发现测试提醒，已清理出 Today Queue。" if matched and not dry_run else "没有发现待清理的 E2E 测试提醒。",
            "execution_available": False,
        }

    def list_local_config(self, *, user_id: str = "default-user") -> list[LocalUserConfig]:
        return list(
            self.db.scalars(
                select(LocalUserConfig)
                .where(LocalUserConfig.user_id == user_id, ~LocalUserConfig.config_key.startswith("news_feed:"), ~LocalUserConfig.config_key.startswith("human_control:"))
                .order_by(LocalUserConfig.config_key.asc(), LocalUserConfig.id.asc())
            ).all()
        )

    def upsert_local_config(self, *, config_key: str, user_id: str, value_json: dict[str, Any], description: str | None) -> LocalUserConfig:
        if config_key.startswith(("news_feed:", "human_control:")):
            raise DailyUseError("use the authenticated settings API for this configuration namespace")
        if contains_secret_config_key({config_key: value_json}):
            raise DailyUseError("local config must not contain inline secrets")
        config = self.db.scalar(
            select(LocalUserConfig)
            .where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == config_key)
            .limit(1)
        )
        if config is None:
            config = LocalUserConfig(user_id=user_id, config_key=config_key, value_json=value_json, description=description)
            self.db.add(config)
            action = "local_config.created"
        else:
            config.value_json = value_json
            config.description = description
            action = "local_config.updated"
        self.db.flush()
        self._audit(action, "LocalUserConfig", config.id, {"config_key": config.config_key})
        self.db.commit()
        self.db.refresh(config)
        return config

    def list_exports(self, *, user_id: str = "default-user", limit: int = 50) -> list[ExportArtifact]:
        return list(
            self.db.scalars(
                select(ExportArtifact)
                .where(ExportArtifact.user_id == user_id)
                .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
                .limit(limit)
            ).all()
        )

    def get_export(self, artifact_id: str) -> ExportArtifact:
        artifact = self.db.get(ExportArtifact, artifact_id)
        if artifact is None:
            raise DailyUseError("export artifact not found")
        return artifact

    def create_export(self, *, user_id: str, export_type: str, include_sections: list[str] | None = None) -> ExportArtifact:
        sections = include_sections or sections_for_export(export_type)
        payload = self._export_payload(user_id=user_id, export_type=export_type, sections=sections)
        summary = {
            "export_type": export_type,
            "sections": sections,
            "counts": {key: len(value) if isinstance(value, list) else 1 for key, value in payload["sections"].items()},
            "execution_available": False,
            "contains_secrets": False,
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type=export_type,
            format="json",
            status="ready",
            payload_json=payload,
            summary_json=summary,
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        self._audit("export_artifact.created", "ExportArtifact", artifact.id, summary)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def create_backup_manifest(self, *, user_id: str = "default-user") -> ExportArtifact:
        return self.create_export(user_id=user_id, export_type="local_backup_manifest", include_sections=DEFAULT_EXPORT_SECTIONS)

    def _run_data_refresh_task(self, *, dataset_type: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data_mode = self.local_start_status(user_id=user_id).get("data_mode")
        symbols = self._focus_symbols(user_id=user_id)
        if dataset_type == "market_quotes":
            connection = self._default_market_connection()
            result = DataSourceService(self.db).import_quotes(connection.id, symbols=symbols, asset_type="stock", market="US", currency="USD")
            return {
                "status": "completed",
                "message": f"已刷新 {result.quotes_imported} 条只读行情。",
                "snapshot_id": result.snapshot.id,
                "quality_report_id": result.quality_report.id,
                "summary": {"symbols": result.symbols, "skipped": result.skipped, "source": result.connection.provider},
                "route": "/?module=settings&tab=data",
                "next_steps": ["查看质量报告。", "回到 Today Queue 处理下一项。"],
            }
        if dataset_type == "market_candles":
            connection = self._default_market_connection()
            result = DataSourceService(self.db).import_candles(connection.id, symbols=symbols[:6], timeframe="1d", limit=30, asset_type="stock", market="US", currency="USD")
            return {
                "status": "completed",
                "message": f"已刷新 {result.candles_imported} 条只读 K 线。",
                "snapshot_id": result.snapshot.id,
                "quality_report_id": result.quality_report.id,
                "summary": {"symbols": result.symbols, "timeframe": result.timeframe, "skipped": result.skipped, "source": result.connection.provider},
                "route": "/?module=settings&tab=data",
                "next_steps": ["行情信号和风险模型现在可以读取新的 K 线。"],
            }
        if dataset_type in {"fx_rates", "corporate_actions"} and data_mode == "simulation":
            return self._persist_simulated_external_dataset(dataset_type=dataset_type, symbols=symbols)
        if dataset_type == "read_only_account":
            connection = self._syncable_account_connection()
            if connection is not None:
                result = DataSourceService(self.db).sync_account_snapshot(connection.id, sample_payload=payload.get("sample_payload"))
                return {
                    "status": "completed",
                    "message": f"已同步只读账户快照：{result.positions_synced} 个持仓，{result.balances_synced} 个余额。",
                    "snapshot_id": result.snapshot.id,
                    "quality_report_id": result.quality_report.id,
                    "summary": {"provider": result.connection.provider, "positions_synced": result.positions_synced, "balances_synced": result.balances_synced},
                    "route": "/?module=settings&tab=data",
                    "next_steps": ["检查 quality report。", "再运行账本同步与对账。"],
                }
            return self._manual_data_task(
                dataset_type=dataset_type,
                route="/?module=settings&tab=data&setup=read_only",
                steps=[
                    "配置 Binance Spot read-only 或其他只读账户连接。",
                    "只保存 secret reference，不保存明文 key。",
                    "完成权限截图、提现关闭证明和只读 preflight 后再同步。",
                ],
            )
        if dataset_type.startswith("csv_"):
            return self._manual_data_task(
                dataset_type=dataset_type,
                route="/?module=settings&tab=data&setup=csv",
                steps=[
                    "导入 CSV statement 或持仓文件。",
                    "确认字段映射、币种和账户标签。",
                    "导入后运行账本对账，再回到 Today Queue。",
                ],
            )
        return self._manual_data_task(
            dataset_type=dataset_type,
            route="/?module=settings&tab=data",
            steps=["选择一个只读数据源。", "完成同步或导入。", "查看质量报告后再用于决策。"],
        )

    def _default_market_connection(self) -> DataSourceConnection:
        DataSourceService(self.db).ensure_default_connections()
        connection = self.db.scalar(
            select(DataSourceConnection)
            .where(DataSourceConnection.provider == "mock_market_data")
            .order_by(DataSourceConnection.created_at.desc(), DataSourceConnection.id.desc())
            .limit(1)
        )
        if connection is None:
            raise DailyUseError("local mock market data connection is not available")
        return connection

    def _syncable_account_connection(self) -> DataSourceConnection | None:
        connections = list(
            self.db.scalars(
                select(DataSourceConnection)
                .where(DataSourceConnection.provider.in_(["binance_spot_readonly", "ibkr_readonly", "futu_readonly", "cex_readonly", "wallet_readonly"]))
                .order_by(DataSourceConnection.updated_at.desc(), DataSourceConnection.id.desc())
            ).all()
        )
        for connection in connections:
            config = connection.config_json or {}
            has_sample = isinstance(config.get("sample_snapshot"), dict) and bool(config.get("sample_snapshot"))
            if connection.provider == "binance_spot_readonly" and connection.credentials_ref:
                return connection
            if has_sample:
                return connection
        return None

    def _focus_symbols(self, *, user_id: str) -> list[str]:
        symbols: list[str] = []
        for item in self.list_watchlist(user_id=user_id, active_only=True, limit=20):
            symbols.append(item.symbol)
        positions = list(self.db.scalars(self._workspace_position_statement(user_id=user_id).order_by(Position.updated_at.desc(), Position.id.desc()).limit(50)).all())
        asset_ids = {item.asset_id for item in positions if item.asset_id}
        if asset_ids:
            for asset in self.db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all():
                if asset.asset_type != "cash":
                    symbols.append(asset.symbol)
        fallback = ["AAPL", "NVDA", "MSFT", "TSLA", "QQQ", "SPY", "BTC", "ETH", "SOL", "GLD", "VIX"]
        normalized = []
        for symbol in symbols + fallback:
            clean = str(symbol).upper().strip()
            if clean and clean not in normalized:
                normalized.append(clean)
        return normalized[:12]

    def _persist_simulated_external_dataset(self, *, dataset_type: str, symbols: list[str]) -> dict[str, Any]:
        fetched_at = datetime.now(timezone.utc)
        if dataset_type == "fx_rates":
            data = {
                "base_currency": "USD",
                "provider": "local_simulation",
                "rates": {
                    "USD": {"to_usd": 1.0, "date": fetched_at.date().isoformat()},
                    "CNY": {"to_usd": 0.138, "date": fetched_at.date().isoformat()},
                    "HKD": {"to_usd": 0.128, "date": fetched_at.date().isoformat()},
                    "EUR": {"to_usd": 1.08, "date": fetched_at.date().isoformat()},
                    "JPY": {"to_usd": 0.0064, "date": fetched_at.date().isoformat()},
                },
            }
            label = "汇率"
            source = "local_simulated_fx"
            row_count = len(data["rates"])
        else:
            data = {
                "provider": "local_simulation",
                "events": [
                    {"symbol": symbol, "action_type": "cash_dividend", "ex_date": fetched_at.date().isoformat(), "amount_per_share": 0.0, "currency": "USD", "simulation_only": True}
                    for symbol in symbols[:5]
                    if symbol not in {"BTC", "ETH", "SOL", "USDC", "VIX", "DXY", "US10Y"}
                ],
            }
            label = "公司行动"
            source = "local_simulated_corporate_actions"
            row_count = len(data["events"])
        snapshot = DataSnapshot(
            snapshot_type=dataset_type,
            as_of=fetched_at,
            data_json=data,
            metadata_json={"provider": source, "read_only": True, "simulation_only": True, "execution_available": False},
        )
        self.db.add(snapshot)
        self.db.flush()
        quality_report = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source=source,
            metric_type=f"{dataset_type}_simulation_quality",
            score=1.0,
            details_json={"rows_received": row_count, "simulation_only": True, "read_only": True, "execution_available": False},
        )
        self.db.add(quality_report)
        self.db.flush()
        catalog = DataCatalogService(self.db).create_entry(
            dataset_type=dataset_type,
            source=source,
            source_ref="local_simulation",
            row_count=row_count,
            snapshot=snapshot,
            quality_report=quality_report,
            usable_for_trading=False,
            lineage_json={"fetched_at": fetched_at.isoformat(), "simulation_only": True},
            contract_json={"mode": "simulation", "read_only": True, "execution_available": False},
        )
        self._audit("daily_use.simulated_dataset_refreshed", "DataSnapshot", snapshot.id, {"dataset_type": dataset_type, "catalog_entry_id": catalog.id})
        self.db.commit()
        return {
            "status": "completed",
            "message": f"已生成本地模拟{label}证据包。",
            "snapshot_id": snapshot.id,
            "quality_report_id": quality_report.id,
            "catalog_entry_id": catalog.id,
            "summary": {"source": source, "row_count": row_count, "simulation_only": True},
            "route": "/?module=settings&tab=data",
            "next_steps": ["这是本地模拟证据，后续接真实只读源后需要重新生成真实 evidence packet。"],
        }

    @staticmethod
    def _manual_data_task(*, dataset_type: str, route: str, steps: list[str]) -> dict[str, Any]:
        return {
            "status": "manual_required",
            "message": f"{dataset_display_label(dataset_type)}需要你提供只读数据或文件后才能完成。",
            "route": route,
            "next_steps": steps,
        }

    def _asset_for(self, *, symbol: str, asset_id: str | None) -> Asset | None:
        if asset_id:
            asset = self.db.get(Asset, asset_id)
            if asset is not None:
                return asset
        return self.db.scalar(select(Asset).where(Asset.symbol == symbol).order_by(Asset.updated_at.desc(), Asset.id.desc()).limit(1))

    def _watchlist_item(self, item_id: str) -> WatchlistItem:
        item = self.db.get(WatchlistItem, item_id)
        if item is None:
            raise DailyUseError("watchlist item not found")
        return item

    def _reminder(self, reminder_id: str) -> Reminder:
        reminder = self.db.get(Reminder, reminder_id)
        if reminder is None:
            raise DailyUseError("reminder not found")
        return reminder

    def _export_payload(self, *, user_id: str, export_type: str, sections: list[str]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if "watchlist" in sections:
            data["watchlist"] = [watchlist_payload(item) for item in self.list_watchlist(user_id=user_id, active_only=False, limit=500)]
        if "reminders" in sections:
            data["reminders"] = [reminder_payload(item) for item in self.list_reminders(user_id=user_id, limit=500)]
        if "local_config" in sections:
            data["local_config"] = [config_payload(item) for item in self.list_local_config(user_id=user_id)]
        if "scheduled_jobs" in sections:
            data["scheduled_jobs"] = [scheduled_job_payload(item) for item in self.db.scalars(select(ScheduledJob).order_by(ScheduledJob.created_at.desc())).all()]
        if "data_sources" in sections:
            data["data_sources"] = [data_source_payload(item) for item in self.db.scalars(select(DataSourceConnection).order_by(DataSourceConnection.created_at.desc())).all()]
        if "theses" in sections:
            data["theses"] = [thesis_payload(item) for item in self.db.scalars(select(InvestmentThesis).order_by(InvestmentThesis.updated_at.desc())).all()]
        if "order_drafts" in sections:
            data["order_drafts"] = [order_draft_payload(item) for item in self.db.scalars(select(OrderDraft).order_by(OrderDraft.created_at.desc()).limit(200)).all()]
        if "reviews" in sections:
            data["reviews"] = [review_payload(item) for item in self.db.scalars(select(PostTradeReview).order_by(PostTradeReview.updated_at.desc()).limit(200)).all()]
        if "playbook_proposals" in sections:
            data["playbook_proposals"] = [proposal_payload(item) for item in self.db.scalars(select(PlaybookUpdateProposal).order_by(PlaybookUpdateProposal.updated_at.desc()).limit(200)).all()]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "export_type": export_type,
            "safe_mode": "read_only_local_export",
            "execution_available": False,
            "sections": data,
        }

    def _audit(self, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        write_audit_log(
            self.db,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json,
            actor_id="phase4-daily-use-service",
        )

    def _count(self, query: Any) -> int:
        value = self.db.scalar(query)
        return int(value or 0)

    def _investment_discipline_status(self, *, user_id: str = "default-user") -> dict[str, Any]:
        constitution = self.db.scalar(
            select(InvestmentConstitution)
            .where(InvestmentConstitution.user_id == user_id, InvestmentConstitution.is_active.is_(True))
            .order_by(InvestmentConstitution.updated_at.desc(), InvestmentConstitution.id.desc())
            .limit(1)
        )
        if constitution is None:
            return {
                "status": "missing_constitution",
                "label": "缺投资纪律",
                "detail": "还没有生效中的投资纪律；计划无法通过风险闸门。",
                "constitution_id": None,
                "budget_asset_classes": [],
                "execution_available": False,
            }
        budgets = list(self.db.scalars(
            select(RiskBudget)
            .where(RiskBudget.user_id == user_id, RiskBudget.constitution_id == constitution.id)
            .order_by(RiskBudget.asset_class.asc(), RiskBudget.id.asc())
        ).all())
        budget_asset_classes = sorted({str(item.asset_class) for item in budgets})
        has_budget = any(asset_class in budget_asset_classes for asset_class in ["stock", "equity"]) and "crypto" in budget_asset_classes
        return {
            "status": "ready" if has_budget else "missing_risk_budget",
            "label": "投资纪律已就绪" if has_budget else "缺风险预算",
            "detail": (
                "生效投资纪律和基础风险预算已就绪。"
                if has_budget
                else "已有投资纪律，但缺少基础 stock/equity/crypto 风险预算。"
            ),
            "constitution_id": constitution.id,
            "budget_asset_classes": budget_asset_classes,
            "execution_available": False,
        }

    def _pending_due_reminders(self, *, user_id: str, now: datetime, limit: int) -> list[Reminder]:
        reminders = self.list_reminders(user_id=user_id, limit=max(limit, 1000))
        due_reminders = [
            reminder
            for reminder in reminders
            if reminder.status in {"pending", "snoozed"}
            and reminder.due_at is not None
            and queue_time(reminder.due_at, now) <= now
            and not is_e2e_artifact(reminder.title)
        ]
        due_reminders.sort(
            key=lambda reminder: (
                queue_time(reminder.due_at, now),
                priority_rank(normalize_priority(reminder.priority)),
                reminder.id,
            )
        )
        return due_reminders[:limit]

    def _high_priority_watchlist(self, *, user_id: str, limit: int) -> list[WatchlistItem]:
        items = self.list_watchlist(user_id=user_id, active_only=False, limit=max(limit, 1000))
        high_priority = [
            item
            for item in items
            if item.is_active is not False and normalize_priority(item.priority) == "high"
        ]
        high_priority.sort(key=lambda item: (item.symbol, item.created_at, item.id))
        return high_priority[:limit]

    def _portfolio_risk_actions(self, *, user_id: str) -> list[dict[str, Any]]:
        positions = list(self.db.scalars(self._workspace_position_statement(user_id=user_id).order_by(Position.updated_at.desc(), Position.id.desc()).limit(500)).all())
        total_value = sum(float(item.market_value or 0) for item in positions)
        if total_value <= 0:
            return []
        asset_ids = {item.asset_id for item in positions if item.asset_id}
        assets = {item.id: item for item in self.db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()} if asset_ids else {}
        actions: list[dict[str, Any]] = []
        for position in positions:
            value = float(position.market_value or 0)
            stored_weight = float(position.weight or 0)
            weight = stored_weight if stored_weight > 0 else value / total_value
            asset = assets.get(position.asset_id)
            if asset is not None and asset.asset_type == "cash":
                continue
            if weight < 0.25:
                continue
            symbol = asset.symbol if asset else position.asset_id
            actions.append(
                {
                    "id": f"risk:concentration:{position.id}",
                    "action_type": "review_portfolio_risk",
                    "priority": "high" if weight >= 0.35 else "normal",
                    "title": f"复查集中度风险：{symbol}",
                    "detail": f"{symbol} 占当前组合市值的 {weight:.1%}。",
                    "status": "open",
                    "source": "portfolio_risk",
                    "related_entity_type": "Position",
                    "related_entity_id": position.id,
                    "due_at": None,
                    "created_at": position.updated_at,
                    "next_action": "打开风险详情，检查 Thesis 与账本证据，并记录人工复核结论。",
                    "execution_available": False,
                }
            )
        return actions

    def _thesis_coverage_actions(self, *, user_id: str) -> list[dict[str, Any]]:
        positions = list(self.db.scalars(self._workspace_position_statement(user_id=user_id).order_by(Position.updated_at.desc(), Position.id.desc()).limit(500)).all())
        total_value = sum(float(item.market_value or 0) for item in positions)
        if total_value <= 0:
            return []
        asset_ids = {item.asset_id for item in positions if item.asset_id}
        assets = {item.id: item for item in self.db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()} if asset_ids else {}
        active_thesis_asset_ids = set(
            self.db.scalars(
                select(InvestmentThesis.asset_id).where(
                    InvestmentThesis.asset_id.in_(asset_ids),
                    InvestmentThesis.status.in_(["active", "monitoring"]),
                )
            ).all()
        ) if asset_ids else set()
        actions: list[dict[str, Any]] = []
        seen_assets: set[str] = set()
        for position in sorted(positions, key=lambda item: float(item.market_value or 0), reverse=True):
            if not position.asset_id or position.asset_id in seen_assets or position.asset_id in active_thesis_asset_ids:
                continue
            asset = assets.get(position.asset_id)
            if asset is not None and asset.asset_type == "cash":
                continue
            seen_assets.add(position.asset_id)
            value = float(position.market_value or 0)
            weight = value / total_value if total_value else 0.0
            symbol = asset.symbol if asset else position.asset_id
            actions.append(
                {
                    "id": f"thesis:missing:{position.id}",
                    "action_type": "create_holding_thesis",
                    "priority": "high" if weight >= 0.15 else "normal",
                    "title": f"为 {symbol} 补充 Thesis",
                    "detail": f"{symbol} 有持仓但没有有效 Thesis，暂不应推进到交易计划。",
                    "status": "open",
                    "source": "thesis_coverage",
                    "related_entity_type": "Position",
                    "related_entity_id": position.id,
                    "related_asset_id": position.asset_id,
                    "related_symbol": symbol,
                    "due_at": None,
                    "created_at": position.updated_at,
                    "next_action": "打开持仓页，写下持有理由、失效条件和复查依据。",
                    "execution_available": False,
                }
            )
            if len(actions) >= 5:
                break
        return actions

    def _local_start_setup_tasks(self, *, user_id: str, state: dict[str, Any], demo_seeded: bool) -> list[dict[str, Any]]:
        if not bool(state.get("initialized")):
            return [
                {
                    "id": "local_start:choose_data_mode",
                    "action_type": "complete_local_start",
                    "title": "完成首次启动",
                    "detail": "先选择模拟数据、CSV 或真实只读账户，确认安全边界后进入 Today Queue。",
                    "route": "/?module=settings&tab=preferences",
                    "action_label": "开始设置",
                    "next_action": "完成本地首次启动，然后处理 Today Queue 的第一项。",
                    "guidance_steps": ["选择数据模式", "确认不会自动实盘或提现", "进入 Today Queue"],
                }
            ]
        data_mode = str(state.get("data_mode") or "")
        if data_mode == "simulation":
            if demo_seeded:
                return []
            return [
                {
                    "id": "local_start:simulation_seed",
                    "action_type": "initialize_simulation_data",
                    "title": "生成模拟数据",
                    "detail": "模拟模式已选择，但样例持仓和 Thesis 尚未生成。",
                    "route": "/?module=settings&tab=preferences",
                    "action_label": "生成模拟数据",
                    "next_action": "重新运行一键初始化模拟数据，然后进入 Today Queue。",
                    "guidance_steps": ["生成样例持仓", "检查 Today Queue", "从 Thesis 和风险开始练习"],
                }
            ]
        if data_mode == "csv":
            imported_count = self._count(
                select(func.count()).select_from(DataCatalogEntry).where(
                    DataCatalogEntry.dataset_type.in_(["csv_holdings", "csv_crypto_holdings", "csv_wallet_balances", "csv_trades", "broker_statement", "broker_statement_import"])
                )
            )
            if imported_count > 0:
                return []
            return [
                {
                    "id": "local_start:csv_import",
                    "action_type": "configure_csv_data",
                    "title": "导入第一份 CSV 数据",
                    "detail": "CSV 模式已初始化，但还没有导入 statement 或持仓文件。",
                    "route": "/?module=settings&tab=data&setup=csv",
                    "action_label": "导入 CSV",
                    "next_action": "打开数据页，导入只读 statement 或持仓 CSV，并查看质量报告。",
                    "guidance_steps": ["准备 CSV 文件", "导入并确认字段映射", "查看质量报告后回 Today Queue"],
                }
            ]
        if data_mode == "read_only":
            connection = self._syncable_account_connection()
            if connection is None:
                return [
                    {
                        "id": "local_start:read_only_setup",
                        "action_type": "configure_read_only_account",
                        "title": "配置真实只读账户",
                        "detail": "真实只读模式已初始化，但还没有可同步的 Secret Reference 或样例快照。",
                        "route": "/?module=settings&tab=data&setup=read_only",
                        "action_label": "配置只读账户",
                        "next_action": "配置 read-only Secret Reference，确认提现关闭证明，再生成证据包。",
                        "guidance_steps": ["准备只读 Key 和提现关闭证明", "只保存 Secret Reference", "运行只读 preflight 和快照同步"],
                    }
                ]
            if connection.provider != "binance_spot_readonly":
                return []
            evidence = self._binance_readonly_evidence_state(user_id=user_id)
            if not evidence["preflight_ready"]:
                return [
                    {
                        "id": "local_start:binance_evidence_preflight",
                        "action_type": "prepare_binance_readonly_evidence",
                        "title": "生成 Binance 只读证据包",
                        "detail": "已保存 Binance Secret Reference，但还缺权限截图、提现关闭证明和预检包。",
                        "route": "/?module=settings&tab=data&setup=read_only",
                        "action_label": "生成证据包",
                        "next_action": "上传脱敏权限截图引用和提现关闭证明引用，生成 Binance 只读预检包。",
                        "guidance_steps": ["确认 Key 只有只读权限", "填写权限截图和提现关闭证明引用", "生成并下载预检包"],
                        "evidence_status": evidence,
                    }
                ]
            if not evidence["snapshot_ready"] or not evidence["quality_report_ready"]:
                missing = []
                if not evidence["snapshot_ready"]:
                    missing.append("真实只读 snapshot")
                if not evidence["quality_report_ready"]:
                    missing.append("quality report")
                return [
                    {
                        "id": "local_start:binance_private_sync",
                        "action_type": "run_binance_private_readonly_sync",
                        "title": "运行 Binance 私有只读同步",
                        "detail": f"预检包已完成，还缺 {'、'.join(missing)}。这一步只读取账户快照，不会下单或提现。",
                        "route": "/?module=settings&tab=data&setup=read_only",
                        "action_label": "查看私有同步步骤",
                        "next_action": "在私有环境运行只读同步，保存 snapshot、quality report 和 audit packet。",
                        "guidance_steps": ["确认提现关闭证明仍有效", "运行只读账户同步", "核对 snapshot 和 quality report 后回 Today Queue"],
                        "evidence_status": evidence,
                    }
                ]
            return []
        return []

    def _binance_readonly_evidence_state(self, *, user_id: str) -> dict[str, Any]:
        preflight = self.db.scalar(
            select(ExportArtifact)
            .where(
                ExportArtifact.user_id == user_id,
                ExportArtifact.export_type == "binance_readonly_evidence_preflight",
            )
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        preflight_payload = preflight.payload_json if preflight is not None else {}
        preflight_ready = (
            preflight is not None
            and preflight.status == "ready"
            and preflight_payload.get("provider") == "binance_spot_readonly"
            and preflight_payload.get("status") == "preflight_ready"
        )

        snapshots = list(
            self.db.scalars(
                select(DataSnapshot)
                .where(DataSnapshot.snapshot_type == "read_only_account")
                .order_by(DataSnapshot.created_at.desc(), DataSnapshot.id.desc())
                .limit(25)
            ).all()
        )
        snapshot = next((item for item in snapshots if (item.data_json or {}).get("provider") == "binance_spot_readonly"), None)
        quality = None
        if snapshot is not None:
            quality = self.db.scalar(
                select(DataQualityReport)
                .where(
                    DataQualityReport.source == "binance_spot_readonly",
                    DataQualityReport.data_snapshot_id == snapshot.id,
                )
                .order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc())
                .limit(1)
            )

        return {
            "preflight_ready": preflight_ready,
            "preflight_artifact_id": preflight.id if preflight is not None else None,
            "snapshot_ready": snapshot is not None,
            "snapshot_id": snapshot.id if snapshot is not None else None,
            "quality_report_ready": quality is not None,
            "quality_report_id": quality.id if quality is not None else None,
            "execution_available": False,
        }


def sections_for_export(export_type: str) -> list[str]:
    if export_type == "watchlist":
        return ["watchlist", "reminders"]
    if export_type == "reviews":
        return ["reviews", "playbook_proposals", "order_drafts"]
    if export_type == "local_backup_manifest":
        return DEFAULT_EXPORT_SECTIONS
    return DEFAULT_EXPORT_SECTIONS


def onboarding_next_actions(missing: list[str]) -> list[str]:
    mapping = {
        "workspace_goal": "Define the founder workspace goal for the next 7 days.",
        "risk_boundary_acknowledged": "Acknowledge the read-only/no-live-execution boundary.",
        "read_only_data_plan": "Pick the first authenticated read-only data source to verify privately.",
        "investment_discipline": "Create a conservative investment discipline and base risk budgets.",
        "daily_review_time": "Set the daily open/close review cadence.",
        "first_daily_open": "Complete the first daily open and review the Today Queue.",
    }
    return [mapping[key] for key in missing] or ["Open the today action queue and complete one read-only review item."]


def onboarding_step_details(completed: list[str]) -> list[dict[str, Any]]:
    completed_set = set(completed)
    steps = [
        {
            "key": "workspace_goal",
            "label": "工作目标",
            "detail": "确认这个工作台先服务你的每日投资检查，而不是自动交易。",
            "route": "/?module=settings",
            "action_label": "填写目标",
        },
        {
            "key": "risk_boundary_acknowledged",
            "label": "安全边界",
            "detail": "确认禁止自动实盘、wallet signing、提现、DEX swap、自动审批和绕过 gates。",
            "route": "/?module=settings",
            "action_label": "确认边界",
        },
        {
            "key": "read_only_data_plan",
            "label": "数据模式",
            "detail": "选择模拟、CSV 或真实只读数据，真实只读只保存 Secret Reference。",
            "route": "/?module=settings&tab=data",
            "action_label": "选择数据",
        },
        {
            "key": "investment_discipline",
            "label": "投资纪律",
            "detail": "建立保守默认纪律和基础风险预算，后续计划才能进入五道闸门。",
            "route": "/?module=investment_logic&tab=constitution",
            "action_label": "建立纪律",
        },
        {
            "key": "daily_review_time",
            "label": "每日复盘时间",
            "detail": "设置每天开盘检查和收盘复盘的节奏。",
            "route": "/?module=settings&tab=preferences",
            "action_label": "设置时间",
        },
        {
            "key": "first_daily_open",
            "label": "首次开盘检查",
            "detail": "生成第一份 daily open packet，并进入 Today Queue。",
            "route": "/?module=overview&focus=today_queue",
            "action_label": "打开队列",
        },
    ]
    return [
        {
            **step,
            "status": "ready" if step["key"] in completed_set else "action_required",
        }
        for step in steps
    ]


VERIFIED_SCHEDULER_STATUSES = {"succeeded", "scheduled", "open", "closed", "awaiting_human_approved_provider"}


def scheduler_health_status(jobs: list[ScheduledJob], *, now: datetime) -> dict[str, Any]:
    active_jobs = [job for job in jobs if job.status == "active"]
    stale_after = timedelta(hours=36)
    if not active_jobs:
        return {
            "status": "not_configured",
            "label": "待设置",
            "detail": "还没有本地自动提醒任务，请先完成首次启动。",
            "verified_jobs": 0,
            "stale_after_hours": int(stale_after.total_seconds() // 3600),
        }

    def recent_verified(job: ScheduledJob) -> bool:
        if job.last_run_at is None or str(job.last_run_status or "") not in VERIFIED_SCHEDULER_STATUSES:
            return False
        last_run = job.last_run_at.replace(tzinfo=timezone.utc) if job.last_run_at.tzinfo is None else job.last_run_at
        return now - last_run <= stale_after

    verified_jobs = sum(1 for job in active_jobs if recent_verified(job))
    latest_run = max((job.last_run_at for job in active_jobs if job.last_run_at is not None), default=None)
    failed_latest = any(
        job.last_run_at == latest_run and str(job.last_run_status or "") == "failed"
        for job in active_jobs
        if latest_run is not None
    )
    if latest_run is None:
        return {
            "status": "needs_verification",
            "label": "需验证",
            "detail": f"{len(active_jobs)} 个本地调度任务已配置，但还没有运行证据。",
            "verified_jobs": verified_jobs,
            "stale_after_hours": int(stale_after.total_seconds() // 3600),
        }
    if latest_run.tzinfo is None:
        latest_run = latest_run.replace(tzinfo=timezone.utc)
    age = now - latest_run
    if failed_latest:
        return {
            "status": "failed",
            "label": "运行失败",
            "detail": "最近一次自动提醒调度失败，请重新验证调度运行。",
            "verified_jobs": verified_jobs,
            "stale_after_hours": int(stale_after.total_seconds() // 3600),
        }
    if age > stale_after:
        return {
            "status": "stale",
            "label": "需复验",
            "detail": f"最近一次调度运行已超过 {int(stale_after.total_seconds() // 3600)} 小时，请重新验证。",
            "verified_jobs": verified_jobs,
            "stale_after_hours": int(stale_after.total_seconds() // 3600),
        }
    return {
        "status": "verified",
        "label": "已验证",
        "detail": f"{verified_jobs}/{len(active_jobs)} 个本地调度任务有最近运行证据。",
        "verified_jobs": verified_jobs,
        "stale_after_hours": int(stale_after.total_seconds() // 3600),
    }


def serializable_packet(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: serializable_packet(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serializable_packet(item) for item in value]
    return value


def db_order(query: Any, model: Any) -> Any:
    return query.order_by(model.created_at.desc(), model.id.desc())


def is_older_than(value: datetime, *, now: datetime, delta: timedelta) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < now - delta


def normalize_priority(value: str | None) -> str:
    return value if value in {"low", "normal", "high"} else "normal"


def priority_rank(value: str) -> int:
    return {"high": 0, "normal": 1, "low": 2}.get(value, 1)


def source_rank(value: str) -> int:
    return {"local_start": 0, "portfolio_risk": 1, "thesis_coverage": 2, "data_freshness": 3}.get(value, 4)


def queue_time(value: datetime | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def present_queue_action(item: dict[str, Any]) -> dict[str, Any]:
    source = str(item.get("source") or "")
    action_type = str(item.get("action_type") or "")
    if source == "portfolio_risk":
        route = f"/?module=risk&queue_item={item['id']}"
        action_label = "审查风险"
        steps = ["查看异常仓位和时序证据", "确认风险来源及影响", "记录人工处理结论"]
    elif source == "data_freshness":
        route = f"/?module=settings&tab=data&queue_item={item['id']}"
        action_label = "更新数据"
        steps = ["确认缺失或过期的数据集", "运行只读同步或导入", "检查质量报告后返回队列"]
    elif source == "backup" or action_type == "create_backup_manifest":
        route = f"/?module=settings&tab=data&queue_item={item['id']}"
        action_label = "创建备份"
        steps = ["生成本地只读导出", "检查导出清单", "返回队列标记完成"]
    elif source == "watchlist":
        route = f"/?module=investment_logic&tab=thesis&queue_item={item['id']}"
        action_label = "复查 Thesis"
        steps = ["检查最新证据与原始理由", "更新失效条件和置信度", "需要行动时再生成计划"]
    elif source == "thesis_coverage":
        asset_ref = item.get("related_asset_id") or item.get("related_symbol") or ""
        route = f"/?module=holdings&asset={asset_ref}&create_thesis=1&queue_item={item['id']}"
        action_label = "补 Thesis"
        steps = ["打开对应持仓", "写下为什么持有和什么情况失效", "创建 Thesis 后再生成计划并做风险预检"]
    elif source == "local_start":
        route = str(item.get("route") or "/?module=settings&tab=preferences")
        action_label = str(item.get("action_label") or "继续设置")
        raw_steps = item.get("guidance_steps")
        steps = list(raw_steps) if isinstance(raw_steps, list) and raw_steps else ["打开本地启动设置", "完成缺失配置", "回到 Today Queue"]
    elif action_type == "complete_reminder":
        route = f"/?module=overview&focus=today_queue&queue_item={item['id']}"
        action_label = "处理提醒"
        steps = ["查看提醒上下文", "完成相关只读检查", "标记完成或延期"]
    else:
        route = f"/?module=overview&focus=today_queue&queue_item={item['id']}"
        action_label = "开始处理"
        steps = ["查看任务依据", "完成建议动作", "返回队列记录结果"]
    return {**item, "route": route, "action_label": action_label, "guidance_steps": steps}


def queue_action_message(*, action: str, has_next: bool) -> str:
    labels = {
        "complete": "任务已完成",
        "snooze": "任务已延期",
        "dismiss": "任务已忽略",
        "assign": "任务已分派给你",
    }
    suffix = "，已为你打开下一项。" if has_next else "，今日队列已清空。"
    return f"{labels[action]}{suffix}"


def local_data_detail(*, data_mode: str | None, freshness: dict[str, Any]) -> str:
    if data_mode == "simulation":
        return "模拟数据已就绪"
    mode_label = "CSV 数据" if data_mode == "csv" else "只读数据"
    if freshness["overall_status"] == "ok":
        return f"{mode_label}正常"
    issue_count = freshness["stale_count"] + freshness["missing_count"] + freshness["blocked_count"]
    return f"{mode_label}有 {issue_count} 项待处理"


def freshness_status_label(status: str) -> str:
    return {
        "missing": "缺少数据",
        "stale": "数据已过期",
        "blocked": "同步受阻",
        "fresh": "正常",
    }.get(status, status)


def dataset_display_label(dataset_type: str, *, fallback: str | None = None) -> str:
    labels = {
        "market_quotes": "行情报价",
        "market_candles": "K 线数据",
        "read_only_account": "只读账户快照",
        "fx_rates": "汇率数据",
        "corporate_actions": "公司行动",
        "csv_holdings": "CSV 持仓",
        "csv_crypto_holdings": "CSV 加密资产持仓",
        "csv_wallet_balances": "CSV 钱包余额",
        "csv_trades": "CSV 交易记录",
        "broker_statement": "券商 Statement",
        "broker_statement_import": "券商 Statement 导入",
        "demo_low_quality_market_quotes": "演示低质量行情样本",
    }
    if dataset_type in labels:
        return labels[dataset_type]
    return (fallback or dataset_type.replace("_", " ")).strip()


def watchlist_payload(item: WatchlistItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "asset_id": item.asset_id,
        "investment_thesis_id": item.investment_thesis_id,
        "name": item.name,
        "asset_type": item.asset_type,
        "market": item.market,
        "priority": item.priority,
        "alert_rules_json": item.alert_rules_json,
        "notes": item.notes,
        "is_active": item.is_active,
        "updated_at": item.updated_at.isoformat(),
    }


def position_payload(item: Position) -> dict[str, Any]:
    return {
        "id": item.id,
        "account_id": item.account_id,
        "asset_id": item.asset_id,
        "quantity": float(item.quantity),
        "average_cost": float(item.average_cost),
        "market_price": float(item.market_price),
        "market_value": float(item.market_value),
        "unrealized_pnl": float(item.unrealized_pnl),
        "realized_pnl": float(item.realized_pnl),
        "weight": float(item.weight),
        "updated_at": item.updated_at.isoformat(),
    }


def asset_payload(item: Asset) -> dict[str, Any]:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "name": item.name,
        "asset_type": item.asset_type,
        "market": item.market,
        "venue": item.venue,
        "currency": item.currency,
        "risk_level": item.risk_level,
        "tradable": item.tradable,
        "manual_enabled": item.manual_enabled,
        "auto_enabled": item.auto_enabled,
    }


def reminder_payload(item: Reminder) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "reminder_type": item.reminder_type,
        "related_entity_type": item.related_entity_type,
        "related_entity_id": item.related_entity_id,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "recurrence_json": item.recurrence_json,
        "priority": item.priority,
        "status": item.status,
        "payload_json": item.payload_json,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def config_payload(item: LocalUserConfig) -> dict[str, Any]:
    return {
        "config_key": item.config_key,
        "value_json": item.value_json,
        "description": item.description,
        "updated_at": item.updated_at.isoformat(),
    }


def scheduler_continuity_label(*, runtime_enabled: bool, status: str, active_jobs: int) -> str:
    if not runtime_enabled:
        return "后台循环未启用"
    if active_jobs == 0:
        return "待设置"
    if status == "verified":
        return "持续运行已验证"
    if status == "failed":
        return "最近运行失败"
    if status == "stale":
        return "需要复验"
    return "等待首次验证"


def scheduler_continuity_detail(*, runtime_enabled: bool, poll_seconds: int, health_detail: str) -> str:
    if not runtime_enabled:
        return "本地 runtime scheduler 已关闭；可以手动验证提醒调度，但不会自动轮询到期任务。"
    return f"本地后台每 {poll_seconds} 秒检查一次到期任务。{health_detail}"


def scheduled_job_schedule_label(item: ScheduledJob) -> str:
    job_type = str(item.job_type or "")
    if job_type == "product_daily_open":
        return "每个交易日 08:00 开盘检查"
    if job_type == "product_continuous_reminders":
        return "每 15 分钟刷新提醒"
    if job_type == "product_daily_close":
        return "每个交易日 18:00 收盘复盘"
    if job_type == "product_research_eval":
        return "按需运行研究评估"
    return "本地调度任务"


def next_scheduled_run_at(item: ScheduledJob, *, now: datetime) -> datetime | None:
    if item.status != "active":
        return None
    schedule = item.schedule_json or {}
    cron = str(schedule.get("cron") or "")
    fields = cron.split()
    if len(fields) != 5:
        return None
    minute_field, hour_field, _day, _month, weekday_field = fields
    timezone_name = str(schedule.get("timezone") or "Asia/Shanghai")
    try:
        local_now = now.astimezone(ZoneInfo(timezone_name))
    except Exception:
        local_now = now.astimezone(timezone.utc)
    cursor = local_now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for offset in range(0, 8 * 24 * 60):
        candidate = cursor + timedelta(minutes=offset)
        if (
            scheduler_cron_field_matches(minute_field, candidate.minute)
            and scheduler_cron_field_matches(hour_field, candidate.hour)
            and scheduler_weekday_matches(weekday_field, candidate.weekday())
        ):
            return candidate.astimezone(timezone.utc)
    return None


def scheduler_cron_field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    if field.startswith("*/"):
        try:
            interval = int(field[2:])
        except ValueError:
            return False
        return interval > 0 and value % interval == 0
    try:
        return value == int(field)
    except ValueError:
        return False


def scheduler_weekday_matches(field: str, python_weekday: int) -> bool:
    if field == "*":
        return True
    cron_weekday = (python_weekday + 1) % 7
    if "-" in field:
        try:
            start, end = (int(item) for item in field.split("-", 1))
        except ValueError:
            return False
        return start <= cron_weekday <= end
    try:
        return cron_weekday == int(field) % 7
    except ValueError:
        return False


def scheduled_job_payload(item: ScheduledJob, *, now: datetime | None = None) -> dict[str, Any]:
    observed_at = now or datetime.now(timezone.utc)
    next_run = next_scheduled_run_at(item, now=observed_at)
    return {
        "id": item.id,
        "name": item.name,
        "job_type": item.job_type,
        "status": item.status,
        "schedule_label": scheduled_job_schedule_label(item),
        "schedule_json": item.schedule_json,
        "target_json": item.target_json,
        "last_run_status": item.last_run_status,
        "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
        "next_run_at": next_run.isoformat() if next_run else None,
        "execution_available": False,
    }


def data_source_payload(item: DataSourceConnection) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "provider": item.provider,
        "source_type": item.source_type,
        "mode": item.mode,
        "status": item.status,
        "capabilities_json": item.capabilities_json,
        "last_health_status": item.last_health_status,
        "has_credentials_ref": bool(item.credentials_ref),
        "credentials_ref": "redacted" if item.credentials_ref else None,
    }


def export_payload(item: ExportArtifact) -> dict[str, Any]:
    return {
        "id": item.id,
        "export_type": item.export_type,
        "format": item.format,
        "status": item.status,
        "summary_json": item.summary_json,
        "created_at": item.created_at.isoformat(),
        "execution_available": False,
    }


def thesis_payload(item: InvestmentThesis) -> dict[str, Any]:
    return {
        "id": item.id,
        "asset_id": item.asset_id,
        "strategy_playbook_id": item.strategy_playbook_id,
        "status": item.status,
        "entry_reason": item.entry_reason,
        "key_drivers_json": item.key_drivers_json,
        "invalidation_conditions_json": item.invalidation_conditions_json,
        "expected_horizon": item.expected_horizon,
        "confidence": float(item.confidence),
        "updated_at": item.updated_at.isoformat(),
    }


def order_draft_payload(item: OrderDraft) -> dict[str, Any]:
    return {
        "id": item.id,
        "order_intent_id": item.order_intent_id,
        "risk_status": item.risk_status,
        "behavior_status": item.behavior_status,
        "approval_status": item.approval_status,
        "execution_status": item.execution_status,
        "created_at": item.created_at.isoformat(),
    }


def review_payload(item: PostTradeReview) -> dict[str, Any]:
    return {
        "id": item.id,
        "order_draft_id": item.order_draft_id,
        "status": item.status,
        "prompt_json": item.prompt_json,
        "review_json": item.review_json,
        "updated_at": item.updated_at.isoformat(),
    }


def proposal_payload(item: PlaybookUpdateProposal) -> dict[str, Any]:
    return {
        "id": item.id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "strategy_playbook_id": item.strategy_playbook_id,
        "status": item.status,
        "requires_user_approval": item.requires_user_approval,
        "rationale": item.rationale,
        "updated_at": item.updated_at.isoformat(),
    }


def is_e2e_artifact(title: str | None, payload: dict[str, Any] | None = None) -> bool:
    text = f"{title or ''} {payload or {}}".lower()
    return "e2e" in text or "playwright" in text or "local-self-use" in text
