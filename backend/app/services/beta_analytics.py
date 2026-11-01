from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.config import Settings
from app.core.config import get_settings
from app.models import AuditLog
from app.models import ExportArtifact
from app.models import InvestmentThesis
from app.models import LocalUserConfig
from app.models import Position
from app.models import UserAccount
from app.services.privacy_center import PrivacyCenterService


class BetaAnalyticsError(ValueError):
    pass


class BetaAnalyticsService:
    PROFILE_KEY = "beta:icp_profile"
    TERMS_VERSION = "private-beta-2026-07-17-v1"
    CONSENT_ACTION = "ACCEPT_PRIVATE_BETA_TERMS"
    ICP = {
        "key": "self_directed_thesis_multi_asset_investor_v1",
        "title": "Self-directed thesis-driven US equity/ETF and crypto investor",
        "required_criteria": ["holds_us_equity_or_etf", "holds_crypto", "thesis_driven", "self_directed"],
        "excluded": ["fully_delegated_investor", "live_execution_seeker", "withdrawal_or_wallet_signing_required"],
    }

    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def profile(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require_read(actor)
        record = self._profile_record(actor.user_id)
        value = dict(record.value_json or {}) if record else None
        consent_current = bool(value and value.get("private_beta_consent") and value.get("risk_disclosure_acknowledged") and value.get("beta_terms_version") == self.TERMS_VERSION and value.get("privacy_policy_version") == PrivacyCenterService.POLICY_VERSION)
        return {
            "icp": self.ICP,
            "terms": {"beta_terms_version": self.TERMS_VERSION, "privacy_policy_version": PrivacyCenterService.POLICY_VERSION, "consent_action": self.CONSENT_ACTION},
            "profile": value,
            "consent_current": consent_current,
            "qualified": bool(value and value.get("qualified") and consent_current),
            "usage_metrics_counted": False,
            "note": "Self-attested ICP metadata qualifies the audience only; it never counts as activation or retention evidence.",
        }

    def save_profile(self, *, actor: AuthenticatedUser, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_read(actor)
        criteria = {key: bool(payload.get(key)) for key in self.ICP["required_criteria"]}
        consent_requested = bool(payload.get("private_beta_consent"))
        risk_requested = bool(payload.get("risk_disclosure_acknowledged"))
        accepting = consent_requested or risk_requested
        if accepting and (
            payload.get("consent_action") != self.CONSENT_ACTION
            or payload.get("beta_terms_version") != self.TERMS_VERSION
            or payload.get("privacy_policy_version") != PrivacyCenterService.POLICY_VERSION
        ):
            raise BetaAnalyticsError("current versioned private Beta terms and privacy policy must be explicitly accepted")
        consent = consent_requested
        risk_ack = risk_requested
        excluded = [key for key in self.ICP["excluded"] if bool(payload.get(key))]
        qualified = all(criteria.values()) and consent and risk_ack and not excluded
        record = self._profile_record(actor.user_id)
        previous = (record.value_json or {}) if record else {}
        recorded_at = self._now()
        previously_consented = bool(previous.get("private_beta_consent") and previous.get("risk_disclosure_acknowledged"))
        consented_now = consent and risk_ack
        value = {
            "icp_key": self.ICP["key"],
            **criteria,
            "private_beta_consent": consent,
            "risk_disclosure_acknowledged": risk_ack,
            "beta_terms_version": self.TERMS_VERSION if consented_now else previous.get("beta_terms_version"),
            "privacy_policy_version": PrivacyCenterService.POLICY_VERSION if consented_now else previous.get("privacy_policy_version"),
            "consent_accepted_at": previous.get("consent_accepted_at") if previously_consented and consented_now and previous.get("beta_terms_version") == self.TERMS_VERSION and previous.get("privacy_policy_version") == PrivacyCenterService.POLICY_VERSION else recorded_at.isoformat() if consented_now else None,
            "consent_withdrawn_at": recorded_at.isoformat() if previously_consented and not consented_now else previous.get("consent_withdrawn_at"),
            "excluded_criteria": excluded,
            "qualified": qualified,
            "recorded_at": recorded_at.isoformat(),
            "qualified_at": (previous.get("qualified_at") if previous.get("qualified") and qualified else recorded_at.isoformat() if qualified else None),
            "evidence_kind": "user_self_attestation_not_usage_evidence",
            "production_execution_allowed": False,
        }
        if record is None:
            record = LocalUserConfig(user_id=actor.user_id, config_key=self.PROFILE_KEY, value_json=value, description="Private Beta ICP self-attestation; not usage or retention evidence.")
            self.db.add(record)
        else:
            record.value_json = value
        self.db.flush()
        self.db.add(AuditLog(
            user_id=actor.user_id,
            actor_type="user",
            actor_id=actor.user_id,
            action="beta.icp_profile_recorded",
            entity_type="LocalUserConfig",
            entity_id=record.id,
            payload_json={"icp_key": self.ICP["key"], "qualified": qualified, "consented": consented_now, "beta_terms_version": self.TERMS_VERSION, "privacy_policy_version": PrivacyCenterService.POLICY_VERSION, "usage_evidence": False},
        ))
        self.db.commit()
        return self.profile(actor=actor)

    def metrics(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require_operator(actor)
        with self._operator_scope():
            profiles = list(self.db.scalars(
                select(LocalUserConfig).where(LocalUserConfig.config_key == self.PROFILE_KEY).execution_options(tenant_scope_bypass=True)
            ).all())
            qualified_profiles = [profile for profile in profiles if (
                (profile.value_json or {}).get("qualified")
                and (profile.value_json or {}).get("beta_terms_version") == self.TERMS_VERSION
                and (profile.value_json or {}).get("privacy_policy_version") == PrivacyCenterService.POLICY_VERSION
            )]
            users = {user.user_id: user for user in self.db.scalars(
                select(UserAccount).where(UserAccount.user_id.in_([profile.user_id for profile in qualified_profiles])).execution_options(tenant_scope_bypass=True)
            ).all()} if qualified_profiles else {}
            rows = [self._user_metrics(profile, users.get(profile.user_id)) for profile in qualified_profiles]

        evidence_environment = self._real_evidence_environment()
        verified_rows = [row for row in rows if row["identity_evidence_valid"]]
        mature_rows = [row for row in verified_rows if row["observation_days"] >= 28]
        retained_four_weeks = [row for row in mature_rows if row["four_week_retained"]]
        activated = [row for row in verified_rows if row["activated"]]
        d7_eligible = [row for row in verified_rows if row["observation_days"] >= 14]
        d7_retained = [row for row in d7_eligible if row["d7_retained"]]
        return {
            "status": "verified" if evidence_environment and len(retained_four_weeks) >= 5 else "insufficient_real_beta_evidence",
            "icp": self.ICP,
            "evidence_environment": evidence_environment,
            "counts": {
                "self_attested_profiles": len(profiles),
                "qualified_profiles": len(qualified_profiles),
                "identity_verified_profiles": len(verified_rows),
                "activated_users": len(activated),
                "d7_eligible_users": len(d7_eligible),
                "d7_retained_users": len(d7_retained),
                "four_week_eligible_users": len(mature_rows),
                "four_week_retained_users": len(retained_four_weeks),
            },
            "metrics": {
                "activation_rate": self._rate(len(activated), len(verified_rows)),
                "first_day_loop_rate": self._rate(sum(1 for row in verified_rows if row["first_day_loop_completed"]), len(verified_rows)),
                "d7_retention_rate": self._rate(len(d7_retained), len(d7_eligible)),
                "four_week_retention_rate": self._rate(len(retained_four_weeks), len(mature_rows)),
                "average_weekly_active_days": self._average([row["average_weekly_active_days"] for row in verified_rows]),
                "average_time_to_first_value_hours": self._average([row["time_to_first_value_hours"] for row in activated if row["time_to_first_value_hours"] is not None]),
                "thesis_coverage_rate": self._ratio_sum(rows, "covered_position_assets", "position_assets"),
                "daily_review_completion_rate": self._ratio_sum(rows, "daily_close_count", "daily_open_count", cap=True),
            },
            "users": rows,
            "blockers": self._blockers(evidence_environment, verified_rows, mature_rows, retained_four_weeks),
            "rules": {
                "activation": "first persisted daily_close_record after ICP profile",
                "first_day_loop": "daily_close_record within 24 hours of profile recorded_at",
                "d7_retention": "at least one daily open/close on day 7 through day 13",
                "four_week_retention": "at least one daily open/close in each of four seven-day windows",
                "weekly_frequency": "distinct active days divided by observed weeks, capped at four weeks",
                "thesis_coverage": "distinct held asset ids with an active thesis divided by distinct held asset ids",
                "review_completion": "daily close count divided by daily open count, capped at 100%",
            },
            "manual_activation_events_counted": False,
            "simulated_or_test_users_counted": False,
            "registered_users_counted_without_behavior": False,
            "generated_at": self._now(),
            "production_execution_allowed": False,
        }

    def _user_metrics(self, profile: LocalUserConfig, user: UserAccount | None) -> dict[str, Any]:
        recorded_at = self._parse((profile.value_json or {}).get("qualified_at")) or self._parse((profile.value_json or {}).get("recorded_at")) or profile.created_at
        now = self._now()
        artifacts = list(self.db.scalars(
            select(ExportArtifact).where(
                ExportArtifact.user_id == profile.user_id,
                ExportArtifact.export_type.in_(("daily_open_record", "daily_close_record")),
                ExportArtifact.created_at >= recorded_at,
            ).order_by(ExportArtifact.created_at).execution_options(tenant_scope_bypass=True)
        ).all())
        opens = [row for row in artifacts if row.export_type == "daily_open_record"]
        closes = [row for row in artifacts if row.export_type == "daily_close_record"]
        activity_days = sorted({self._aware(row.created_at).date() for row in artifacts})
        first_value = closes[0].created_at if closes else None
        observation_days = max(0, (now.date() - self._aware(recorded_at).date()).days)
        windows = [
            any(start <= (day - self._aware(recorded_at).date()).days < start + 7 for day in activity_days)
            for start in (0, 7, 14, 21)
        ]
        d7 = any(7 <= (day - self._aware(recorded_at).date()).days <= 13 for day in activity_days)
        positions = list(self.db.scalars(select(Position).where(Position.user_id == profile.user_id).execution_options(tenant_scope_bypass=True)).all())
        position_assets = {position.asset_id for position in positions}
        theses = list(self.db.scalars(select(InvestmentThesis).where(
            InvestmentThesis.user_id == profile.user_id,
            InvestmentThesis.status == "active",
        ).execution_options(tenant_scope_bypass=True)).all())
        covered_assets = position_assets.intersection({thesis.asset_id for thesis in theses})
        identity_provider = str((user.onboarding_state_json or {}).get("identity_provider") or "") if user else ""
        identity_valid = bool(
            self._real_evidence_environment()
            and user
            and user.status == "active"
            and identity_provider.startswith("https://")
            and not self._test_identity(profile.user_id)
        )
        weeks = min(4.0, max(1.0, (observation_days + 1) / 7))
        return {
            "user_ref": self._user_ref(profile.user_id),
            "identity_evidence_valid": identity_valid,
            "observation_days": observation_days,
            "activated": first_value is not None,
            "first_day_loop_completed": bool(first_value and self._aware(first_value) <= self._aware(recorded_at) + timedelta(hours=24)),
            "time_to_first_value_hours": round((self._aware(first_value) - self._aware(recorded_at)).total_seconds() / 3600, 2) if first_value else None,
            "d7_retained": d7 if observation_days >= 14 else None,
            "four_week_windows": windows,
            "four_week_retained": all(windows) if observation_days >= 28 else False,
            "average_weekly_active_days": round(len(activity_days) / weeks, 2),
            "daily_open_count": len(opens),
            "daily_close_count": len(closes),
            "position_assets": len(position_assets),
            "covered_position_assets": len(covered_assets),
            "raw_user_id_returned": False,
        }

    def _real_evidence_environment(self) -> bool:
        return bool(
            self.settings.environment in {"staging", "production"}
            and self.settings.managed_auth_required
            and (self.settings.oidc_issuer or "").startswith("https://")
            and "localhost" not in (self.settings.oidc_issuer or "")
        )

    @staticmethod
    def _test_identity(user_id: str) -> bool:
        lowered = user_id.lower()
        return lowered == "default-user" or any(fragment in lowered for fragment in ("test", "demo", "sample", "e2e", "fixture"))

    @staticmethod
    def _user_ref(user_id: str) -> str:
        import hashlib
        return hashlib.sha256(user_id.encode()).hexdigest()[:16]

    def _profile_record(self, user_id: str) -> LocalUserConfig | None:
        return self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == self.PROFILE_KEY).limit(1))

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return round(mean(values), 2) if values else None

    @staticmethod
    def _ratio_sum(rows: list[dict[str, Any]], numerator: str, denominator: str, *, cap: bool = False) -> float | None:
        den = sum(int(row[denominator]) for row in rows)
        if not den:
            return None
        ratio = sum(int(row[numerator]) for row in rows) / den
        return round(min(1.0, ratio) if cap else ratio, 4)

    @staticmethod
    def _blockers(environment: bool, verified: list[dict[str, Any]], mature: list[dict[str, Any]], retained: list[dict[str, Any]]) -> list[str]:
        blockers = []
        if not environment:
            blockers.append("real_staging_or_production_oidc_environment_missing")
        if len(verified) < 5:
            blockers.append("fewer_than_5_identity_verified_beta_users")
        if len(mature) < 5:
            blockers.append("fewer_than_5_users_observed_for_4_weeks")
        if len(retained) < 5:
            blockers.append("fewer_than_5_users_retained_across_all_4_weeks")
        return blockers

    @staticmethod
    def _parse(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @contextmanager
    def _operator_scope(self):
        previous = self.db.info.get("tenant_scope_bypass")
        self.db.info["tenant_scope_bypass"] = True
        try:
            yield
        finally:
            if previous is None:
                self.db.info.pop("tenant_scope_bypass", None)
            else:
                self.db.info["tenant_scope_bypass"] = previous

    @staticmethod
    def _require_read(actor: AuthenticatedUser) -> None:
        if "read" not in actor.permissions:
            raise BetaAnalyticsError("authenticated beta profile access is required")

    @staticmethod
    def _require_operator(actor: AuthenticatedUser) -> None:
        if actor.role not in {"owner", "admin", "operator"} or "users:read" not in actor.permissions or "readiness:read" not in actor.permissions:
            raise BetaAnalyticsError("beta analytics operator permission is required")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
