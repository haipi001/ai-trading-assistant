from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.config import Settings
from app.core.config import get_settings
from app.models import AuditLog
from app.models import OperationalEvent
from app.models import WorkflowReviewTask
from app.models import UserAccount
from app.schemas.core import contains_secret_config_key


class BetaSupportError(ValueError):
    pass


class BetaSupportService:
    CATEGORIES = {"bug", "question", "feedback", "data_quality", "privacy", "security"}
    PRIORITIES = {"low", "normal", "high", "urgent"}
    TRANSITIONS = {
        "open": {"triaged", "closed"},
        "triaged": {"in_progress", "waiting_user", "resolved", "closed"},
        "in_progress": {"waiting_user", "resolved", "closed"},
        "waiting_user": {"in_progress", "resolved", "closed"},
        "resolved": {"in_progress", "closed"},
        "closed": set(),
    }
    SECRET_TEXT = re.compile(r"(?i)(?:authorization\s*:|api[_-]?key\s*[=:]|secret\s*[=:]|password\s*[=:]|sk-[a-z0-9_-]{12,})")

    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def create(self, *, actor: AuthenticatedUser, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_read(actor)
        category = str(payload.get("category") or "feedback").strip().lower()
        priority = str(payload.get("priority") or "normal").strip().lower()
        title = str(payload.get("title") or "").strip()
        description = str(payload.get("description") or "").strip()
        context = payload.get("context") or {}
        if category not in self.CATEGORIES:
            raise BetaSupportError("unsupported support category")
        if priority not in self.PRIORITIES:
            raise BetaSupportError("unsupported support priority")
        if not 3 <= len(title) <= 160:
            raise BetaSupportError("support title must contain 3 to 160 characters")
        if not 10 <= len(description) <= 4000:
            raise BetaSupportError("support description must contain 10 to 4000 characters")
        if not isinstance(context, dict) or contains_secret_config_key(context):
            raise BetaSupportError("support context must be a secret-free object")
        if self.SECRET_TEXT.search(title) or self.SECRET_TEXT.search(description):
            raise BetaSupportError("remove credentials or secret values before submitting support content")
        if category == "security":
            priority = "urgent"
        created_at = self._now()
        event = OperationalEvent(
            user_id=actor.user_id,
            event_type="support.ticket",
            severity={"low": "info", "normal": "info", "high": "warning", "urgent": "critical"}[priority],
            source="beta-support",
            message=title,
            status="open",
            payload_json={
                "category": category,
                "priority": priority,
                "description": description,
                "context": context,
                "assignee_id": None,
                "resolution_summary": None,
                "history": [{"at": created_at.isoformat(), "by": actor.user_id, "action": "created", "status": "open"}],
                "contains_secrets": False,
                "production_execution_allowed": False,
            },
        )
        self.db.add(event)
        self.db.flush()
        task = WorkflowReviewTask(
            user_id=actor.user_id,
            queue_item_id=f"support:{event.id}",
            item_type="beta_support",
            title=title,
            detail=description[:1000],
            priority=priority,
            status="open",
            assignee_id=None,
            due_at=created_at + timedelta(hours={"low": 168, "normal": 72, "high": 24, "urgent": 4}[priority]),
            related_entity_type="OperationalEvent",
            related_entity_id=event.id,
            payload_json={"category": category, "support_ticket_id": event.id, "production_execution_allowed": False},
        )
        self.db.add(task)
        self.db.flush()
        self._audit(actor.user_id, "support.ticket_created", event.id, {"category": category, "priority": priority, "task_id": task.id})
        self.db.commit()
        return self._payload(event, task)

    def list(self, *, actor: AuthenticatedUser, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self._require_read(actor)
        if status and status not in self.TRANSITIONS:
            raise BetaSupportError("unsupported support status")
        query = select(OperationalEvent).where(
            OperationalEvent.user_id == actor.user_id,
            OperationalEvent.event_type == "support.ticket",
        )
        if status:
            query = query.where(OperationalEvent.status == status)
        events = list(self.db.scalars(query.order_by(OperationalEvent.created_at.desc(), OperationalEvent.id.desc()).limit(max(1, min(limit, 100)))).all())
        tasks = self._tasks([event.id for event in events])
        return [self._payload(event, tasks.get(event.id)) for event in events]

    def get(self, *, actor: AuthenticatedUser, ticket_id: str) -> dict[str, Any]:
        self._require_read(actor)
        event = self._owned_ticket(actor.user_id, ticket_id)
        return self._payload(event, self._task(event.id))

    def reply(self, *, actor: AuthenticatedUser, ticket_id: str, message: str) -> dict[str, Any]:
        self._require_read(actor)
        event = self._owned_ticket(actor.user_id, ticket_id)
        message = message.strip()
        if not 2 <= len(message) <= 2000:
            raise BetaSupportError("support reply must contain 2 to 2000 characters")
        if self.SECRET_TEXT.search(message):
            raise BetaSupportError("remove credentials or secret values before submitting support content")
        if event.status == "closed":
            raise BetaSupportError("closed support tickets cannot receive replies")
        payload = dict(event.payload_json or {})
        history = list(payload.get("history") or [])
        next_status = "triaged" if event.status == "waiting_user" else event.status
        history.append({"at": self._now().isoformat(), "by": actor.user_id, "action": "user_reply", "message": message, "status": next_status})
        event.status = next_status
        event.payload_json = {**payload, "history": history[-50:]}
        task = self._task(event.id)
        if task and task.status == "completed":
            task.status = "open"
            task.completed_at = None
        self._audit(actor.user_id, "support.ticket_user_replied", event.id, {"status": next_status, "message_stored_in_ticket_only": True})
        self.db.commit()
        return self._payload(event, task)

    def transition(self, *, actor: AuthenticatedUser, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_operator(actor)
        with self._operator_scope():
            event = self.db.scalar(select(OperationalEvent).where(OperationalEvent.id == ticket_id, OperationalEvent.event_type == "support.ticket").limit(1).execution_options(tenant_scope_bypass=True))
            if event is None:
                raise BetaSupportError("support ticket not found")
            next_status = str(payload.get("status") or "").strip()
            if next_status not in self.TRANSITIONS.get(event.status, set()):
                raise BetaSupportError(f"invalid support transition: {event.status} -> {next_status}")
            assignee_id = str(payload.get("assignee_id") or "").strip() or None
            resolution = str(payload.get("resolution_summary") or "").strip() or None
            if next_status in {"resolved", "closed"} and not resolution:
                raise BetaSupportError("resolved or closed tickets require a resolution summary")
            if resolution and (len(resolution) > 2000 or self.SECRET_TEXT.search(resolution)):
                raise BetaSupportError("resolution summary is too long or contains secret-shaped content")
            current = event.status
            event.status = next_status
            event.payload_json = {
                **(event.payload_json or {}),
                "assignee_id": assignee_id or (event.payload_json or {}).get("assignee_id"),
                "resolution_summary": resolution or (event.payload_json or {}).get("resolution_summary"),
                "history": [
                    *list((event.payload_json or {}).get("history") or [])[-49:],
                    {"at": self._now().isoformat(), "by": actor.user_id, "action": "transition", "from": current, "status": next_status, "resolution_summary": resolution},
                ],
            }
            task = self.db.scalar(select(WorkflowReviewTask).where(
                WorkflowReviewTask.item_type == "beta_support",
                WorkflowReviewTask.related_entity_id == event.id,
            ).limit(1).execution_options(tenant_scope_bypass=True))
            if task:
                task.assignee_id = assignee_id or task.assignee_id
                task.status = "completed" if next_status in {"resolved", "closed"} else "open"
                task.completed_at = self._now() if task.status == "completed" else None
                task.payload_json = {**(task.payload_json or {}), "support_status": next_status}
            self._audit(actor.user_id, "support.ticket_transitioned", event.id, {"from": current, "to": next_status, "assignee_id": assignee_id})
            self.db.commit()
            return self._payload(event, task)

    def operator_queue(self, *, actor: AuthenticatedUser, limit: int = 100) -> list[dict[str, Any]]:
        self._require_operator(actor)
        with self._operator_scope():
            tasks = list(self.db.scalars(
                select(WorkflowReviewTask)
                .where(WorkflowReviewTask.item_type == "beta_support", WorkflowReviewTask.status == "open")
                .order_by(WorkflowReviewTask.due_at, WorkflowReviewTask.created_at)
                .limit(max(1, min(limit, 200)))
                .execution_options(tenant_scope_bypass=True)
            ).all())
            events = {event.id: event for event in self.db.scalars(select(OperationalEvent).where(OperationalEvent.id.in_([task.related_entity_id for task in tasks])).execution_options(tenant_scope_bypass=True)).all()} if tasks else {}
            return [self._payload(events[task.related_entity_id], task) for task in tasks if task.related_entity_id in events]

    def operator_metrics(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require_operator(actor)
        with self._operator_scope():
            events = list(self.db.scalars(
                select(OperationalEvent)
                .where(OperationalEvent.event_type == "support.ticket")
                .order_by(OperationalEvent.created_at)
                .execution_options(tenant_scope_bypass=True)
            ).all())
            tasks = self._tasks_operator([event.id for event in events])
            users = {user.user_id: user for user in self.db.scalars(select(UserAccount).execution_options(tenant_scope_bypass=True)).all()}
        now = self._now()
        rows: list[dict[str, Any]] = []
        for event in events:
            history = list((event.payload_json or {}).get("history") or [])
            created = self._aware(event.created_at)
            operator_times = [self._parse(item.get("at")) for item in history if item.get("action") == "transition"]
            resolved_times = [self._parse(item.get("at")) for item in history if item.get("status") in {"resolved", "closed"}]
            first_response = next((item for item in operator_times if item is not None), None)
            first_resolution = next((item for item in resolved_times if item is not None), None)
            task = tasks.get(event.id)
            due = self._aware(task.due_at) if task and task.due_at else None
            user = users.get(event.user_id)
            identity_provider = str((user.onboarding_state_json or {}).get("identity_provider") or "") if user else ""
            real_identity = bool(
                self.settings.environment in {"staging", "production"}
                and self.settings.managed_auth_required
                and identity_provider.startswith("https://")
                and not any(marker in event.user_id.lower() for marker in ("default", "demo", "test", "e2e", "sample"))
            )
            rows.append({
                "first_response_minutes": round((first_response - created).total_seconds() / 60, 2) if first_response else None,
                "resolution_minutes": round((first_resolution - created).total_seconds() / 60, 2) if first_resolution else None,
                "first_response_within_sla": bool(first_response and due and first_response <= due),
                "currently_overdue": bool(event.status not in {"resolved", "closed"} and due and due < now),
                "reopened": any(item.get("action") == "user_reply" and item.get("status") == "triaged" for item in history) or any(item.get("from") == "resolved" for item in history),
                "real_identity": real_identity,
            })
        def average(key: str) -> float | None:
            values = [float(row[key]) for row in rows if row[key] is not None]
            return round(sum(values) / len(values), 2) if values else None
        responded = [row for row in rows if row["first_response_minutes"] is not None]
        real_rows = [row for row in rows if row["real_identity"]]
        return {
            "ticket_count": len(rows),
            "open_count": sum(1 for event in events if event.status not in {"resolved", "closed"}),
            "currently_overdue_count": sum(1 for row in rows if row["currently_overdue"]),
            "responded_count": len(responded),
            "resolved_count": sum(1 for row in rows if row["resolution_minutes"] is not None),
            "reopened_count": sum(1 for row in rows if row["reopened"]),
            "average_first_response_minutes": average("first_response_minutes"),
            "average_resolution_minutes": average("resolution_minutes"),
            "first_response_sla_rate": round(sum(1 for row in responded if row["first_response_within_sla"]) / len(responded), 4) if responded else None,
            "verified_real_user_ticket_count": len(real_rows),
            "real_support_quality_evidence": bool(real_rows),
            "local_or_test_tickets_excluded_from_real_evidence": len(real_rows) != len(rows),
            "generated_at": now,
        }

    def _tasks_operator(self, ticket_ids: list[str]) -> dict[str, WorkflowReviewTask]:
        if not ticket_ids:
            return {}
        return {task.related_entity_id: task for task in self.db.scalars(select(WorkflowReviewTask).where(
            WorkflowReviewTask.item_type == "beta_support",
            WorkflowReviewTask.related_entity_id.in_(ticket_ids),
        ).execution_options(tenant_scope_bypass=True)).all()}

    def _owned_ticket(self, user_id: str, ticket_id: str) -> OperationalEvent:
        event = self.db.scalar(select(OperationalEvent).where(
            OperationalEvent.id == ticket_id,
            OperationalEvent.user_id == user_id,
            OperationalEvent.event_type == "support.ticket",
        ).limit(1))
        if event is None:
            raise BetaSupportError("support ticket not found")
        return event

    def _task(self, ticket_id: str) -> WorkflowReviewTask | None:
        return self.db.scalar(select(WorkflowReviewTask).where(
            WorkflowReviewTask.item_type == "beta_support",
            WorkflowReviewTask.related_entity_id == ticket_id,
        ).limit(1))

    def _tasks(self, ticket_ids: list[str]) -> dict[str, WorkflowReviewTask]:
        if not ticket_ids:
            return {}
        return {task.related_entity_id: task for task in self.db.scalars(select(WorkflowReviewTask).where(
            WorkflowReviewTask.item_type == "beta_support",
            WorkflowReviewTask.related_entity_id.in_(ticket_ids),
        )).all()}

    def _payload(self, event: OperationalEvent, task: WorkflowReviewTask | None) -> dict[str, Any]:
        payload = event.payload_json or {}
        return {
            "id": event.id,
            "title": event.message,
            "category": payload.get("category"),
            "priority": payload.get("priority"),
            "status": event.status,
            "description": payload.get("description"),
            "context": payload.get("context") or {},
            "assignee_id": payload.get("assignee_id"),
            "resolution_summary": payload.get("resolution_summary"),
            "history": payload.get("history") or [],
            "created_at": event.created_at,
            "task": {
                "id": task.id,
                "status": task.status,
                "due_at": task.due_at,
                "assignee_id": task.assignee_id,
            } if task else None,
            "production_execution_allowed": False,
        }

    def _audit(self, user_id: str, action: str, entity_id: str, payload: dict[str, Any]) -> None:
        self.db.add(AuditLog(
            user_id=user_id,
            actor_type="user",
            actor_id=user_id,
            action=action,
            entity_type="OperationalEvent",
            entity_id=entity_id,
            payload_json={**payload, "production_execution_allowed": False},
        ))

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
            raise BetaSupportError("authenticated support access is required")

    @staticmethod
    def _require_operator(actor: AuthenticatedUser) -> None:
        if "events:write" not in actor.permissions:
            raise BetaSupportError("support operator permission is required")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

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
