import hashlib
import json
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot


class DataCatalogNotFoundError(ValueError):
    pass


class DataTrustGateError(ValueError):
    """Raised when downstream decision support tries to consume untrusted data."""

    def __init__(self, message: str, *, gate: dict[str, Any]):
        super().__init__(message)
        self.gate = gate


DATA_TRUST_REQUIREMENTS: dict[str, dict[str, bool]] = {
    "research": {"market_quotes": True, "market_candles": True},
    "order_draft": {"market_quotes": True, "market_candles": True, "read_only_account": False},
    "ledger": {"read_only_account": False},
    "daily_review": {"market_quotes": False, "read_only_account": False},
}

DATA_TRUST_FRESHNESS_THRESHOLDS: dict[str, timedelta] = {
    "market_quotes": timedelta(hours=24),
    "market_candles": timedelta(days=7),
    "read_only_account": timedelta(hours=24),
    "csv_holdings": timedelta(days=30),
    "csv_crypto_holdings": timedelta(days=30),
    "csv_wallet_balances": timedelta(days=30),
    "csv_trades": timedelta(days=30),
}


def quality_status_from_score(score: float) -> str:
    if score >= 0.999:
        return "VALID"
    if score <= 0:
        return "FAILED"
    return "INCOMPLETE"


class DataCatalogService:
    def __init__(self, db: Session):
        self.db = db

    def create_entry(
        self,
        *,
        dataset_type: str,
        source: str,
        row_count: int,
        snapshot: DataSnapshot | None = None,
        quality_report: DataQualityReport | None = None,
        source_ref: str | None = None,
        usable_for_trading: bool = False,
        lineage_json: dict[str, Any] | None = None,
        contract_json: dict[str, Any] | None = None,
    ) -> DataCatalogEntry:
        score = float(quality_report.score) if quality_report else 0
        quality_status = quality_status_from_score(score)
        entry = DataCatalogEntry(
            dataset_type=dataset_type,
            source=source,
            source_ref=source_ref,
            data_snapshot_id=snapshot.id if snapshot else None,
            quality_report_id=quality_report.id if quality_report else None,
            row_count=row_count,
            quality_status=quality_status,
            usable_for_trading=usable_for_trading and quality_status == "VALID",
            lineage_json=lineage_json or {},
            contract_json=contract_json or {},
        )
        self.db.add(entry)
        self.db.flush()
        write_audit_log(
            self.db,
            action="data_catalog.entry_created",
            entity_type="DataCatalogEntry",
            entity_id=entry.id,
            payload_json={
                "dataset_type": dataset_type,
                "source": source,
                "snapshot_id": entry.data_snapshot_id,
                "quality_report_id": entry.quality_report_id,
                "quality_status": entry.quality_status,
                "usable_for_trading": entry.usable_for_trading,
                "row_count": row_count,
            },
            actor_id="v4-data-catalog-service",
        )
        return entry

    def promotion_status(self, entry_id: str) -> dict[str, Any]:
        entry = self.db.get(DataCatalogEntry, entry_id)
        if entry is None:
            raise DataCatalogNotFoundError("data catalog entry not found")
        return self._promotion_view(entry)

    def snapshot_decision_gate(self, snapshot_id: str, *, decision_scope: str) -> dict[str, Any]:
        """Evaluate the exact snapshot a downstream service intends to consume.

        A broad trust report is not sufficient here: callers must prove that the
        referenced snapshot itself is catalogued, valid, fresh, explicitly at
        the trusted promotion stage, and still eligible for trust now.
        """
        checked_at = datetime.now(timezone.utc)
        entry = self.db.scalar(
            select(DataCatalogEntry)
            .where(DataCatalogEntry.data_snapshot_id == snapshot_id)
            .order_by(DataCatalogEntry.created_at.desc(), DataCatalogEntry.id.desc())
            .limit(1)
        )
        blockers: list[str] = []
        snapshot = self.db.get(DataSnapshot, snapshot_id)
        quality_report = None
        if snapshot is None:
            blockers.append("snapshot_not_found")
        if entry is None:
            blockers.append("snapshot_not_catalogued")
        else:
            quality_report = self.db.get(DataQualityReport, entry.quality_report_id) if entry.quality_report_id else None
            allowed_scopes = list((entry.contract_json or {}).get("allowed_decision_scopes") or [])
            if allowed_scopes and decision_scope not in allowed_scopes:
                blockers.append("decision_scope_not_allowed")
            if quality_report is None:
                blockers.append("quality_report_missing")
            if entry.quality_status != "VALID":
                blockers.append("quality_not_valid")
            if self._stage_of(entry) != "trusted":
                blockers.append("promotion_stage_not_trusted")
            if self._eligible_stage(entry) != "trusted":
                blockers.append("trust_evidence_no_longer_eligible")
            if not entry.usable_for_trading:
                blockers.append("trusted_usage_flag_missing")
            threshold = DATA_TRUST_FRESHNESS_THRESHOLDS.get(entry.dataset_type, timedelta(days=30))
            as_of = self._effective_as_of(entry=entry, snapshot=snapshot)
            if as_of is None:
                blockers.append("snapshot_as_of_missing")
            elif checked_at - as_of > threshold:
                blockers.append("snapshot_stale")

        gate = {
            "decision_scope": decision_scope,
            "snapshot_id": snapshot_id,
            "entry_id": entry.id if entry else None,
            "dataset_type": entry.dataset_type if entry else None,
            "promotion_stage": self._stage_of(entry) if entry else None,
            "quality_status": entry.quality_status if entry else None,
            "quality_report_id": quality_report.id if quality_report else None,
            "allowed_decision_scopes": allowed_scopes if entry else [],
            "status": "trusted" if not blockers else "blocked",
            "blockers": dedupe(blockers),
            "checked_at": checked_at.isoformat(),
            "execution_available": False,
        }
        write_audit_log(
            self.db,
            action="data_catalog.downstream_trust_gate_passed" if not blockers else "data_catalog.downstream_trust_gate_blocked",
            entity_type="DataSnapshot",
            entity_id=snapshot_id,
            payload_json={
                "decision_scope": decision_scope,
                "entry_id": gate["entry_id"],
                "status": gate["status"],
                "blockers": gate["blockers"],
                "execution_available": False,
            },
            actor_id="data-catalog-decision-gate",
        )
        self.db.commit()
        return gate

    def require_trusted_snapshot(self, snapshot_id: str, *, decision_scope: str) -> dict[str, Any]:
        gate = self.snapshot_decision_gate(snapshot_id, decision_scope=decision_scope)
        if gate["status"] != "trusted":
            raise DataTrustGateError(
                f"{decision_scope} blocked: referenced data snapshot is not trusted ({', '.join(gate['blockers'])})",
                gate=gate,
            )
        return gate

    def promote_entry(self, entry_id: str) -> dict[str, Any]:
        """Evidence-driven promotion through raw → reviewed → trusted.

        - reviewed requires quality_status VALID (the data passed its checks).
        - trusted additionally requires no unresolved critical/error
          reconciliation breaks touching this dataset's snapshot.
        usable_for_trading is bound to the 'trusted' stage only. Promotion is
        idempotent, fail-closed (missing evidence keeps the lower stage), never
        skips a stage, and is fully audited. It cannot demote here — demotion
        happens only when the underlying quality/reconciliation evidence
        changes and promote is re-run.
        """
        entry = self.db.get(DataCatalogEntry, entry_id)
        if entry is None:
            raise DataCatalogNotFoundError("data catalog entry not found")

        current_stage = self._stage_of(entry)
        target_stage = self._eligible_stage(entry)
        stages = ["raw", "reviewed", "trusted"]
        # Advance at most one step per call so promotion is auditable and never
        # jumps from raw straight to trusted without recording 'reviewed'.
        current_index = stages.index(current_stage)
        target_index = stages.index(target_stage)
        if target_index > current_index:
            new_stage = stages[current_index + 1]
        else:
            new_stage = target_stage  # holds or reflects an evidence downgrade

        lineage = dict(entry.lineage_json or {})
        history = list(lineage.get("promotion_history") or [])
        if new_stage != current_stage:
            history.append(
                {
                    "from": current_stage,
                    "to": new_stage,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "quality_status": entry.quality_status,
                }
            )
        lineage["promotion_stage"] = new_stage
        lineage["promotion_history"] = history[-20:]
        entry.lineage_json = lineage
        entry.usable_for_trading = new_stage == "trusted"
        self.db.add(entry)
        self.db.flush()
        write_audit_log(
            self.db,
            action="data_catalog.entry_promoted",
            entity_type="DataCatalogEntry",
            entity_id=entry.id,
            payload_json={
                "from_stage": current_stage,
                "to_stage": new_stage,
                "eligible_stage": target_stage,
                "usable_for_trading": entry.usable_for_trading,
                "quality_status": entry.quality_status,
            },
            actor_id="v4-data-catalog-service",
        )
        self.db.commit()
        self.db.refresh(entry)
        return self._promotion_view(entry)

    def _stage_of(self, entry: DataCatalogEntry) -> str:
        return str((entry.lineage_json or {}).get("promotion_stage") or "raw")

    def _open_critical_breaks(self, entry: DataCatalogEntry) -> int:
        """Count unresolved critical/error reconciliation breaks. Absent an
        explicit resolved flag on the model, severity gates trust: any
        critical/error break blocks the trusted stage until reconciliation is
        clean."""
        from app.models import ReconciliationBreak

        return int(
            self.db.scalar(
                select(func.count())
                .select_from(ReconciliationBreak)
                .where(ReconciliationBreak.severity.in_(["critical", "error"]))
            )
            or 0
        )

    def _eligible_stage(self, entry: DataCatalogEntry) -> str:
        if entry.quality_status != "VALID":
            return "raw"
        if self._open_critical_breaks(entry) > 0:
            return "reviewed"
        return "trusted"

    def _promotion_view(self, entry: DataCatalogEntry) -> dict[str, Any]:
        stage = self._stage_of(entry)
        eligible = self._eligible_stage(entry)
        blockers: list[str] = []
        if entry.quality_status != "VALID":
            blockers.append("quality_not_valid")
        elif self._open_critical_breaks(entry) > 0:
            blockers.append("open_critical_reconciliation_breaks")
        return {
            "entry_id": entry.id,
            "dataset_type": entry.dataset_type,
            "current_stage": stage,
            "eligible_stage": eligible,
            "can_advance": eligible != stage and ["raw", "reviewed", "trusted"].index(eligible) > ["raw", "reviewed", "trusted"].index(stage),
            "usable_for_trading": entry.usable_for_trading,
            "quality_status": entry.quality_status,
            "trusted_blockers": blockers,
            "promotion_history": list((entry.lineage_json or {}).get("promotion_history") or []),
            "execution_available": False,
        }

    def list_entries(
        self,
        *,
        dataset_type: str | None = None,
        quality_status: str | None = None,
        usable_for_trading: bool | None = None,
        limit: int = 50,
    ) -> list[DataCatalogEntry]:
        query = select(DataCatalogEntry)
        if dataset_type:
            query = query.where(DataCatalogEntry.dataset_type == dataset_type)
        if quality_status:
            query = query.where(DataCatalogEntry.quality_status == quality_status)
        if usable_for_trading is not None:
            query = query.where(DataCatalogEntry.usable_for_trading.is_(usable_for_trading))
        query = query.order_by(DataCatalogEntry.created_at.desc(), DataCatalogEntry.id.desc()).limit(limit)
        return list(self.db.scalars(query).all())

    def overview(self, *, limit: int = 8) -> dict[str, Any]:
        entries = self.list_entries(limit=500)
        quality_counts: dict[str, int] = {}
        for entry in entries:
            quality_counts[entry.quality_status] = quality_counts.get(entry.quality_status, 0) + 1

        all_blockers = [
            entry
            for entry in entries
            if (not entry.usable_for_trading) or entry.quality_status != "VALID"
        ]
        blockers = all_blockers[:limit]
        latest_entries = entries[:limit]
        return {
            "total_entries": len(entries),
            "usable_for_trading_count": sum(1 for entry in entries if entry.usable_for_trading),
            "blocked_count": len(all_blockers),
            "quality_counts": quality_counts,
            "latest_entries": latest_entries,
            "blockers": blockers,
        }

    def trust_report(self, *, decision_scope: str = "research") -> dict[str, Any]:
        if decision_scope not in DATA_TRUST_REQUIREMENTS:
            raise ValueError(f"unsupported data trust scope: {decision_scope}")

        checked_at = datetime.now(timezone.utc)
        entries = self.list_entries(limit=500)
        latest_by_dataset: dict[str, DataCatalogEntry] = {}
        for entry in entries:
            latest_by_dataset.setdefault(entry.dataset_type, entry)

        required_datasets = DATA_TRUST_REQUIREMENTS[decision_scope]
        items = [
            self._trust_item(
                dataset_type=dataset_type,
                requires_trading_usable=requires_trading_usable,
                entry=latest_by_dataset.get(dataset_type),
                checked_at=checked_at,
            )
            for dataset_type, requires_trading_usable in required_datasets.items()
        ]
        blocked_count = sum(1 for item in items if item["status"] in {"missing", "invalid", "blocked", "stale"})
        review_only_count = sum(1 for item in items if item["status"] == "review_only")
        trusted_count = sum(1 for item in items if item["status"] == "trusted")
        if blocked_count:
            overall_status = "blocked"
        elif review_only_count:
            overall_status = "review_only"
        else:
            overall_status = "trusted"

        recommended_actions: list[str] = []
        for item in items:
            for action in item["recommended_actions"]:
                if action not in recommended_actions:
                    recommended_actions.append(action)
        if not recommended_actions:
            recommended_actions.append("Continue monitoring freshness and quality before downstream decisions.")

        return {
            "decision_scope": decision_scope,
            "overall_status": overall_status,
            "checked_at": checked_at,
            "trusted_count": trusted_count,
            "review_only_count": review_only_count,
            "blocked_count": blocked_count,
            "items": items,
            "recommended_actions": recommended_actions,
            "execution_available": False,
        }

    def entry_detail(self, entry_id: str) -> dict[str, Any]:
        entry = self.db.get(DataCatalogEntry, entry_id)
        if entry is None:
            raise DataCatalogNotFoundError("data catalog entry not found")

        snapshot = self.db.get(DataSnapshot, entry.data_snapshot_id) if entry.data_snapshot_id else None
        quality_report = self.db.get(DataQualityReport, entry.quality_report_id) if entry.quality_report_id else None
        blockers = catalog_blockers(entry=entry, snapshot=snapshot, quality_report=quality_report)
        contract_status = "usable" if entry.usable_for_trading and not blockers else "blocked" if blockers else "review_only"
        recommended_actions = catalog_recommended_actions(
            entry=entry,
            snapshot=snapshot,
            quality_report=quality_report,
            blockers=blockers,
        )
        return {
            "entry": entry,
            "snapshot": snapshot,
            "quality_report": quality_report,
            "contract_status": contract_status,
            "blockers": blockers,
            "recommended_actions": recommended_actions,
            "related_action": related_action_for_entry(entry),
            "execution_available": False,
        }

    def version_entry_snapshot(self, entry_id: str) -> dict[str, Any]:
        entry = self.db.get(DataCatalogEntry, entry_id)
        if entry is None:
            raise DataCatalogNotFoundError("data catalog entry not found")
        snapshot = self.db.get(DataSnapshot, entry.data_snapshot_id) if entry.data_snapshot_id else None
        if snapshot is None:
            raise DataCatalogNotFoundError("data catalog entry has no linked snapshot")

        content_hash = stable_snapshot_content_hash(snapshot)
        dataset_version = f"sha256:{content_hash}"
        checked_at = datetime.now(timezone.utc)
        snapshot.metadata_json = {
            **(snapshot.metadata_json or {}),
            "dataset_version": dataset_version,
            "stable_content_hash": content_hash,
            "immutable_replay": True,
            "replayable": True,
            "versioned_at": checked_at.isoformat(),
            "execution_available": False,
        }
        entry.lineage_json = {
            **(entry.lineage_json or {}),
            "dataset_version": dataset_version,
            "stable_content_hash": content_hash,
            "versioned_snapshot_id": snapshot.id,
        }
        entry.contract_json = {
            **(entry.contract_json or {}),
            "dataset_version": dataset_version,
            "replayable": True,
            "execution_available": False,
        }
        write_audit_log(
            self.db,
            action="data_catalog.snapshot_versioned",
            entity_type="DataCatalogEntry",
            entity_id=entry.id,
            payload_json={
                "snapshot_id": snapshot.id,
                "dataset_version": dataset_version,
                "execution_available": False,
            },
            actor_id="data-catalog-service",
        )
        self.db.commit()
        return {
            "entry_id": entry.id,
            "snapshot_id": snapshot.id,
            "dataset_version": dataset_version,
            "stable_content_hash": content_hash,
            "versioned_at": checked_at,
            "replayable": True,
            "execution_available": False,
        }

    def compare_entry_snapshots(self, entry_id: str, other_entry_id: str) -> dict[str, Any]:
        """Diff two catalog entries' snapshots for drift/regression review.

        Answers "did this dataset change between two versions?" — the core
        check when re-importing a source or validating a replay copy against
        its origin. Compares stable content hashes (fast identical/changed
        verdict), then row-level or field-level differences. Review-only: no
        data is written except the audit record of the comparison."""
        entry_a = self.db.get(DataCatalogEntry, entry_id)
        if entry_a is None:
            raise DataCatalogNotFoundError("data catalog entry not found")
        entry_b = self.db.get(DataCatalogEntry, other_entry_id)
        if entry_b is None:
            raise DataCatalogNotFoundError("comparison data catalog entry not found")
        snapshot_a = self.db.get(DataSnapshot, entry_a.data_snapshot_id) if entry_a.data_snapshot_id else None
        snapshot_b = self.db.get(DataSnapshot, entry_b.data_snapshot_id) if entry_b.data_snapshot_id else None
        if snapshot_a is None or snapshot_b is None:
            raise DataCatalogNotFoundError("both catalog entries must have a linked snapshot to compare")

        hash_a = stable_snapshot_content_hash(snapshot_a)
        hash_b = stable_snapshot_content_hash(snapshot_b)
        version_a = (snapshot_a.metadata_json or {}).get("dataset_version") or f"sha256:{hash_a}"
        version_b = (snapshot_b.metadata_json or {}).get("dataset_version") or f"sha256:{hash_b}"
        content_identical = hash_a == hash_b

        warnings: list[str] = []
        if entry_a.dataset_type != entry_b.dataset_type:
            warnings.append("dataset_type_mismatch")
        if snapshot_a.snapshot_type != snapshot_b.snapshot_type:
            warnings.append("snapshot_type_mismatch")

        rows_a = _extract_snapshot_rows(snapshot_a.data_json)
        rows_b = _extract_snapshot_rows(snapshot_b.data_json)
        row_diff = None
        field_diff = None
        if rows_a is not None and rows_b is not None:
            row_diff = _diff_rows(rows_a, rows_b)
        else:
            field_diff = _diff_fields(snapshot_a.data_json, snapshot_b.data_json)

        verdict = "identical" if content_identical else "content_changed"
        response = {
            "verdict": verdict,
            "content_identical": content_identical,
            "base": {
                "entry_id": entry_a.id,
                "snapshot_id": snapshot_a.id,
                "dataset_type": entry_a.dataset_type,
                "source": entry_a.source,
                "dataset_version": version_a,
                "stable_content_hash": hash_a,
                "row_count": entry_a.row_count,
            },
            "compared": {
                "entry_id": entry_b.id,
                "snapshot_id": snapshot_b.id,
                "dataset_type": entry_b.dataset_type,
                "source": entry_b.source,
                "dataset_version": version_b,
                "stable_content_hash": hash_b,
                "row_count": entry_b.row_count,
            },
            "row_diff": row_diff,
            "field_diff": field_diff,
            "warnings": dedupe(warnings),
            "review_only": True,
            "execution_available": False,
        }
        write_audit_log(
            self.db,
            action="data_catalog.snapshots_compared",
            entity_type="DataCatalogEntry",
            entity_id=entry_a.id,
            payload_json={
                "compared_entry_id": entry_b.id,
                "verdict": verdict,
                "base_hash": hash_a,
                "compared_hash": hash_b,
                "execution_available": False,
            },
            actor_id="data-catalog-service",
        )
        self.db.commit()
        return response

    def replay_preflight(self, entry_id: str) -> dict[str, Any]:
        entry = self.db.get(DataCatalogEntry, entry_id)
        if entry is None:
            raise DataCatalogNotFoundError("data catalog entry not found")
        snapshot = self.db.get(DataSnapshot, entry.data_snapshot_id) if entry.data_snapshot_id else None
        quality_report = self.db.get(DataQualityReport, entry.quality_report_id) if entry.quality_report_id else None
        blockers: list[str] = []
        warnings: list[str] = []
        next_actions: list[str] = []

        if snapshot is None:
            blockers.append("missing_snapshot")
            next_actions.append("Re-import the dataset so a DataSnapshot exists before replay.")
        if quality_report is None:
            blockers.append("missing_quality_report")
            next_actions.append("Generate or repair the quality report before replay.")
        if entry.contract_json.get("execution_available") is not False:
            blockers.append("execution_boundary_not_explicit")
            next_actions.append("Set execution_available=false in the data contract before replay.")

        dataset_version = None
        stable_hash = None
        if snapshot is not None:
            stable_hash = stable_snapshot_content_hash(snapshot)
            dataset_version = (
                (snapshot.metadata_json or {}).get("dataset_version")
                or (entry.lineage_json or {}).get("dataset_version")
                or f"sha256:{stable_hash}"
            )
            metadata_hash = (snapshot.metadata_json or {}).get("stable_content_hash")
            if metadata_hash and metadata_hash != stable_hash:
                blockers.append("snapshot_hash_drift")
                next_actions.append("Re-version the snapshot; current payload no longer matches recorded stable hash.")
            if not (snapshot.metadata_json or {}).get("dataset_version"):
                warnings.append("snapshot_not_explicitly_versioned")
                next_actions.append("Click version snapshot first so replay has an explicit dataset version.")

        if entry.usable_for_trading:
            warnings.append("source_entry_was_trading_usable_but_replay_will_be_review_only")
        if not blockers:
            next_actions.append("Replay can create a review-only copy for audit, testing, and regression comparison.")

        return {
            "entry_id": entry.id,
            "snapshot_id": snapshot.id if snapshot else None,
            "quality_report_id": quality_report.id if quality_report else None,
            "dataset_type": entry.dataset_type,
            "source": entry.source,
            "dataset_version": dataset_version,
            "stable_content_hash": stable_hash,
            "status": "ready" if not blockers else "blocked",
            "can_replay": not blockers,
            "blockers": dedupe(blockers),
            "warnings": dedupe(warnings),
            "next_actions": dedupe(next_actions),
            "replay_will_be_review_only": True,
            "execution_available": False,
        }

    def replay_entry_snapshot(self, entry_id: str) -> dict[str, Any]:
        preflight = self.replay_preflight(entry_id)
        if not preflight["can_replay"]:
            return {**preflight, "replay_created": False}

        entry = self.db.get(DataCatalogEntry, entry_id)
        if entry is None:
            raise DataCatalogNotFoundError("data catalog entry not found")
        snapshot = self.db.get(DataSnapshot, entry.data_snapshot_id) if entry.data_snapshot_id else None
        quality_report = self.db.get(DataQualityReport, entry.quality_report_id) if entry.quality_report_id else None
        if snapshot is None or quality_report is None:
            raise DataCatalogNotFoundError("data catalog entry is not replayable")

        replayed_at = datetime.now(timezone.utc)
        stable_hash = str(preflight["stable_content_hash"])
        dataset_version = str(preflight["dataset_version"])
        replay_snapshot = DataSnapshot(
            snapshot_type=snapshot.snapshot_type,
            as_of=snapshot.as_of,
            data_json=snapshot.data_json,
            metadata_json={
                **(snapshot.metadata_json or {}),
                "dataset_version": dataset_version,
                "stable_content_hash": stable_hash,
                "replay": True,
                "replayed_at": replayed_at.isoformat(),
                "replay_source_snapshot_id": snapshot.id,
                "replay_source_entry_id": entry.id,
                "execution_available": False,
            },
        )
        self.db.add(replay_snapshot)
        self.db.flush()
        replay_quality = DataQualityReport(
            data_snapshot_id=replay_snapshot.id,
            source=f"{quality_report.source}:replay",
            metric_type=quality_report.metric_type,
            score=float(quality_report.score),
            details_json={
                **(quality_report.details_json or {}),
                "replay": True,
                "source_quality_report_id": quality_report.id,
                "source_snapshot_id": snapshot.id,
                "dataset_version": dataset_version,
                "execution_available": False,
            },
        )
        self.db.add(replay_quality)
        self.db.flush()
        replay_entry = DataCatalogEntry(
            dataset_type=entry.dataset_type,
            source=f"{entry.source}:replay",
            source_ref=f"replay:{dataset_version}",
            data_snapshot_id=replay_snapshot.id,
            quality_report_id=replay_quality.id,
            row_count=entry.row_count,
            quality_status=entry.quality_status,
            usable_for_trading=False,
            lineage_json={
                **(entry.lineage_json or {}),
                "replay": True,
                "source_catalog_entry_id": entry.id,
                "source_snapshot_id": snapshot.id,
                "source_quality_report_id": quality_report.id,
                "dataset_version": dataset_version,
                "stable_content_hash": stable_hash,
            },
            contract_json={
                **(entry.contract_json or {}),
                "replay": True,
                "replayable": True,
                "execution_available": False,
                "usable_for_trading": False,
            },
        )
        self.db.add(replay_entry)
        self.db.flush()
        write_audit_log(
            self.db,
            action="data_catalog.snapshot_replayed",
            entity_type="DataCatalogEntry",
            entity_id=replay_entry.id,
            payload_json={
                "source_entry_id": entry.id,
                "source_snapshot_id": snapshot.id,
                "replay_snapshot_id": replay_snapshot.id,
                "dataset_version": dataset_version,
                "execution_available": False,
            },
            actor_id="data-catalog-service",
        )
        self.db.commit()
        return {
            **preflight,
            "replay_created": True,
            "replay_snapshot": data_snapshot_payload(replay_snapshot),
            "replay_quality_report": data_quality_report_payload(replay_quality),
            "replay_catalog_entry": data_catalog_entry_payload(replay_entry),
            "next_actions": ["Use this replay copy for audit, regression comparison, or manual review. It remains review-only."],
            "execution_available": False,
        }

    def provenance_report(self, *, decision_scope: str = "research", limit: int = 50) -> dict[str, Any]:
        if decision_scope not in DATA_TRUST_REQUIREMENTS:
            raise ValueError(f"unsupported data trust scope: {decision_scope}")
        checked_at = datetime.now(timezone.utc)
        trust_report = self.trust_report(decision_scope=decision_scope)
        entries = self.list_entries(limit=limit)
        items = [self._provenance_item(entry=entry, checked_at=checked_at) for entry in entries]
        required_dataset_types = set(DATA_TRUST_REQUIREMENTS[decision_scope])
        required_items = [item for item in items if item["dataset_type"] in required_dataset_types]
        blockers = []
        for item in required_items:
            blockers.extend(item["blockers"])
        missing_required = [
            dataset_type
            for dataset_type in sorted(required_dataset_types)
            if dataset_type not in {item["dataset_type"] for item in required_items}
        ]
        blockers.extend(f"Missing provenance for required dataset: {dataset_type}." for dataset_type in missing_required)
        if blockers:
            provenance_status = "blocked"
        elif any(item["status"] == "review_required" for item in required_items):
            provenance_status = "review_required"
        else:
            provenance_status = "trusted"
        return {
            "decision_scope": decision_scope,
            "checked_at": checked_at,
            "provenance_status": provenance_status,
            "trust_status": trust_report["overall_status"],
            "required_dataset_types": sorted(required_dataset_types),
            "blockers": dedupe(blockers),
            "recommended_actions": dedupe(
                trust_report["recommended_actions"]
                + [action for item in required_items for action in item["recommended_actions"]]
            ),
            "items": items,
            "execution_available": False,
        }

    def contract_enforcement_report(self, *, decision_scope: str = "research", limit: int = 50) -> dict[str, Any]:
        if decision_scope not in DATA_TRUST_REQUIREMENTS:
            raise ValueError(f"unsupported data trust scope: {decision_scope}")
        checked_at = datetime.now(timezone.utc)
        provenance = self.provenance_report(decision_scope=decision_scope, limit=limit)
        trust = self.trust_report(decision_scope=decision_scope)
        required_dataset_types = set(DATA_TRUST_REQUIREMENTS[decision_scope])
        items = []
        for item in provenance["items"]:
            if item["dataset_type"] not in required_dataset_types:
                continue
            checks = [
                enforcement_check(
                    "hash",
                    "Payload hash",
                    "ok" if item["raw_payload_hash"] or item["computed_snapshot_hash"] else "block",
                    {
                        "raw_payload_hash": item["raw_payload_hash"],
                        "computed_snapshot_hash": item["computed_snapshot_hash"],
                    },
                ),
                enforcement_check(
                    "contract_version",
                    "Contract version",
                    "ok" if item["contract_version"] != "unspecified" else "block",
                    {"contract_version": item["contract_version"]},
                ),
                enforcement_check(
                    "quality",
                    "Quality status",
                    "ok" if item["quality_status"] == "VALID" else "block",
                    {"quality_status": item["quality_status"], "quality_score": item["quality_score"]},
                ),
                enforcement_check(
                    "freshness",
                    "Freshness",
                    "ok"
                    if item["age_seconds"] is None or item["age_seconds"] <= item["threshold_seconds"]
                    else "block",
                    {"age_seconds": item["age_seconds"], "threshold_seconds": item["threshold_seconds"]},
                ),
                enforcement_check(
                    "execution_boundary",
                    "Execution boundary",
                    "ok" if item["execution_available"] is False else "block",
                    {"execution_available": item["execution_available"]},
                ),
            ]
            item_blockers = [f"{item['dataset_type']}:{check['key']}" for check in checks if check["status"] == "block"]
            items.append(
                {
                    "entry_id": item["entry_id"],
                    "dataset_type": item["dataset_type"],
                    "source": item["source"],
                    "status": "blocked" if item_blockers else "enforced",
                    "blockers": item_blockers,
                    "checks": checks,
                    "recommended_actions": item["recommended_actions"],
                    "execution_available": False,
                }
            )
        present_dataset_types = {item["dataset_type"] for item in items}
        missing_required = sorted(required_dataset_types - present_dataset_types)
        blockers = [blocker for item in items for blocker in item["blockers"]]
        blockers.extend(f"{dataset_type}:missing_required_dataset" for dataset_type in missing_required)
        status = "blocked" if blockers or provenance["blockers"] or trust["overall_status"] == "blocked" else "enforced"
        return {
            "decision_scope": decision_scope,
            "checked_at": checked_at,
            "enforcement_status": status,
            "trust_status": trust["overall_status"],
            "provenance_status": provenance["provenance_status"],
            "required_dataset_types": sorted(required_dataset_types),
            "missing_required_dataset_types": missing_required,
            "blockers": dedupe(blockers + provenance["blockers"]),
            "next_actions": dedupe(
                provenance["recommended_actions"]
                + trust["recommended_actions"]
                + ["Keep data enforcement as a decision gate only; it must never unlock execution by itself."]
            ),
            "items": items,
            "can_unlock_order_approval": False,
            "execution_available": False,
        }

    def _trust_item(
        self,
        *,
        dataset_type: str,
        requires_trading_usable: bool,
        entry: DataCatalogEntry | None,
        checked_at: datetime,
    ) -> dict[str, Any]:
        threshold = DATA_TRUST_FRESHNESS_THRESHOLDS.get(dataset_type, timedelta(days=30))
        if entry is None:
            return {
                "dataset_type": dataset_type,
                "required": True,
                "requires_trading_usable": requires_trading_usable,
                "status": "missing",
                "entry": None,
                "snapshot_id": None,
                "quality_report_id": None,
                "quality_status": None,
                "quality_score": None,
                "age_seconds": None,
                "threshold_seconds": int(threshold.total_seconds()),
                "blockers": [f"Missing required dataset: {dataset_type}."],
                "recommended_actions": [f"Import or refresh {dataset_type} through a read-only source."],
            }

        snapshot = self.db.get(DataSnapshot, entry.data_snapshot_id) if entry.data_snapshot_id else None
        quality_report = self.db.get(DataQualityReport, entry.quality_report_id) if entry.quality_report_id else None
        blockers = catalog_blockers(entry=entry, snapshot=snapshot, quality_report=quality_report)
        as_of = self._effective_as_of(entry=entry, snapshot=snapshot)
        age_seconds = int((checked_at - as_of).total_seconds()) if as_of else None
        is_stale = age_seconds is not None and age_seconds > int(threshold.total_seconds())
        if is_stale:
            blockers.append(f"Dataset is stale: age {age_seconds}s exceeds {int(threshold.total_seconds())}s.")

        review_only_blockers = [blocker for blocker in blockers if "review-only" in blocker]
        hard_blockers = [blocker for blocker in blockers if blocker not in review_only_blockers]
        if snapshot is None or quality_report is None or entry.quality_status != "VALID":
            status = "invalid"
        elif is_stale:
            status = "stale"
        elif hard_blockers:
            status = "blocked"
        elif review_only_blockers or (requires_trading_usable and not entry.usable_for_trading):
            status = "review_only"
        else:
            status = "trusted"

        recommended_actions = catalog_recommended_actions(
            entry=entry,
            snapshot=snapshot,
            quality_report=quality_report,
            blockers=blockers,
        )
        if requires_trading_usable and not entry.usable_for_trading:
            recommended_actions.append("Use as context only; do not let this dataset unlock order approval or execution.")

        return {
            "dataset_type": dataset_type,
            "required": True,
            "requires_trading_usable": requires_trading_usable,
            "status": status,
            "entry": entry,
            "snapshot_id": snapshot.id if snapshot else None,
            "quality_report_id": quality_report.id if quality_report else None,
            "quality_status": entry.quality_status,
            "quality_score": float(quality_report.score) if quality_report else None,
            "age_seconds": age_seconds,
            "threshold_seconds": int(threshold.total_seconds()),
            "blockers": blockers,
            "recommended_actions": recommended_actions,
        }

    def _effective_as_of(self, *, entry: DataCatalogEntry, snapshot: DataSnapshot | None) -> datetime | None:
        as_of = snapshot.as_of if snapshot else entry.created_at
        if as_of is None:
            return None
        return as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)

    def _provenance_item(self, *, entry: DataCatalogEntry, checked_at: datetime) -> dict[str, Any]:
        snapshot = self.db.get(DataSnapshot, entry.data_snapshot_id) if entry.data_snapshot_id else None
        quality_report = self.db.get(DataQualityReport, entry.quality_report_id) if entry.quality_report_id else None
        blockers = catalog_blockers(entry=entry, snapshot=snapshot, quality_report=quality_report)
        lineage = dict(entry.lineage_json or {})
        contract = dict(entry.contract_json or {})
        raw_hash = lineage.get("raw_payload_hash") or lineage.get("payload_hash") or lineage.get("snapshot_hash")
        computed_hash = snapshot_payload_hash(snapshot)
        contract_version = contract.get("contract_version") or contract.get("schema")
        if not contract_version and contract.get("execution_available") is False and contract:
            contract_version = f"{entry.dataset_type}_contract_v1"
        contract_version = contract_version or "unspecified"
        if not raw_hash and not computed_hash:
            blockers.append("Dataset provenance lacks raw_payload_hash or computable snapshot hash.")
        if contract_version == "unspecified":
            blockers.append("Dataset contract version/schema is unspecified.")
        if contract.get("execution_available") is not False:
            blockers.append("Data contract must explicitly keep execution_available=false.")

        as_of = self._effective_as_of(entry=entry, snapshot=snapshot)
        age_seconds = int((checked_at - as_of).total_seconds()) if as_of else None
        threshold = DATA_TRUST_FRESHNESS_THRESHOLDS.get(entry.dataset_type, timedelta(days=30))
        if age_seconds is not None and age_seconds > int(threshold.total_seconds()):
            blockers.append(f"Dataset is stale: age {age_seconds}s exceeds {int(threshold.total_seconds())}s.")

        if blockers:
            status = "blocked"
        elif not entry.usable_for_trading:
            status = "review_required"
        else:
            status = "trusted"
        return {
            "entry_id": entry.id,
            "dataset_type": entry.dataset_type,
            "source": entry.source,
            "source_ref": entry.source_ref,
            "snapshot_id": snapshot.id if snapshot else None,
            "quality_report_id": quality_report.id if quality_report else None,
            "status": status,
            "quality_status": entry.quality_status,
            "quality_score": float(quality_report.score) if quality_report else None,
            "row_count": entry.row_count,
            "usable_for_trading": entry.usable_for_trading,
            "raw_payload_hash": raw_hash,
            "computed_snapshot_hash": computed_hash,
            "contract_version": contract_version,
            "lineage_keys": sorted(lineage.keys()),
            "contract_keys": sorted(contract.keys()),
            "age_seconds": age_seconds,
            "threshold_seconds": int(threshold.total_seconds()),
            "blockers": dedupe(blockers),
            "recommended_actions": catalog_recommended_actions(
                entry=entry,
                snapshot=snapshot,
                quality_report=quality_report,
                blockers=blockers,
            ),
            "execution_available": False,
        }


def catalog_blockers(
    *,
    entry: DataCatalogEntry,
    snapshot: DataSnapshot | None,
    quality_report: DataQualityReport | None,
) -> list[str]:
    blockers: list[str] = []
    if snapshot is None:
        blockers.append("Missing linked DataSnapshot; dataset cannot be trusted downstream.")
    if quality_report is None:
        blockers.append("Missing linked DataQualityReport; quality is unknown.")
    if entry.quality_status != "VALID":
        blockers.append(f"Quality status is {entry.quality_status}, not VALID.")
    if quality_report is not None and float(quality_report.score) < 0.999:
        blockers.append(f"Quality score is {float(quality_report.score):.3f}; full completeness is required.")
    if not entry.usable_for_trading:
        blockers.append("Dataset is review-only and cannot be used for trading decisions.")
    if entry.contract_json.get("execution_available") is not False:
        blockers.append("Data contract must explicitly keep execution_available=false.")
    return blockers


def catalog_recommended_actions(
    *,
    entry: DataCatalogEntry,
    snapshot: DataSnapshot | None,
    quality_report: DataQualityReport | None,
    blockers: list[str],
) -> list[str]:
    actions: list[str] = []
    if snapshot is None:
        actions.append("Re-import the dataset through a read-only data source or CSV import so a DataSnapshot is recorded.")
    if quality_report is None or entry.quality_status != "VALID":
        actions.append("Refresh the source and resolve skipped rows before using this dataset downstream.")
    if not entry.usable_for_trading:
        actions.append("Keep this dataset in review-only workflows until reconciliation and quality policy explicitly allow trading-decision use.")
    if entry.dataset_type.startswith("csv_"):
        actions.append("Map the CSV schema, inspect skipped rows, and reconcile imported positions against the investment ledger.")
    if entry.dataset_type == "read_only_account":
        actions.append("Run ledger sync and reconciliation after account snapshot refresh.")
    if entry.dataset_type in {"market_quotes", "market_candles"} and not blockers:
        actions.append("Use this dataset as research input only; order drafts must still pass thesis, gates, risk, behavior, and approval.")
    if not actions:
        actions.append("No remediation required; keep monitoring freshness and lineage before downstream use.")
    return actions


def related_action_for_entry(entry: DataCatalogEntry) -> dict[str, Any]:
    if entry.dataset_type == "read_only_account":
        return {"label": "Run ledger sync", "target": "/ledger/sync", "method": "POST"}
    if entry.dataset_type.startswith("csv_"):
        return {"label": "Review CSV import and reconcile", "target": "/ledger/reconcile", "method": "POST"}
    if entry.dataset_type in {"market_quotes", "market_candles"}:
        return {"label": "Refresh market data", "target": "/data-sources/connections/{connection_id}/import-quotes", "method": "POST"}
    return {"label": "Review dataset", "target": "/data-catalog/entries", "method": "GET"}


def enforcement_check(key: str, label: str, status: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"key": key, "label": label, "status": status, "evidence": evidence}


def snapshot_payload_hash(snapshot: DataSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    payload = {
        "snapshot_type": snapshot.snapshot_type,
        "data_json": snapshot.data_json,
        "metadata_json": snapshot.metadata_json,
        "as_of": snapshot.as_of.isoformat() if snapshot.as_of else None,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_snapshot_content_hash(snapshot: DataSnapshot) -> str:
    metadata = dict(snapshot.metadata_json or {})
    for key in [
        "dataset_version",
        "stable_content_hash",
        "immutable_replay",
        "replayable",
        "versioned_at",
        "replay",
        "replayed_at",
        "replay_source_snapshot_id",
        "replay_source_entry_id",
    ]:
        metadata.pop(key, None)
    payload = {
        "snapshot_type": snapshot.snapshot_type,
        "as_of": snapshot.as_of.isoformat() if snapshot.as_of else None,
        "data_json": snapshot.data_json,
        "metadata_json": metadata,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_ROW_LIST_KEYS = ("rows", "records", "data", "candles", "quotes", "balances", "holdings", "orders", "trades", "positions")


def _extract_snapshot_rows(data_json: Any) -> list[Any] | None:
    """Return a list of row records from a snapshot payload, or None when the
    payload is not row-shaped (a scalar/keyed dict is diffed field-wise)."""
    if isinstance(data_json, list):
        return data_json
    if isinstance(data_json, dict):
        for key in _ROW_LIST_KEYS:
            value = data_json.get(key)
            if isinstance(value, list):
                return value
    return None


def _row_hash(row: Any) -> str:
    encoded = json.dumps(row, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _diff_rows(rows_a: list[Any], rows_b: list[Any], *, sample_limit: int = 20) -> dict[str, Any]:
    """Multiset row diff by content hash. Rows present in B but not A are
    'added'; rows in A but not B are 'removed'. Order-insensitive and
    duplicate-aware; samples are bounded for a review-friendly payload."""
    from collections import Counter

    hashes_a = Counter(_row_hash(row) for row in rows_a)
    hashes_b = Counter(_row_hash(row) for row in rows_b)
    by_hash_a: dict[str, Any] = {}
    for row in rows_a:
        by_hash_a.setdefault(_row_hash(row), row)
    by_hash_b: dict[str, Any] = {}
    for row in rows_b:
        by_hash_b.setdefault(_row_hash(row), row)

    added = hashes_b - hashes_a
    removed = hashes_a - hashes_b
    added_count = sum(added.values())
    removed_count = sum(removed.values())
    unchanged_count = sum((hashes_a & hashes_b).values())
    added_sample = [by_hash_b[h] for h in list(added.elements())[:sample_limit]]
    removed_sample = [by_hash_a[h] for h in list(removed.elements())[:sample_limit]]
    return {
        "shape": "rows",
        "row_count_base": len(rows_a),
        "row_count_compared": len(rows_b),
        "row_count_delta": len(rows_b) - len(rows_a),
        "added_row_count": added_count,
        "removed_row_count": removed_count,
        "unchanged_row_count": unchanged_count,
        "added_sample": added_sample,
        "removed_sample": removed_sample,
        "sample_truncated": added_count > sample_limit or removed_count > sample_limit,
    }


def _diff_fields(data_a: Any, data_b: Any, *, sample_limit: int = 40) -> dict[str, Any]:
    """Top-level field diff for non-row-shaped payloads."""
    dict_a = data_a if isinstance(data_a, dict) else {"_value": data_a}
    dict_b = data_b if isinstance(data_b, dict) else {"_value": data_b}
    keys_a = set(dict_a.keys())
    keys_b = set(dict_b.keys())
    added_keys = sorted(keys_b - keys_a)
    removed_keys = sorted(keys_a - keys_b)
    changed_keys = sorted(key for key in (keys_a & keys_b) if dict_a.get(key) != dict_b.get(key))
    return {
        "shape": "fields",
        "added_keys": added_keys[:sample_limit],
        "removed_keys": removed_keys[:sample_limit],
        "changed_keys": changed_keys[:sample_limit],
        "changed": [
            {"key": key, "base": dict_a.get(key), "compared": dict_b.get(key)}
            for key in changed_keys[:sample_limit]
        ],
    }


def data_snapshot_payload(snapshot: DataSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "snapshot_type": snapshot.snapshot_type,
        "as_of": snapshot.as_of,
        "data_json": snapshot.data_json,
        "metadata_json": snapshot.metadata_json,
        "created_at": snapshot.created_at,
    }


def data_quality_report_payload(report: DataQualityReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "data_snapshot_id": report.data_snapshot_id,
        "source": report.source,
        "metric_type": report.metric_type,
        "score": float(report.score),
        "details_json": report.details_json,
        "created_at": report.created_at,
    }


def data_catalog_entry_payload(entry: DataCatalogEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "dataset_type": entry.dataset_type,
        "source": entry.source,
        "source_ref": entry.source_ref,
        "data_snapshot_id": entry.data_snapshot_id,
        "quality_report_id": entry.quality_report_id,
        "row_count": entry.row_count,
        "quality_status": entry.quality_status,
        "usable_for_trading": entry.usable_for_trading,
        "lineage_json": entry.lineage_json,
        "contract_json": entry.contract_json,
        "created_at": entry.created_at,
    }


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
