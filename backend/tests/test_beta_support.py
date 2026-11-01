import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.db.base import Base
from app.models import AuditLog
from app.models import OperationalEvent
from app.models import WorkflowReviewTask
from app.services.beta_support import BetaSupportError
from app.services.beta_support import BetaSupportService


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def actor(user_id: str, role: str = "viewer") -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, role=role, permissions=ROLE_PERMISSIONS[role], auth_required=True, token_configured=True)


def ticket_payload(**overrides):
    return {
        "category": "bug",
        "priority": "high",
        "title": "Portfolio total does not refresh",
        "description": "The portfolio total stays unchanged after a successful read-only sync.",
        "context": {"module": "portfolio", "release_id": "test-release"},
        **overrides,
    }


def test_create_ticket_enters_unified_task_queue_with_due_time_and_audit(db) -> None:
    service = BetaSupportService(db)
    created = service.create(actor=actor("user-a"), payload=ticket_payload())

    assert created["status"] == "open"
    assert created["task"]["status"] == "open"
    task = db.scalar(select(WorkflowReviewTask).where(WorkflowReviewTask.related_entity_id == created["id"]))
    assert task is not None
    assert task.item_type == "beta_support"
    assert task.queue_item_id == f"support:{created['id']}"
    assert task.due_at is not None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "support.ticket_created")) is not None


def test_security_ticket_is_urgent_and_secret_shaped_content_is_rejected(db) -> None:
    service = BetaSupportService(db)
    security = service.create(actor=actor("user-a"), payload=ticket_payload(category="security", priority="low"))
    assert security["priority"] == "urgent"
    with pytest.raises(BetaSupportError, match="remove credentials"):
        service.create(actor=actor("user-a"), payload=ticket_payload(description="The request included Authorization: Bearer secret-value and should be removed."))
    with pytest.raises(BetaSupportError, match="secret-free"):
        service.create(actor=actor("user-a"), payload=ticket_payload(context={"api_key": "secret"}))


def test_ticket_lists_are_tenant_scoped_and_cross_tenant_ids_are_hidden(db) -> None:
    service = BetaSupportService(db)
    first = service.create(actor=actor("user-a"), payload=ticket_payload(title="User A issue"))
    service.create(actor=actor("user-b"), payload=ticket_payload(title="User B issue"))

    rows = service.list(actor=actor("user-a"))
    assert [row["title"] for row in rows] == ["User A issue"]
    with pytest.raises(BetaSupportError, match="not found"):
        service.get(actor=actor("user-b"), ticket_id=first["id"])


def test_operator_state_machine_requires_permission_valid_transition_and_resolution(db) -> None:
    service = BetaSupportService(db)
    created = service.create(actor=actor("user-a"), payload=ticket_payload())
    with pytest.raises(BetaSupportError, match="operator permission"):
        service.transition(actor=actor("user-a"), ticket_id=created["id"], payload={"status": "triaged"})

    operator = actor("ops-user", "operator")
    triaged = service.transition(actor=operator, ticket_id=created["id"], payload={"status": "triaged", "assignee_id": "ops-user"})
    assert triaged["status"] == "triaged"
    assert triaged["task"]["assignee_id"] == "ops-user"
    with pytest.raises(BetaSupportError, match="invalid support transition"):
        service.transition(actor=operator, ticket_id=created["id"], payload={"status": "open"})
    with pytest.raises(BetaSupportError, match="resolution summary"):
        service.transition(actor=operator, ticket_id=created["id"], payload={"status": "resolved"})
    resolved = service.transition(actor=operator, ticket_id=created["id"], payload={"status": "resolved", "resolution_summary": "Refresh invalidation fixed and verified."})
    assert resolved["status"] == "resolved"
    assert resolved["task"]["status"] == "completed"


def test_waiting_user_reply_reopens_task_and_closed_ticket_rejects_reply(db) -> None:
    service = BetaSupportService(db)
    user = actor("user-a")
    operator = actor("ops-user", "operator")
    created = service.create(actor=user, payload=ticket_payload())
    service.transition(actor=operator, ticket_id=created["id"], payload={"status": "triaged"})
    waiting = service.transition(actor=operator, ticket_id=created["id"], payload={"status": "waiting_user"})
    assert waiting["status"] == "waiting_user"
    replied = service.reply(actor=user, ticket_id=created["id"], message="The issue also happens after a full page reload.")
    assert replied["status"] == "triaged"
    assert replied["history"][-1]["action"] == "user_reply"
    resolved = service.transition(actor=operator, ticket_id=created["id"], payload={"status": "resolved", "resolution_summary": "Fixed cache invalidation."})
    service.transition(actor=operator, ticket_id=created["id"], payload={"status": "closed", "resolution_summary": resolved["resolution_summary"]})
    with pytest.raises(BetaSupportError, match="closed"):
        service.reply(actor=user, ticket_id=created["id"], message="One more detail")


def test_operator_queue_orders_open_support_tasks_and_excludes_resolved(db) -> None:
    service = BetaSupportService(db)
    operator = actor("ops-user", "operator")
    urgent = service.create(actor=actor("user-a"), payload=ticket_payload(category="security"))
    normal = service.create(actor=actor("user-b"), payload=ticket_payload(priority="normal", title="How do I review a thesis?"))
    queue = service.operator_queue(actor=operator)
    assert {row["id"] for row in queue} == {urgent["id"], normal["id"]}
    service.transition(actor=operator, ticket_id=urgent["id"], payload={"status": "triaged"})
    service.transition(actor=operator, ticket_id=urgent["id"], payload={"status": "resolved", "resolution_summary": "Security report reviewed and remediated."})
    assert [row["id"] for row in service.operator_queue(actor=operator)] == [normal["id"]]


def test_operator_metrics_measure_workflow_but_exclude_local_test_tickets_from_real_evidence(db) -> None:
    service = BetaSupportService(db)
    operator = actor("ops-user", "operator")
    created = service.create(actor=actor("test-beta-user"), payload=ticket_payload())
    service.transition(actor=operator, ticket_id=created["id"], payload={"status": "triaged", "assignee_id": "ops-user"})
    service.transition(actor=operator, ticket_id=created["id"], payload={"status": "resolved", "resolution_summary": "Fixed and verified."})
    metrics = service.operator_metrics(actor=operator)
    assert metrics["ticket_count"] == 1
    assert metrics["responded_count"] == 1
    assert metrics["resolved_count"] == 1
    assert metrics["first_response_sla_rate"] == 1.0
    assert metrics["verified_real_user_ticket_count"] == 0
    assert metrics["real_support_quality_evidence"] is False
    assert metrics["local_or_test_tickets_excluded_from_real_evidence"] is True


def test_support_api_viewer_can_create_list_reply_but_not_operate(client) -> None:
    headers = {"X-AI-Trading-User": "support-api-user", "X-AI-Trading-Role": "viewer"}
    created = client.post("/production/support/tickets", headers=headers, json=ticket_payload())
    assert created.status_code == 201
    ticket_id = created.json()["id"]
    rows = client.get("/production/support/tickets", headers=headers)
    assert rows.status_code == 200
    assert rows.json()[0]["id"] == ticket_id
    replied = client.post(f"/production/support/tickets/{ticket_id}/replies", headers=headers, json={"message": "This is a safe additional detail."})
    assert replied.status_code == 200
    denied = client.patch(f"/production/support/tickets/{ticket_id}", headers=headers, json={"status": "triaged"})
    assert denied.status_code == 422
    metrics_denied = client.get("/production/support/operator-metrics", headers=headers)
    assert metrics_denied.status_code == 403
