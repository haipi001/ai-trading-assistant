import csv
import hashlib
import io
import json
from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import Account
from app.models import Asset
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import Execution
from app.models import InvestmentLedgerEntry
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PaperCorporateAction
from app.models import PaperTaxLot
from app.models import Position
from app.models import ReconciliationBreak
from app.models import ReconciliationRun
from app.models import StatementImportBatch
from app.models import WorkflowReviewTask
from app.schemas.core import ReconciliationBreakRead
from app.schemas.core import ReconciliationRunRead
from app.schemas.core import StatementImportBatchRead
from app.schemas.core import contains_secret_config_key
from app.services.data_catalog import DataCatalogService


QUANTITY_TOLERANCE = 0.000001
CASH_TOLERANCE = 0.01


class LedgerImportError(ValueError):
    pass


LEDGER_LOCAL_NEXT_STEPS = [
    {
        "key": "statement_import",
        "label": "导入或下载 Statement",
        "detail": "先通过 CSV 或只读下载源导入 broker/CEX/bank statement，保留 raw snapshot 和 quality report。",
        "action_label": "导入 Statement",
        "route": "/?module=settings&tab=data",
        "execution_available": False,
    },
    {
        "key": "row_detail",
        "label": "查看 skipped rows 与重复项",
        "detail": "逐行查看 raw row、归一化结果、跳过原因、重复 hash 和 row-to-break linking。",
        "action_label": "查看行详情",
        "route": "/?module=settings&tab=settings&admin_maintenance=1&focus=ledger_repair",
        "execution_available": False,
    },
    {
        "key": "repair_assignment",
        "label": "分派并完成修复任务",
        "detail": "把差异或跳过行变成 WorkflowReviewTask，人工分派、完成，并保留审计记录。",
        "action_label": "分派修复",
        "route": "/?module=settings&tab=settings&admin_maintenance=1&focus=ledger_repair",
        "execution_available": False,
    },
    {
        "key": "rerun_reconciliation",
        "label": "重跑对账并晋级数据",
        "detail": "修复后重跑 extended reconciliation，只有通过人工复核的数据才能从 raw 晋级到 reviewed/trusted。",
        "action_label": "重跑对账",
        "route": "/?module=settings&tab=settings&admin_maintenance=1&focus=ledger_repair",
        "execution_available": False,
    },
]


def ledger_local_next_steps(*, batches: int, skipped_rows: int, open_tasks: int, latest_status: str | None) -> list[dict[str, Any]]:
    return [
        {**LEDGER_LOCAL_NEXT_STEPS[0], "status": "ready" if batches > 0 else "action_required"},
        {**LEDGER_LOCAL_NEXT_STEPS[1], "status": "action_required" if skipped_rows > 0 else "ready" if batches > 0 else "blocked"},
        {**LEDGER_LOCAL_NEXT_STEPS[2], "status": "action_required" if open_tasks > 0 else "ready" if skipped_rows == 0 and batches > 0 else "blocked"},
        {**LEDGER_LOCAL_NEXT_STEPS[3], "status": "ready" if latest_status == "ok" else "action_required" if batches > 0 else "blocked"},
    ]


def ledger_promotion_gate(
    *,
    batches: int,
    ledger_entries_count: int,
    latest_status: str | None,
    skipped_rows: int,
    open_tasks: int,
    data_trust_status: str,
) -> dict[str, Any]:
    missing: list[str] = []
    if batches == 0:
        missing.append("statement_import")
    if ledger_entries_count == 0:
        missing.append("normalized_ledger_entries")
    if latest_status is None:
        missing.append("reconciliation_run")
    if skipped_rows > 0:
        missing.append("skipped_rows_review")
    if open_tasks > 0:
        missing.append("open_repair_tasks")
    if data_trust_status == "blocked":
        missing.append("ledger_data_trust")
    reviewed_ready = batches > 0 and ledger_entries_count > 0 and latest_status in {"ok", "warn"} and open_tasks == 0
    trusted_ready = reviewed_ready and latest_status == "ok" and skipped_rows == 0 and data_trust_status == "trusted"
    return {
        "label": "账本数据晋级门槛",
        "status": "trusted_ready" if trusted_ready else "review_ready" if reviewed_ready else "action_required",
        "stages": [
            {"stage": "raw", "status": "ready" if batches > 0 else "missing"},
            {"stage": "reviewed", "status": "ready" if reviewed_ready else "blocked"},
            {"stage": "trusted", "status": "ready" if trusted_ready else "blocked"},
        ],
        "missing_required": dedupe_strings(missing),
        "can_review_ledger": batches > 0,
        "can_promote_to_reviewed": reviewed_ready,
        "can_promote_to_trusted": trusted_ready,
        "can_use_for_risk_context": reviewed_ready,
        "can_unlock_order_approval": False,
        "can_execute_trades": False,
        "execution_available": False,
        "detail": "Ledger repair promotes data trust only. It cannot approve orders, execute trades, sign wallets, withdraw assets, or bypass gates.",
        "next_action": (
            "Import a statement first."
            if batches == 0
            else "Inspect skipped rows, complete repair tasks, and rerun reconciliation."
            if not reviewed_ready
            else "Reviewed ledger data can support manual review; order approval remains locked by separate gates."
        ),
    }


class InvestmentLedgerService:
    def __init__(self, db: Session):
        self.db = db

    def preflight(self, *, user_id: str = "default-user") -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        data_trust_report = self._ledger_trust_report()
        latest = self.latest_reconciliation(user_id=user_id)
        ledger_entries_count = self._count_ledger_entries(user_id=user_id)
        positions_count = self._count_positions()
        paper_executions_count = self._count_paper_executions()
        statement_imports = self.list_statement_imports(user_id=user_id, limit=100)
        skipped_rows = sum(int(item.skipped_count or 0) for item in statement_imports)
        open_repair_tasks = self._count_open_repair_tasks(user_id=user_id)
        latest_status = latest["run"].status if latest else None

        checks: list[dict[str, Any]] = []
        data_trust_status = data_trust_report["overall_status"]
        if data_trust_status == "blocked":
            data_trust_check_status = "block" if positions_count == 0 and paper_executions_count == 0 else "warn"
        elif data_trust_status == "review_only":
            data_trust_check_status = "warn"
        else:
            data_trust_check_status = "ok"
        checks.append(
            {
                "key": "data_trust",
                "label": "Ledger data trust",
                "status": data_trust_check_status,
                "summary": f"Ledger trust report is {data_trust_status}.",
                "details": {
                    "decision_scope": "ledger",
                    "trusted_count": data_trust_report["trusted_count"],
                    "review_only_count": data_trust_report["review_only_count"],
                    "blocked_count": data_trust_report["blocked_count"],
                },
            }
        )
        source_status = "ok" if positions_count or paper_executions_count or data_trust_status != "blocked" else "block"
        checks.append(
            {
                "key": "ledger_sources",
                "label": "Ledger source availability",
                "status": source_status,
                "summary": f"{positions_count} positions and {paper_executions_count} paper executions are available for sync.",
                "details": {
                    "positions_count": positions_count,
                    "paper_executions_count": paper_executions_count,
                    "ledger_entries_count": ledger_entries_count,
                },
            }
        )
        if latest is None:
            reconciliation_status = "warn"
            reconciliation_summary = "No reconciliation run has been recorded yet."
        else:
            run_status = latest["run"].status
            reconciliation_status = "block" if run_status == "block" else "warn" if run_status == "warn" else "ok"
            reconciliation_summary = f"Latest reconciliation is {run_status} with {latest['run'].breaks_count} breaks."
        checks.append(
            {
                "key": "latest_reconciliation",
                "label": "Latest reconciliation",
                "status": reconciliation_status,
                "summary": reconciliation_summary,
                "details": {"has_latest_reconciliation": latest is not None},
            }
        )
        checks.append(
            {
                "key": "safety_boundary",
                "label": "Safety boundary",
                "status": "ok",
                "summary": "Ledger actions remain read-only and cannot route orders, sign wallet transactions, or withdraw assets.",
                "details": {"execution_available": False},
            }
        )

        if any(check["status"] == "block" for check in checks):
            status = "block"
        elif any(check["status"] == "warn" for check in checks):
            status = "warn"
        else:
            status = "ok"

        next_actions = list(data_trust_report["recommended_actions"])
        if ledger_entries_count == 0 and (positions_count or paper_executions_count):
            next_actions.append("Run /ledger/sync to materialize available positions and paper executions into ledger entries.")
        if latest is None:
            next_actions.append("Run /ledger/reconcile after the next ledger sync.")
        elif latest["run"].status != "ok":
            next_actions.append("Inspect reconciliation breaks before using the ledger in review workflows.")

        return {
            "user_id": user_id,
            "status": status,
            "checked_at": checked_at,
            "can_sync": status != "block" or positions_count > 0 or paper_executions_count > 0,
            "can_reconcile": ledger_entries_count > 0,
            "ledger_entries_count": ledger_entries_count,
            "positions_count": positions_count,
            "paper_executions_count": paper_executions_count,
            "data_trust_status": data_trust_status,
            "data_trust_report": data_trust_report,
            "latest_reconciliation": latest,
            "checks": checks,
            "next_actions": next_actions,
            "local_next_steps": ledger_local_next_steps(
                batches=len(statement_imports),
                skipped_rows=skipped_rows,
                open_tasks=open_repair_tasks,
                latest_status=latest_status,
            ),
            "promotion_gate": ledger_promotion_gate(
                batches=len(statement_imports),
                ledger_entries_count=ledger_entries_count,
                latest_status=latest_status,
                skipped_rows=skipped_rows,
                open_tasks=open_repair_tasks,
                data_trust_status=data_trust_status,
            ),
            "execution_available": False,
        }

    def reconciliation_policy(self, *, user_id: str = "default-user") -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        preflight = self.preflight(user_id=user_id)
        latest = self.latest_reconciliation(user_id=user_id)
        ledger_entries_count = self._count_ledger_entries(user_id=user_id)
        tax_lots_count = self._count_tax_lots()
        corporate_actions_count = self._count_corporate_actions()
        latest_breaks = latest["breaks"] if latest else []
        checks = [
            ledger_policy_check(
                "ledger_materialized",
                "Ledger entries",
                "ok" if ledger_entries_count else "block",
                f"{ledger_entries_count} ledger entrie(s) are materialized.",
                blockers=[] if ledger_entries_count else ["ledger_entries_missing"],
                next_actions=[] if ledger_entries_count else ["Run /ledger/sync or import broker statements before reconciliation policy can pass."],
                evidence={"ledger_entries_count": ledger_entries_count},
            ),
            ledger_policy_check(
                "latest_reconciliation",
                "Latest reconciliation",
                reconciliation_policy_status(latest),
                "Latest reconciliation is available." if latest else "No reconciliation run exists.",
                blockers=reconciliation_policy_blockers(latest),
                next_actions=[] if latest and latest["run"].status == "ok" else ["Run /ledger/reconcile/extended and inspect any breaks."],
                evidence={
                    "has_latest_reconciliation": latest is not None,
                    "latest_status": latest["run"].status if latest else None,
                    "breaks_count": latest["run"].breaks_count if latest else 0,
                },
            ),
            ledger_policy_check(
                "cash_policy",
                "Cash ledger policy",
                "ok" if not any(item.break_type.startswith("cash_") and item.severity == "block" for item in latest_breaks) else "block",
                "Cash breaks are evaluated from the latest reconciliation.",
                blockers=[item.break_type for item in latest_breaks if item.break_type.startswith("cash_") and item.severity == "block"],
                next_actions=["Import or refresh cash balance statement rows, then rerun extended reconciliation."]
                if any(item.break_type.startswith("cash_") for item in latest_breaks)
                else [],
                evidence={"cash_breaks": [item.break_type for item in latest_breaks if item.break_type.startswith("cash_")]},
            ),
            ledger_policy_check(
                "tax_lot_policy",
                "Tax lot policy",
                "ok" if tax_lots_count or not latest_breaks else "warn",
                f"{tax_lots_count} paper tax lot(s) are available.",
                next_actions=[] if tax_lots_count else ["Generate tax lots from paper fills or import external tax lot statement rows before tax-sensitive review."],
                evidence={"paper_tax_lots": tax_lots_count},
            ),
            ledger_policy_check(
                "corporate_action_policy",
                "Corporate action policy",
                "ok" if corporate_actions_count or not latest_breaks else "warn",
                f"{corporate_actions_count} corporate action event(s) are available.",
                next_actions=[] if corporate_actions_count else ["Import corporate action rows when broker statements include splits, dividends, or symbol changes."],
                evidence={"paper_corporate_actions": corporate_actions_count},
            ),
            ledger_policy_check(
                "data_trust_policy",
                "Ledger data trust",
                "block" if preflight["data_trust_status"] == "blocked" else "warn" if preflight["data_trust_status"] == "review_only" else "ok",
                f"Ledger data trust is {preflight['data_trust_status']}.",
                blockers=["ledger_data_trust_blocked"] if preflight["data_trust_status"] == "blocked" else [],
                next_actions=preflight["data_trust_report"]["recommended_actions"],
                evidence={"data_trust_status": preflight["data_trust_status"]},
            ),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        if any(check["status"] == "block" for check in checks):
            status = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            status = "review_required"
        else:
            status = "trusted"
        return {
            "user_id": user_id,
            "checked_at": checked_at,
            "policy_status": status,
            "can_promote_to_review": status in {"trusted", "review_required"} and bool(ledger_entries_count),
            "can_unlock_order_approval": False,
            "execution_available": False,
            "blockers": dedupe_strings(blockers),
            "next_actions": dedupe_strings([action for check in checks for action in check["next_actions"]]),
            "preflight_status": preflight["status"],
            "checks": checks,
        }

    def reconciliation_workbench(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        policy = self.reconciliation_policy(user_id=user_id)
        latest = self.latest_reconciliation(user_id=user_id)
        statement_imports = self.list_statement_imports(user_id=user_id, limit=10)
        ledger_entries_count = self._count_ledger_entries(user_id=user_id)
        skipped_rows = sum(int(item.skipped_count or 0) for item in statement_imports)
        open_repair_tasks = self._count_open_repair_tasks(user_id=user_id)
        latest_status = latest["run"].status if latest else None
        break_summary: dict[str, int] = {}
        severity_summary: dict[str, int] = {}
        breaks = latest["breaks"] if latest else []
        for item in breaks:
            break_summary[item.break_type] = break_summary.get(item.break_type, 0) + 1
            severity_summary[item.severity] = severity_summary.get(item.severity, 0) + 1

        work_items = [
            ledger_work_item(
                "statement_import",
                "Statement imports",
                "ok" if statement_imports else "warn",
                f"{len(statement_imports)} recent statement import batch(es).",
                ["Import at least one broker/CEX statement CSV before external beta reconciliation."]
                if not statement_imports
                else [],
            ),
            ledger_work_item(
                "ledger_materialization",
                "Ledger materialization",
                "ok" if ledger_entries_count else "block",
                f"{ledger_entries_count} ledger entrie(s) available.",
                ["Run /ledger/sync or /ledger/statement-imports before reconciliation."] if not ledger_entries_count else [],
            ),
            ledger_work_item(
                "break_resolution",
                "Break resolution",
                "block" if severity_summary.get("block") else "warn" if breaks else "ok",
                f"{len(breaks)} reconciliation break(s) in latest run.",
                ["Resolve blocking reconciliation breaks before using ledger state in review packets."]
                if severity_summary.get("block")
                else [],
            ),
            ledger_work_item(
                "order_unlock_boundary",
                "Order unlock boundary",
                "ok",
                "Ledger workbench can promote data into review, but cannot unlock order approval.",
                [],
            ),
        ]
        blockers = list(policy["blockers"]) + [
            action for item in work_items if item["status"] == "block" for action in item["next_actions"]
        ]
        if any(item["status"] == "block" for item in work_items) or policy["policy_status"] == "blocked":
            status = "blocked"
        elif any(item["status"] == "warn" for item in work_items) or policy["policy_status"] == "review_required":
            status = "review_required"
        else:
            status = "ready_for_review"
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "workbench_status": status,
            "policy_status": policy["policy_status"],
            "latest_reconciliation": self._workbench_reconciliation_report(latest),
            "recent_statement_imports": [self._workbench_statement_import(item) for item in statement_imports],
            "ledger_entries_count": ledger_entries_count,
            "break_summary": break_summary,
            "severity_summary": severity_summary,
            "blockers": dedupe_strings(blockers),
            "next_actions": dedupe_strings(
                list(policy["next_actions"])
                + [action for item in work_items for action in item["next_actions"]]
                + ["Keep ledger reconciliation review-only; order approval remains governed by thesis, gates, risk, behavior, approval, and audit."]
            ),
            "work_items": work_items,
            "local_next_steps": ledger_local_next_steps(
                batches=len(statement_imports),
                skipped_rows=skipped_rows,
                open_tasks=open_repair_tasks,
                latest_status=latest_status,
            ),
            "promotion_gate": ledger_promotion_gate(
                batches=len(statement_imports),
                ledger_entries_count=ledger_entries_count,
                latest_status=latest_status,
                skipped_rows=skipped_rows,
                open_tasks=open_repair_tasks,
                data_trust_status=policy.get("preflight_status") if policy.get("preflight_status") == "block" else self.preflight(user_id=user_id)["data_trust_status"],
            ),
            "can_promote_to_review": policy["can_promote_to_review"],
            "can_unlock_order_approval": False,
            "execution_available": False,
        }

    def statement_normalization_report(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        batches = self.list_statement_imports(user_id=user_id, limit=200)
        entries = list(
            self.db.scalars(
                select(InvestmentLedgerEntry)
                .where(InvestmentLedgerEntry.user_id == user_id, InvestmentLedgerEntry.source_type == "broker_statement")
                .order_by(InvestmentLedgerEntry.occurred_at.desc(), InvestmentLedgerEntry.id.desc())
                .limit(1000)
            ).all()
        )
        entry_type_counts: dict[str, int] = {}
        currency_counts: dict[str, int] = {}
        for entry in entries:
            entry_type_counts[entry.entry_type] = entry_type_counts.get(entry.entry_type, 0) + 1
            currency_counts[entry.currency] = currency_counts.get(entry.currency, 0) + 1
        blockers = []
        if not batches:
            blockers.append("statement_import_missing")
        if batches and not entries:
            blockers.append("normalized_ledger_entries_missing")
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": "blocked" if blockers else "ready_for_review",
            "statement_batches_count": len(batches),
            "normalized_entries_count": len(entries),
            "entry_type_counts": entry_type_counts,
            "currency_counts": currency_counts,
            "recent_batches": [self._workbench_statement_import(item) for item in batches[:10]],
            "blockers": blockers,
            "next_actions": [
                "Import a broker/CEX statement CSV and inspect skipped rows."
            ]
            if "statement_import_missing" in blockers
            else [
                "Run extended reconciliation after normalization.",
                "Inspect skipped rows and duplicate hashes before promoting data.",
            ],
            "execution_available": False,
        }

    def repair_workflow(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        latest = self.latest_reconciliation(user_id=user_id)
        created = 0
        tasks: list[WorkflowReviewTask] = []
        for item in latest["breaks"] if latest else []:
            queue_item_id = f"ledger_break:{item.id}"
            task = self.db.scalar(
                select(WorkflowReviewTask)
                .where(WorkflowReviewTask.user_id == user_id, WorkflowReviewTask.queue_item_id == queue_item_id)
                .limit(1)
            )
            if task is None:
                task = WorkflowReviewTask(
                    user_id=user_id,
                    queue_item_id=queue_item_id,
                    item_type="ledger_repair",
                    title=f"Repair ledger break: {item.break_type}",
                    detail=item.detail,
                    priority="high" if item.severity == "block" else "normal",
                    status="open",
                    related_entity_type="ReconciliationBreak",
                    related_entity_id=item.id,
                    payload_json={
                        "break_type": item.break_type,
                        "severity": item.severity,
                        "expected_quantity": float(item.expected_quantity),
                        "observed_quantity": float(item.observed_quantity),
                        "delta_quantity": float(item.delta_quantity),
                        "expected_cash": float(item.expected_cash),
                        "observed_cash": float(item.observed_cash),
                        "delta_cash": float(item.delta_cash),
                        "metadata_json": item.metadata_json,
                        "execution_available": False,
                    },
                )
                self.db.add(task)
                created += 1
            tasks.append(task)
        if created:
            self.db.flush()
            write_audit_log(
                self.db,
                action="investment_ledger.repair_tasks_created",
                entity_type="WorkflowReviewTask",
                entity_id="ledger_repair_workflow",
                payload_json={"created": created, "execution_available": False},
                actor_id="ledger-service",
            )
            self.db.commit()
        open_tasks = list(
            self.db.scalars(
                select(WorkflowReviewTask)
                .where(WorkflowReviewTask.user_id == user_id, WorkflowReviewTask.item_type == "ledger_repair")
                .order_by(WorkflowReviewTask.created_at.desc(), WorkflowReviewTask.id.desc())
                .limit(100)
            ).all()
        )
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": "ready_for_review" if open_tasks else "no_breaks",
            "latest_reconciliation": self._workbench_reconciliation_report(latest),
            "tasks_created": created,
            "tasks": [workflow_task_payload(task) for task in open_tasks],
            "next_actions": [
                "Assign each repair task, inspect source statement rows, then rerun /ledger/reconcile/extended.",
                "Keep repairs manual and audited; do not auto-correct balances without review.",
            ]
            if open_tasks
            else ["Run /ledger/reconcile/extended after statement import or ledger sync."],
            "execution_available": False,
        }

    def data_promotion_report(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        normalization = self.statement_normalization_report(user_id=user_id)
        policy = self.reconciliation_policy(user_id=user_id)
        latest = self.latest_reconciliation(user_id=user_id)
        raw_ready = normalization["statement_batches_count"] > 0
        reviewed_ready = bool(latest) and latest["run"].status in {"ok", "warn"} and normalization["normalized_entries_count"] > 0
        trusted_ready = policy["policy_status"] == "trusted"
        stages = [
            {
                "stage": "raw",
                "status": "ready" if raw_ready else "missing",
                "evidence": {"statement_batches_count": normalization["statement_batches_count"]},
            },
            {
                "stage": "reviewed",
                "status": "ready" if reviewed_ready else "blocked",
                "evidence": {
                    "latest_reconciliation_status": latest["run"].status if latest else None,
                    "normalized_entries_count": normalization["normalized_entries_count"],
                },
            },
            {
                "stage": "trusted",
                "status": "ready" if trusted_ready else "blocked",
                "evidence": {"policy_status": policy["policy_status"], "blockers": policy["blockers"]},
            },
        ]
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "promotion_status": "trusted" if trusted_ready else "review_required" if reviewed_ready else "raw_or_missing",
            "stages": stages,
            "can_promote_to_review": reviewed_ready,
            "can_promote_to_trusted": trusted_ready,
            "can_unlock_order_approval": False,
            "policy": policy,
            "normalization": normalization,
            "next_actions": dedupe_strings(
                normalization["next_actions"]
                + policy["next_actions"]
                + ["Ledger promotion changes decision trust only; order approval remains locked by separate gates."]
            ),
            "execution_available": False,
        }

    def statement_row_detail(self, *, batch_id: str, row_index: int, user_id: str = "default-user") -> dict[str, Any]:
        batch = self.db.get(StatementImportBatch, batch_id)
        if batch is None or batch.user_id != user_id:
            raise LedgerImportError("statement import batch not found")
        entries = list(
            self.db.scalars(
                select(InvestmentLedgerEntry)
                .where(InvestmentLedgerEntry.user_id == user_id, InvestmentLedgerEntry.source_type == "broker_statement")
                .order_by(InvestmentLedgerEntry.created_at.desc(), InvestmentLedgerEntry.id.desc())
                .limit(1000)
            ).all()
        )
        entry = next(
            (
                item
                for item in entries
                if item.metadata_json.get("statement_import_batch_id") == batch.id
                and int(item.metadata_json.get("row_index") or 0) == row_index
            ),
            None,
        )
        skipped = next(
            (
                item
                for item in (batch.summary_json or {}).get("skipped", [])
                if int(item.get("row") or 0) == row_index
            ),
            None,
        )
        row_hash = None
        if entry is not None:
            row_hash = entry.metadata_json.get("statement_row_hash") or entry.metadata_json.get("source_row_hash")
        if skipped is not None:
            row_hash = row_hash or skipped.get("row_hash")
        duplicate_rows = [
            item
            for item in (batch.summary_json or {}).get("skipped", [])
            if item.get("reason") == "duplicate_statement_row"
        ]
        latest = self.latest_reconciliation(user_id=user_id)
        linked_breaks = []
        for item in latest["breaks"] if latest else []:
            metadata = item.metadata_json or {}
            if metadata.get("statement_import_batch_id") == batch.id and int(metadata.get("row_index") or -1) == row_index:
                linked_breaks.append({"id": item.id, "break_type": item.break_type, "severity": item.severity, "detail": item.detail})
        if entry is None and skipped is None:
            raise LedgerImportError("statement row not found")
        open_repair_tasks = self._count_open_repair_tasks(user_id=user_id)
        skipped_reason = skipped.get("reason") if skipped else None
        return {
            "user_id": user_id,
            "batch": self._workbench_statement_import(batch),
            "row_index": row_index,
            "status": "imported" if entry is not None else "skipped",
            "normalized_entry": ledger_entry_payload(entry) if entry is not None else None,
            "raw_row": entry.metadata_json.get("row") if entry is not None else skipped.get("row_data"),
            "skipped_reason": skipped_reason,
            "row_hash": row_hash,
            "duplicate": bool(skipped and skipped.get("reason") == "duplicate_statement_row"),
            "duplicate_rows_in_batch": len(duplicate_rows),
            "linked_reconciliation_breaks": linked_breaks,
            "repair_suggestions": row_repair_suggestions(
                skipped_reason,
                has_linked_break=bool(linked_breaks),
            ),
            "repair_next_actions": [
                "Compare the raw row with normalized ledger fields.",
                "If the mapping is wrong, import a corrected statement or create a manual repair review task.",
                "Rerun /ledger/repair-workflow/rerun-reconciliation after repair.",
            ],
            "local_next_steps": ledger_local_next_steps(
                batches=1,
                skipped_rows=1 if skipped_reason else 0,
                open_tasks=open_repair_tasks,
                latest_status=latest["run"].status if latest else None,
            ),
            "repair_gate": {
                "status": "needs_repair" if skipped_reason or linked_breaks else "review_ready",
                "can_assign_repair_task": True,
                "can_complete_repair_task": open_repair_tasks > 0,
                "can_rerun_reconciliation": True,
                "can_unlock_order_approval": False,
                "can_execute_trades": False,
                "execution_available": False,
                "detail": "Row repair is manual and auditable. It changes data trust only and cannot approve or execute orders.",
            },
            "execution_available": False,
        }

    def rerun_repair_reconciliation(self, *, user_id: str = "default-user") -> dict[str, Any]:
        report = self.reconcile_extended(user_id=user_id)
        repair = self.repair_workflow(user_id=user_id)
        return {
            "user_id": user_id,
            "status": "reconciliation_rerun",
            "reconciliation": report,
            "repair_workflow": repair,
            "execution_available": False,
        }

    def list_entries(self, *, user_id: str = "default-user", limit: int = 100) -> list[InvestmentLedgerEntry]:
        return list(
            self.db.scalars(
                select(InvestmentLedgerEntry)
                .where(InvestmentLedgerEntry.user_id == user_id)
                .order_by(InvestmentLedgerEntry.occurred_at.desc(), InvestmentLedgerEntry.id.desc())
                .limit(limit)
            ).all()
        )

    def list_statement_imports(self, *, user_id: str = "default-user", limit: int = 50) -> list[StatementImportBatch]:
        return list(
            self.db.scalars(
                select(StatementImportBatch)
                .where(StatementImportBatch.user_id == user_id)
                .order_by(StatementImportBatch.created_at.desc(), StatementImportBatch.id.desc())
                .limit(limit)
            ).all()
        )

    def import_statement(
        self,
        *,
        user_id: str,
        provider: str,
        account_label: str | None,
        statement_type: str,
        source_ref: str | None,
        default_currency: str,
        csv_text: str,
    ) -> dict[str, Any]:
        raw_text = csv_text.strip()
        raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        reader = csv.DictReader(io.StringIO(raw_text))
        if not reader.fieldnames:
            raise LedgerImportError("statement CSV must include a header row")
        normalized_headers = [normalize_key(header) for header in reader.fieldnames]
        if contains_secret_config_key({header: "" for header in normalized_headers}):
            raise LedgerImportError("statement CSV headers must not contain secret-like fields")

        rows = [normalize_row(row) for row in reader]
        batch = StatementImportBatch(
            user_id=user_id,
            provider=provider.strip() or "manual_statement",
            account_label=account_label,
            statement_type=statement_type,
            source_ref=source_ref,
            raw_payload_hash=raw_hash,
            row_count=len(rows),
            imported_count=0,
            skipped_count=0,
            status="importing",
            summary_json={"execution_available": False},
            execution_available=False,
        )
        self.db.add(batch)
        self.db.flush()

        entries: list[InvestmentLedgerEntry] = []
        skipped: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            try:
                entry = self._statement_row_to_entry(
                    batch=batch,
                    row=row,
                    row_index=index,
                    provider=provider,
                    account_label=account_label,
                    default_currency=default_currency,
                )
            except LedgerImportError as exc:
                skipped.append({"row": index, "reason": str(exc), "row_data": scrub_row(row)})
                continue
            if entry is None:
                skipped.append({"row": index, "reason": "duplicate_statement_row", "row_data": scrub_row(row)})
                continue
            entries.append(entry)

        snapshot = DataSnapshot(
            snapshot_type="broker_statement_import",
            data_json={"rows": [scrub_row(row) for row in rows[:200]]},
            metadata_json={
                "statement_import_batch_id": batch.id,
                "provider": provider,
                "statement_type": statement_type,
                "source_ref": source_ref,
                "raw_payload_hash": raw_hash,
                "execution_available": False,
            },
        )
        self.db.add(snapshot)
        self.db.flush()

        batch.imported_count = len(entries)
        batch.skipped_count = len(skipped)
        batch.status = "imported" if entries else "blocked"
        entry_type_counts: dict[str, int] = {}
        for entry in entries:
            entry_type_counts[entry.entry_type] = entry_type_counts.get(entry.entry_type, 0) + 1
        batch.summary_json = {
            "entry_type_counts": entry_type_counts,
            "skipped": skipped[:25],
            "data_snapshot_id": snapshot.id,
            "execution_available": False,
        }

        score = len(entries) / len(rows) if rows else 0
        quality_status = "VALID" if entries and not skipped else ("PARTIAL" if entries else "BLOCKED")
        quality_report = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source=f"statement_import:{provider}",
            metric_type="statement_import_quality",
            score=score,
            details_json={
                "rows_received": len(rows),
                "rows_imported": len(entries),
                "rows_skipped": len(skipped),
                "quality_status": quality_status,
                "execution_available": False,
            },
        )
        self.db.add(quality_report)
        self.db.flush()

        catalog_entry = DataCatalogEntry(
            dataset_type="broker_statement",
            source=f"statement_import:{provider}",
            source_ref=source_ref or batch.id,
            data_snapshot_id=snapshot.id,
            quality_report_id=quality_report.id,
            row_count=len(entries),
            quality_status=quality_status,
            usable_for_trading=False,
            lineage_json={
                "statement_import_batch_id": batch.id,
                "raw_payload_hash": raw_hash,
                "manual_upload": True,
                "read_only": True,
            },
            contract_json={
                "schema": "statement_csv_v1",
                "required_any": ["type", "entry_type", "symbol", "cash_delta", "quantity"],
                "execution_available": False,
            },
        )
        self.db.add(catalog_entry)
        write_audit_log(
            self.db,
            action="statement_import.imported",
            entity_type="StatementImportBatch",
            entity_id=batch.id,
            payload_json={
                "provider": provider,
                "statement_type": statement_type,
                "rows_received": len(rows),
                "rows_imported": len(entries),
                "rows_skipped": len(skipped),
                "execution_available": False,
            },
            actor_id="ledger-service",
        )
        self.db.commit()
        for entity in [batch, snapshot, quality_report, catalog_entry, *entries]:
            self.db.refresh(entity)
        return {
            "batch": batch,
            "snapshot": snapshot,
            "quality_report": quality_report,
            "catalog_entry": catalog_entry,
            "ledger_entries": entries[:50],
            "skipped": skipped,
            "execution_available": False,
        }

    def sync(self, *, user_id: str = "default-user", limit: int = 200) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        data_trust_report = self._ledger_trust_report()
        created: list[InvestmentLedgerEntry] = []
        existing = 0
        position_created = 0
        paper_created = 0

        positions = list(
            self.db.scalars(
                select(Position)
                .order_by(Position.updated_at.desc(), Position.id.desc())
                .limit(limit)
            ).all()
        )
        for position in positions:
            entry = self._ensure_position_snapshot_entry(position=position, user_id=user_id, now=now)
            if entry is None:
                existing += 1
            else:
                created.append(entry)
                position_created += 1

        executions = list(
            self.db.scalars(
                select(Execution)
                .where(Execution.execution_mode == "paper")
                .order_by(Execution.created_at.desc(), Execution.id.desc())
                .limit(limit)
            ).all()
        )
        for execution in executions:
            entry = self._ensure_paper_execution_entry(execution=execution, user_id=user_id)
            if entry is None:
                existing += 1
            else:
                created.append(entry)
                paper_created += 1

        if created:
            write_audit_log(
                self.db,
                action="investment_ledger.synced",
                entity_type="InvestmentLedgerEntry",
                entity_id="bulk",
                payload_json={
                    "user_id": user_id,
                    "entries_created": len(created),
                    "position_entries_created": position_created,
                    "paper_entries_created": paper_created,
                    "execution_available": False,
                },
                actor_id="ledger-service",
            )
        self.db.commit()
        for entry in created:
            self.db.refresh(entry)
        return {
            "user_id": user_id,
            "synced_at": now,
            "entries_created": len(created),
            "entries_existing": existing,
            "position_entries_created": position_created,
            "paper_entries_created": paper_created,
            "execution_available": False,
            "data_trust_status": data_trust_report["overall_status"],
            "data_trust_report": data_trust_report,
            "entries": created[:25],
        }

    def reconcile(self, *, user_id: str = "default-user") -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        data_trust_report = self._ledger_trust_report()
        positions = list(self.db.scalars(select(Position).order_by(Position.updated_at.desc(), Position.id.desc())).all())
        ledger_entries = list(
            self.db.scalars(
                select(InvestmentLedgerEntry)
                .where(InvestmentLedgerEntry.user_id == user_id)
                .order_by(InvestmentLedgerEntry.occurred_at.desc(), InvestmentLedgerEntry.id.desc())
            ).all()
        )
        snapshot_entries = [entry for entry in ledger_entries if entry.entry_type == "position_snapshot"]

        breaks: list[ReconciliationBreak] = []
        for position in positions:
            matching_entries = [
                entry
                for entry in snapshot_entries
                if entry.source_type == "position" and entry.source_id == position.id
            ]
            observed_quantity = as_float(position.quantity)
            if not matching_entries:
                breaks.append(
                    self._break(
                        account_id=position.account_id,
                        asset_id=position.asset_id,
                        break_type="missing_ledger_position_snapshot",
                        severity="block",
                        expected_quantity=0,
                        observed_quantity=observed_quantity,
                        detail="Current position has no position_snapshot ledger entry.",
                    )
                )
                continue
            expected_quantity = sum(as_float(entry.quantity_delta) for entry in matching_entries)
            delta = observed_quantity - expected_quantity
            if abs(delta) > QUANTITY_TOLERANCE:
                breaks.append(
                    self._break(
                        account_id=position.account_id,
                        asset_id=position.asset_id,
                        break_type="quantity_mismatch",
                        severity="block",
                        expected_quantity=expected_quantity,
                        observed_quantity=observed_quantity,
                        detail="Current position quantity does not match ledger position snapshot.",
                    )
                )

        position_ids = {position.id for position in positions}
        for entry in snapshot_entries:
            if entry.source_type == "position" and entry.source_id and entry.source_id not in position_ids:
                breaks.append(
                    self._break(
                        account_id=entry.account_id,
                        asset_id=entry.asset_id,
                        break_type="orphan_ledger_position_snapshot",
                        severity="warning",
                        expected_quantity=as_float(entry.quantity_delta),
                        observed_quantity=0,
                        detail="Ledger has a position snapshot entry whose source position no longer exists.",
                    )
                )

        if any(item.severity == "block" for item in breaks):
            status = "block"
        elif breaks:
            status = "warn"
        else:
            status = "ok"

        run = ReconciliationRun(
            user_id=user_id,
            scope="portfolio",
            status=status,
            checked_at=checked_at,
            positions_checked=len(positions),
            ledger_entries_checked=len(ledger_entries),
            breaks_count=len(breaks),
            summary_json={
                "position_snapshot_entries": len(snapshot_entries),
                "paper_execution_entries": len([entry for entry in ledger_entries if entry.entry_type == "paper_trade"]),
                "data_trust_status": data_trust_report["overall_status"],
                "execution_available": False,
            },
            execution_available=False,
        )
        self.db.add(run)
        self.db.flush()
        for item in breaks:
            item.reconciliation_run_id = run.id
            self.db.add(item)
        write_audit_log(
            self.db,
            action="investment_ledger.reconciled",
            entity_type="ReconciliationRun",
            entity_id=run.id,
            payload_json={
                "status": status,
                "breaks_count": len(breaks),
                "positions_checked": len(positions),
                "ledger_entries_checked": len(ledger_entries),
                "execution_available": False,
            },
            actor_id="ledger-service",
        )
        self.db.commit()
        self.db.refresh(run)
        for item in breaks:
            self.db.refresh(item)
        return {
            "run": run,
            "breaks": breaks,
            "data_trust_status": data_trust_report["overall_status"],
            "data_trust_report": data_trust_report,
            "execution_available": False,
        }

    def reconcile_extended(self, *, user_id: str = "default-user") -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        data_trust_report = self._ledger_trust_report()
        ledger_entries = list(
            self.db.scalars(
                select(InvestmentLedgerEntry)
                .where(InvestmentLedgerEntry.user_id == user_id)
                .order_by(InvestmentLedgerEntry.occurred_at.asc(), InvestmentLedgerEntry.id.asc())
            ).all()
        )
        breaks: list[ReconciliationBreak] = []
        breaks.extend(self._cash_reconciliation_breaks(ledger_entries))
        breaks.extend(self._tax_lot_reconciliation_breaks(ledger_entries))
        breaks.extend(self._corporate_action_reconciliation_breaks(ledger_entries))

        if any(item.severity == "block" for item in breaks):
            status = "block"
        elif breaks:
            status = "warn"
        else:
            status = "ok"

        run = ReconciliationRun(
            user_id=user_id,
            scope="extended_ledger",
            status=status,
            checked_at=checked_at,
            positions_checked=0,
            ledger_entries_checked=len(ledger_entries),
            breaks_count=len(breaks),
            summary_json={
                "cash_balance_entries": len([entry for entry in ledger_entries if entry.entry_type == "cash_balance"]),
                "external_tax_lot_entries": len([entry for entry in ledger_entries if entry.entry_type == "external_tax_lot"]),
                "corporate_action_entries": len([entry for entry in ledger_entries if entry.entry_type == "corporate_action"]),
                "paper_tax_lots": self._count_tax_lots(),
                "paper_corporate_actions": self._count_corporate_actions(),
                "data_trust_status": data_trust_report["overall_status"],
                "execution_available": False,
            },
            execution_available=False,
        )
        self.db.add(run)
        self.db.flush()
        for item in breaks:
            item.reconciliation_run_id = run.id
            self.db.add(item)
        write_audit_log(
            self.db,
            action="investment_ledger.extended_reconciled",
            entity_type="ReconciliationRun",
            entity_id=run.id,
            payload_json={
                "status": status,
                "scope": "extended_ledger",
                "breaks_count": len(breaks),
                "ledger_entries_checked": len(ledger_entries),
                "execution_available": False,
            },
            actor_id="ledger-service",
        )
        self.db.commit()
        self.db.refresh(run)
        for item in breaks:
            self.db.refresh(item)
        return {
            "run": run,
            "breaks": breaks,
            "data_trust_status": data_trust_report["overall_status"],
            "data_trust_report": data_trust_report,
            "execution_available": False,
        }

    def latest_reconciliation(self, *, user_id: str = "default-user") -> dict[str, Any] | None:
        run = self.db.scalar(
            select(ReconciliationRun)
            .where(ReconciliationRun.user_id == user_id)
            .order_by(ReconciliationRun.checked_at.desc(), ReconciliationRun.id.desc())
            .limit(1)
        )
        if run is None:
            return None
        breaks = list(
            self.db.scalars(
                select(ReconciliationBreak)
                .where(ReconciliationBreak.reconciliation_run_id == run.id)
                .order_by(ReconciliationBreak.severity.desc(), ReconciliationBreak.id.desc())
            ).all()
        )
        return {"run": run, "breaks": breaks, "execution_available": False}

    def _workbench_reconciliation_report(self, latest: dict[str, Any] | None) -> dict[str, Any] | None:
        if latest is None:
            return None
        return {
            "run": ReconciliationRunRead.model_validate(latest["run"]).model_dump(mode="json"),
            "breaks": [
                ReconciliationBreakRead.model_validate(item).model_dump(mode="json")
                for item in latest["breaks"]
            ],
            "execution_available": False,
        }

    def _workbench_statement_import(self, item: StatementImportBatch) -> dict[str, Any]:
        return StatementImportBatchRead.model_validate(item).model_dump(mode="json")

    def _ledger_trust_report(self) -> dict[str, Any]:
        return DataCatalogService(self.db).trust_report(decision_scope="ledger")

    def _count_ledger_entries(self, *, user_id: str) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(InvestmentLedgerEntry)
                .where(InvestmentLedgerEntry.user_id == user_id)
            )
            or 0
        )

    def _count_positions(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Position)) or 0)

    def _count_paper_executions(self) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Execution)
                .where(Execution.execution_mode == "paper")
            )
            or 0
        )

    def _count_open_repair_tasks(self, *, user_id: str) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkflowReviewTask)
                .where(
                    WorkflowReviewTask.user_id == user_id,
                    WorkflowReviewTask.item_type == "ledger_repair",
                    WorkflowReviewTask.status.not_in(["completed", "done"]),
                )
            )
            or 0
        )

    def _ensure_position_snapshot_entry(
        self,
        *,
        position: Position,
        user_id: str,
        now: datetime,
    ) -> InvestmentLedgerEntry | None:
        existing = self._existing(user_id=user_id, source_type="position", source_id=position.id, entry_type="position_snapshot")
        if existing is not None:
            return None
        account = self.db.get(Account, position.account_id)
        asset = self.db.get(Asset, position.asset_id)
        entry = InvestmentLedgerEntry(
            user_id=user_id,
            account_id=position.account_id,
            asset_id=position.asset_id,
            source_type="position",
            source_id=position.id,
            entry_type="position_snapshot",
            side=None,
            quantity_delta=as_float(position.quantity),
            cash_delta=0,
            price=as_float(position.average_cost),
            fee_amount=0,
            realized_pnl=as_float(position.realized_pnl),
            currency=asset.currency if asset is not None else (account.base_currency if account is not None else "USD"),
            occurred_at=position.updated_at or now,
            status="posted",
            metadata_json={
                "market_price": as_float(position.market_price),
                "market_value": as_float(position.market_value),
                "unrealized_pnl": as_float(position.unrealized_pnl),
                "weight": as_float(position.weight),
                "read_only_snapshot": True,
                "execution_available": False,
            },
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def _ensure_paper_execution_entry(self, *, execution: Execution, user_id: str) -> InvestmentLedgerEntry | None:
        existing = self._existing(user_id=user_id, source_type="paper_execution", source_id=execution.id, entry_type="paper_trade")
        if existing is not None:
            return None
        draft = self.db.get(OrderDraft, execution.order_draft_id)
        intent = self.db.get(OrderIntent, draft.order_intent_id) if draft is not None else None
        if intent is None:
            return None
        asset = self.db.get(Asset, intent.asset_id)
        signed_quantity = as_float(execution.filled_quantity)
        if intent.side.lower() == "sell":
            signed_quantity = -signed_quantity
        entry = InvestmentLedgerEntry(
            user_id=user_id,
            account_id=intent.account_id,
            asset_id=intent.asset_id,
            source_type="paper_execution",
            source_id=execution.id,
            entry_type="paper_trade",
            side=intent.side,
            quantity_delta=signed_quantity,
            cash_delta=as_float(execution.cash_effect),
            price=as_float(execution.average_fill_price),
            fee_amount=as_float(execution.fee_amount),
            realized_pnl=as_float(execution.realized_pnl),
            currency=asset.currency if asset is not None else "USD",
            occurred_at=execution.created_at,
            status="posted",
            metadata_json={
                "order_draft_id": execution.order_draft_id,
                "order_intent_id": intent.id,
                "execution_mode": execution.execution_mode,
                "execution_status": execution.status,
                "paper_only": True,
                "execution_available": False,
            },
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def _statement_row_to_entry(
        self,
        *,
        batch: StatementImportBatch,
        row: dict[str, str],
        row_index: int,
        provider: str,
        account_label: str | None,
        default_currency: str,
    ) -> InvestmentLedgerEntry | None:
        raw_type = row.get("entry_type") or row.get("type") or row.get("transaction_type") or row.get("activity_type")
        side = normalize_side(row.get("side") or raw_type)
        entry_type = normalize_statement_entry_type(raw_type, side)
        if entry_type is None:
            raise LedgerImportError("row type is unsupported or missing")

        currency = (row.get("currency") or default_currency or "USD").upper()
        account = self._statement_account(
            provider=provider,
            account_label=row.get("account") or row.get("account_label") or account_label,
            currency=currency,
        )
        symbol = (row.get("symbol") or row.get("ticker") or "").upper()
        asset = self._statement_asset(row=row, symbol=symbol, currency=currency) if symbol else None
        quantity = first_number(row, ["quantity", "qty", "shares", "units"])
        price = first_optional_number(row, ["price", "average_price", "avg_price", "fill_price"])
        fee = first_number(row, ["fee", "fees", "commission"])
        cash = first_optional_number(row, ["cash_delta", "cash", "cash_amount", "amount", "net_amount"])
        if cash is None:
            cash = infer_cash_delta(entry_type=entry_type, side=side, quantity=quantity, price=price, fee=fee)
        signed_quantity = signed_quantity_delta(entry_type=entry_type, side=side, quantity=quantity)
        occurred_at = parse_statement_datetime(row.get("occurred_at") or row.get("date") or row.get("timestamp"))
        source_id = statement_source_id(
            provider=provider,
            source_ref=batch.source_ref or batch.raw_payload_hash,
            row_index=row_index,
            row=row,
        )
        if self._existing(user_id=batch.user_id, source_type="broker_statement", source_id=source_id, entry_type=entry_type) is not None:
            return None

        entry = InvestmentLedgerEntry(
            user_id=batch.user_id,
            account_id=account.id,
            asset_id=asset.id if asset is not None else None,
            source_type="broker_statement",
            source_id=source_id,
            entry_type=entry_type,
            side=side,
            quantity_delta=signed_quantity,
            cash_delta=cash,
            price=price,
            fee_amount=fee,
            realized_pnl=first_number(row, ["realized_pnl", "pnl"]),
            currency=currency,
            occurred_at=occurred_at,
            status="posted",
            metadata_json={
                "statement_import_batch_id": batch.id,
                "row_index": row_index,
                "provider": provider,
                "statement_type": batch.statement_type,
                "source_ref": batch.source_ref,
                "raw_entry_type": raw_type,
                "read_only_statement": True,
                "execution_available": False,
                "row": scrub_row(row),
            },
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def _statement_account(self, *, provider: str, account_label: str | None, currency: str) -> Account:
        label = (account_label or f"{provider} Statement Account").strip()
        account = self.db.scalar(
            select(Account).where(Account.name == label, Account.broker == provider).limit(1)
        )
        if account is not None:
            return account
        account = Account(
            name=label,
            account_type="broker_statement",
            broker=provider,
            base_currency=currency,
            mode="read_only",
            live_trading_enabled=False,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def _statement_asset(self, *, row: dict[str, str], symbol: str, currency: str) -> Asset:
        market = row.get("market") or "US"
        venue = row.get("venue") or row.get("exchange") or market
        asset = self.db.scalar(
            select(Asset).where(Asset.symbol == symbol, Asset.market == market, Asset.venue == venue).limit(1)
        )
        if asset is not None:
            return asset
        asset = Asset(
            symbol=symbol,
            name=row.get("name") or symbol,
            asset_type=row.get("asset_type") or "stock",
            market=market,
            venue=venue,
            currency=currency,
            tradable=False,
            manual_enabled=False,
            auto_enabled=False,
            risk_level="medium",
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def _existing(
        self,
        *,
        user_id: str,
        source_type: str,
        source_id: str | None,
        entry_type: str,
    ) -> InvestmentLedgerEntry | None:
        return self.db.scalar(
            select(InvestmentLedgerEntry)
            .where(
                InvestmentLedgerEntry.user_id == user_id,
                InvestmentLedgerEntry.source_type == source_type,
                InvestmentLedgerEntry.source_id == source_id,
                InvestmentLedgerEntry.entry_type == entry_type,
            )
            .limit(1)
        )

    def _break(
        self,
        *,
        account_id: str | None,
        asset_id: str | None,
        break_type: str,
        severity: str,
        expected_quantity: float,
        observed_quantity: float,
        detail: str,
    ) -> ReconciliationBreak:
        delta = observed_quantity - expected_quantity
        return ReconciliationBreak(
            reconciliation_run_id="pending",
            account_id=account_id,
            asset_id=asset_id,
            break_type=break_type,
            severity=severity,
            expected_quantity=expected_quantity,
            observed_quantity=observed_quantity,
            delta_quantity=delta,
            expected_cash=0,
            observed_cash=0,
            delta_cash=0,
            detail=detail,
            metadata_json={"execution_available": False},
        )

    def _cash_break(
        self,
        *,
        account_id: str | None,
        break_type: str,
        severity: str,
        expected_cash: float,
        observed_cash: float,
        detail: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> ReconciliationBreak:
        return ReconciliationBreak(
            reconciliation_run_id="pending",
            account_id=account_id,
            asset_id=None,
            break_type=break_type,
            severity=severity,
            expected_quantity=0,
            observed_quantity=0,
            delta_quantity=0,
            expected_cash=expected_cash,
            observed_cash=observed_cash,
            delta_cash=observed_cash - expected_cash,
            detail=detail,
            metadata_json={**(metadata_json or {}), "execution_available": False},
        )

    def _cash_reconciliation_breaks(self, ledger_entries: list[InvestmentLedgerEntry]) -> list[ReconciliationBreak]:
        breaks: list[ReconciliationBreak] = []
        balances: dict[tuple[str | None, str], InvestmentLedgerEntry] = {}
        for entry in ledger_entries:
            if entry.entry_type != "cash_balance":
                continue
            key = (entry.account_id, entry.currency)
            current = balances.get(key)
            if current is None or normalize_dt(entry.occurred_at) >= normalize_dt(current.occurred_at):
                balances[key] = entry
        for (account_id, currency), balance_entry in balances.items():
            expected_cash = sum(
                as_float(entry.cash_delta)
                for entry in ledger_entries
                if entry.account_id == account_id
                and entry.currency == currency
                and entry.entry_type in {"paper_trade", "external_trade", "cash_movement", "cash_event"}
                and normalize_dt(entry.occurred_at) <= normalize_dt(balance_entry.occurred_at)
            )
            observed_cash = as_float(balance_entry.cash_delta)
            if abs(observed_cash - expected_cash) > CASH_TOLERANCE:
                breaks.append(
                    self._cash_break(
                        account_id=account_id,
                        break_type="cash_balance_mismatch",
                        severity="warning",
                        expected_cash=expected_cash,
                        observed_cash=observed_cash,
                        detail="Imported cash balance does not match accumulated cash ledger deltas.",
                        metadata_json={"currency": currency, "cash_balance_entry_id": balance_entry.id},
                    )
                )
        return breaks

    def _tax_lot_reconciliation_breaks(self, ledger_entries: list[InvestmentLedgerEntry]) -> list[ReconciliationBreak]:
        external_entries = [entry for entry in ledger_entries if entry.entry_type == "external_tax_lot"]
        if not external_entries:
            return []
        paper_lots = list(
            self.db.scalars(
                select(PaperTaxLot)
                .where(PaperTaxLot.status == "open", PaperTaxLot.quantity_remaining > 0)
                .order_by(PaperTaxLot.opened_at.asc(), PaperTaxLot.id.asc())
            ).all()
        )
        paper_by_key: dict[tuple[str | None, str | None], float] = {}
        for lot in paper_lots:
            key = (lot.account_id, lot.asset_id)
            paper_by_key[key] = paper_by_key.get(key, 0) + as_float(lot.quantity_remaining)
        external_by_key: dict[tuple[str | None, str | None], float] = {}
        for entry in external_entries:
            key = (entry.account_id, entry.asset_id)
            external_by_key[key] = external_by_key.get(key, 0) + abs(as_float(entry.quantity_delta))
        breaks: list[ReconciliationBreak] = []
        for (account_id, asset_id), observed_quantity in external_by_key.items():
            expected_quantity = paper_by_key.get((account_id, asset_id), 0)
            if abs(observed_quantity - expected_quantity) > QUANTITY_TOLERANCE:
                breaks.append(
                    self._break(
                        account_id=account_id,
                        asset_id=asset_id,
                        break_type="tax_lot_quantity_mismatch",
                        severity="warning",
                        expected_quantity=expected_quantity,
                        observed_quantity=observed_quantity,
                        detail="External tax-lot quantity does not match open paper tax-lot quantity.",
                    )
                )
        return breaks

    def _corporate_action_reconciliation_breaks(self, ledger_entries: list[InvestmentLedgerEntry]) -> list[ReconciliationBreak]:
        external_entries = [entry for entry in ledger_entries if entry.entry_type == "corporate_action"]
        if not external_entries:
            return []
        paper_actions = list(
            self.db.scalars(
                select(PaperCorporateAction).order_by(PaperCorporateAction.effective_at.desc(), PaperCorporateAction.id.desc())
            ).all()
        )
        paper_keys = {(action.account_id, action.asset_id, action.action_type) for action in paper_actions}
        breaks: list[ReconciliationBreak] = []
        for entry in external_entries:
            action_type = str(entry.metadata_json.get("raw_entry_type") or "").lower()
            normalized = "stock_split" if "split" in action_type else ("cash_dividend" if "dividend" in action_type else "corporate_action")
            if (entry.account_id, entry.asset_id, normalized) not in paper_keys:
                breaks.append(
                    self._break(
                        account_id=entry.account_id,
                        asset_id=entry.asset_id,
                        break_type="corporate_action_not_recorded",
                        severity="warning",
                        expected_quantity=0,
                        observed_quantity=as_float(entry.quantity_delta),
                        detail="Statement contains a corporate action that has not been recorded in the paper ledger.",
                    )
                )
        return breaks

    def _count_tax_lots(self) -> int:
        return len(list(self.db.scalars(select(PaperTaxLot.id)).all()))

    def _count_corporate_actions(self) -> int:
        return len(list(self.db.scalars(select(PaperCorporateAction.id)).all()))


def as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def ledger_policy_check(
    key: str,
    label: str,
    status: str,
    summary: str,
    *,
    blockers: list[str] | None = None,
    next_actions: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "summary": summary,
        "blockers": blockers or [],
        "next_actions": next_actions or [],
        "evidence": evidence or {},
    }


def ledger_work_item(key: str, label: str, status: str, summary: str, next_actions: list[str]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "summary": summary,
        "next_actions": next_actions,
    }


def workflow_task_payload(item: WorkflowReviewTask) -> dict[str, Any]:
    return {
        "id": item.id,
        "queue_item_id": item.queue_item_id,
        "item_type": item.item_type,
        "title": item.title,
        "detail": item.detail,
        "priority": item.priority,
        "status": item.status,
        "assignee_id": item.assignee_id,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "related_entity_type": item.related_entity_type,
        "related_entity_id": item.related_entity_id,
        "payload_json": item.payload_json,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "execution_available": False,
    }


def ledger_entry_payload(item: InvestmentLedgerEntry) -> dict[str, Any]:
    return {
        "id": item.id,
        "account_id": item.account_id,
        "asset_id": item.asset_id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "entry_type": item.entry_type,
        "side": item.side,
        "quantity_delta": float(item.quantity_delta),
        "cash_delta": float(item.cash_delta),
        "price": float(item.price) if item.price is not None else None,
        "fee_amount": float(item.fee_amount),
        "realized_pnl": float(item.realized_pnl),
        "currency": item.currency,
        "occurred_at": item.occurred_at.isoformat(),
        "status": item.status,
        "metadata_json": item.metadata_json,
        "execution_available": False,
    }


def reconciliation_policy_status(latest: dict[str, Any] | None) -> str:
    if latest is None:
        return "block"
    if latest["run"].status == "block":
        return "block"
    if latest["run"].status == "warn":
        return "warn"
    return "ok"


def reconciliation_policy_blockers(latest: dict[str, Any] | None) -> list[str]:
    if latest is None:
        return ["latest_reconciliation_missing"]
    if latest["run"].status == "ok":
        return []
    return [item.break_type for item in latest["breaks"] if item.severity == "block"] or [f"latest_reconciliation_{latest['run'].status}"]


def dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def normalize_key(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def normalize_row(row: dict[str, Any]) -> dict[str, str]:
    return {normalize_key(key): str(value or "").strip() for key, value in row.items()}


def scrub_row(row: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in row.items() if "secret" not in key and "token" not in key and "password" not in key}


def row_repair_suggestions(reason: str | None, *, has_linked_break: bool) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    if reason == "duplicate_statement_row":
        suggestions.append({"code": "confirm_duplicate", "label": "Confirm this row is a duplicate and keep the original normalized entry."})
    elif reason:
        suggestions.append({"code": "correct_mapping", "label": "Correct the source mapping and re-import the statement as a new batch."})
    if has_linked_break:
        suggestions.append({"code": "open_linked_break", "label": "Open the linked reconciliation break before completing the repair task."})
    suggestions.append({"code": "rerun_reconciliation", "label": "Rerun reconciliation after the reviewed repair is complete."})
    return suggestions


def first_number(row: dict[str, str], keys: list[str]) -> float:
    value = first_optional_number(row, keys)
    return value if value is not None else 0.0


def first_optional_number(row: dict[str, str], keys: list[str]) -> float | None:
    for key in keys:
        raw = row.get(key)
        if raw not in (None, ""):
            try:
                return float(str(raw).replace(",", ""))
            except ValueError:
                return None
    return None


def normalize_side(value: str | None) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"buy", "bought", "purchase"}:
        return "buy"
    if text in {"sell", "sold"}:
        return "sell"
    if text in {"deposit", "inflow"}:
        return "deposit"
    if text in {"withdrawal", "withdraw", "outflow"}:
        return "withdrawal"
    return None


def normalize_statement_entry_type(raw_type: str | None, side: str | None) -> str | None:
    text = str(raw_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"position", "holding", "holdings"}:
        return "external_position"
    if text in {"cash_balance", "balance"}:
        return "cash_balance"
    if side in {"deposit", "withdrawal"} or text in {"cash_movement", "cash_transfer", "transfer"}:
        return "cash_movement"
    if text in {"dividend", "interest", "fee", "commission"}:
        return "cash_event"
    if text in {"tax_lot", "lot"}:
        return "external_tax_lot"
    if text in {"split", "stock_split", "corporate_action", "cash_dividend"}:
        return "corporate_action"
    if side in {"buy", "sell"} or text in {"trade", "fill", "execution"}:
        return "external_trade"
    return None


def signed_quantity_delta(*, entry_type: str, side: str | None, quantity: float) -> float:
    if entry_type not in {"external_trade", "external_position", "external_tax_lot", "corporate_action"}:
        return 0.0
    if side == "sell":
        return -abs(quantity)
    return quantity


def infer_cash_delta(*, entry_type: str, side: str | None, quantity: float, price: float | None, fee: float) -> float:
    if entry_type != "external_trade" or price is None:
        return 0.0
    notional = abs(quantity) * price
    if side == "sell":
        return notional - fee
    if side == "buy":
        return -notional - fee
    return 0.0


def parse_statement_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    cleaned = value.strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(cleaned, "%Y-%m-%d")
        except ValueError as exc:
            raise LedgerImportError(f"invalid occurred_at/date value: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def statement_source_id(*, provider: str, source_ref: str, row_index: int, row: dict[str, str]) -> str:
    canonical = json.dumps(row, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(f"{provider}|{source_ref}|{row_index}|{canonical}".encode("utf-8")).hexdigest()


def normalize_dt(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
