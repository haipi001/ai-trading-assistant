from fastapi.testclient import TestClient

from test_risk_approval import create_account
from test_risk_approval import create_asset
from test_risk_approval import create_intent
from test_risk_approval import pass_decision_gates
from test_risk_approval import risk_payload


def create_approved_draft(
    client: TestClient,
    *,
    asset: dict | None = None,
    account: dict | None = None,
    side: str = "buy",
    quantity: float | None = None,
    notional: float | None = 225.12,
    limit_price: float | None = None,
    strategy_playbook_id: str | None = None,
) -> dict:
    asset = asset or create_asset(client)
    account = account or create_account(client)
    intent = create_intent(
        client,
        asset["id"],
        account["id"],
        side=side,
        quantity=quantity,
        notional=notional,
        limit_price=limit_price,
        strategy_playbook_id=strategy_playbook_id,
    )
    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft_response.status_code == 201
    draft = draft_response.json()
    approval_response = client.post(
        f"/orders/drafts/{draft['id']}/approve",
        json={"approver_id": "human-user", "decision_reason": "Paper execution test approval."},
    )
    assert approval_response.status_code == 201
    return draft


def create_strategy_playbook(client: TestClient, *, user_id: str = "default-user") -> dict:
    response = client.post(
        "/strategy-playbooks",
        json={
            "user_id": user_id,
            "name": "Paper review discipline",
            "strategy_type": "swing",
            "applicable_markets": ["US"],
            "applicable_assets": ["AAPL"],
            "entry_conditions_json": {"requires_thesis_alignment": True},
            "exit_conditions_json": {"invalidate_on_thesis_break": True},
            "risk_rules_json": {"max_position_pct": 0.1},
            "automation_level": "A1_RESEARCH",
            "requires_human_approval": True,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_paper_execution_requires_approval(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"], notional=225.12)
    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft_response.status_code == 201
    draft = draft_response.json()

    response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12},
    )

    assert response.status_code == 422
    assert "approved order draft" in response.json()["detail"]


def test_paper_execution_records_journal_and_audit(client: TestClient) -> None:
    draft = create_approved_draft(client)

    response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "decision_reason": "Record paper fill.", "fill_price": 225.12, "fee_bps": 0},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["execution"]["execution_mode"] == "paper"
    assert payload["execution"]["status"] == "filled"
    assert payload["execution"]["fill_notional"] == 225.12
    assert payload["execution"]["fee_amount"] == 0
    assert payload["execution"]["cash_effect"] == -225.12
    assert payload["order_draft"]["execution_status"] == "paper_filled"
    assert "Paper BUY" in payload["journal_entry"]["title"]
    assert "Live execution performed: false" in payload["journal_entry"]["notes"]
    assert payload["post_trade_review"]["status"] == "pending"
    assert payload["post_trade_review"]["prompt_json"]["status"] == "pending_review"

    executions = client.get("/paper-executions").json()
    assert len(executions) == 1
    journal_entries = client.get("/trade-journal-entries").json()
    assert len(journal_entries) == 1
    post_trade_reviews = client.get("/post-trade-reviews").json()
    assert len(post_trade_reviews) == 1
    positions = client.get("/positions").json()
    asset_positions = [position for position in positions if position["asset_id"] == payload["journal_entry"]["asset_id"]]
    cash_positions = [position for position in positions if position["asset_id"] != payload["journal_entry"]["asset_id"]]
    assert asset_positions[0]["quantity"] == 1
    assert asset_positions[0]["average_cost"] == 225.12
    assert cash_positions[0]["quantity"] == 99774.88
    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert {
        "paper_execution.filled",
        "paper_portfolio.updated_from_execution",
        "trade_journal.created_from_paper_execution",
        "post_trade_review.created_from_paper_execution",
    }.issubset(actions)


def test_paper_execution_is_idempotently_blocked(client: TestClient) -> None:
    draft = create_approved_draft(client)
    first = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12},
    )
    assert first.status_code == 201

    second = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12},
    )

    assert second.status_code == 422
    assert "already has a paper execution" in second.json()["detail"]


def test_post_trade_review_can_be_completed(client: TestClient) -> None:
    draft = create_approved_draft(client)
    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12},
    )
    assert execute_response.status_code == 201
    review = execute_response.json()["post_trade_review"]

    update_response = client.patch(
        f"/post-trade-reviews/{review['id']}",
        json={"status": "completed", "review_json": {"lesson": "Aligned with thesis and risk gates."}},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "completed"
    assert updated["review_json"]["lesson"] == "Aligned with thesis and risk gates."


def test_partial_paper_fills_can_complete_same_draft(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    draft = create_approved_draft(client, asset=asset, account=account, quantity=10, notional=None, limit_price=100)

    first = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 100, "fill_quantity": 4, "fee_bps": 0},
    )
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload["execution"]["status"] == "partially_filled"
    assert first_payload["execution"]["requested_quantity"] == 10
    assert first_payload["execution"]["filled_quantity"] == 4
    assert first_payload["execution"]["cumulative_filled_quantity"] == 4
    assert first_payload["execution"]["remaining_quantity"] == 6
    assert first_payload["order_draft"]["execution_status"] == "paper_partially_filled"
    assert first_payload["tax_lots"][0]["quantity_remaining"] == 4

    second = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 100, "fill_quantity": 6, "fee_bps": 0},
    )
    assert second.status_code == 201
    second_payload = second.json()
    assert second_payload["execution"]["status"] == "filled"
    assert second_payload["execution"]["cumulative_filled_quantity"] == 10
    assert second_payload["execution"]["remaining_quantity"] == 0
    assert second_payload["order_draft"]["execution_status"] == "paper_filled"

    executions = client.get("/paper-executions").json()
    assert len(executions) == 2
    positions = client.get("/positions").json()
    asset_positions = [position for position in positions if position["asset_id"] == asset["id"]]
    assert asset_positions[0]["quantity"] == 10
    tax_lots = client.get(f"/paper-tax-lots?account_id={account['id']}&asset_id={asset['id']}").json()
    assert len(tax_lots) == 2
    assert sum(lot["quantity_remaining"] for lot in tax_lots) == 10


def test_sell_paper_execution_realizes_fifo_tax_lot_pnl(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    first_buy_draft = create_approved_draft(client, asset=asset, account=account, quantity=4, notional=None, limit_price=100)
    second_buy_draft = create_approved_draft(client, asset=asset, account=account, quantity=6, notional=None, limit_price=110)

    first_buy = client.post(
        f"/paper-executions/drafts/{first_buy_draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 100, "fee_bps": 0},
    )
    assert first_buy.status_code == 201
    second_buy = client.post(
        f"/paper-executions/drafts/{second_buy_draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 110, "fee_bps": 0},
    )
    assert second_buy.status_code == 201

    sell_draft = create_approved_draft(client, asset=asset, account=account, side="sell", quantity=5, notional=None, limit_price=120)
    sell = client.post(
        f"/paper-executions/drafts/{sell_draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 120, "fee_bps": 0},
    )

    assert sell.status_code == 201
    payload = sell.json()
    assert payload["execution"]["proceeds_amount"] == 600
    assert payload["execution"]["cost_basis_amount"] == 510
    assert payload["execution"]["realized_pnl"] == 90
    assert payload["execution"]["cash_effect"] == 600
    assert len(payload["tax_lot_realizations"]) == 2
    assert sum(realization["quantity"] for realization in payload["tax_lot_realizations"]) == 5

    positions = client.get("/positions").json()
    asset_positions = [position for position in positions if position["asset_id"] == asset["id"]]
    assert asset_positions[0]["quantity"] == 5
    assert asset_positions[0]["average_cost"] == 110
    assert asset_positions[0]["realized_pnl"] == 90
    realizations = client.get(f"/paper-tax-lot-realizations?execution_id={payload['execution']['id']}").json()
    assert len(realizations) == 2


def test_sell_paper_execution_blocks_insufficient_quantity(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"], side="sell", quantity=1, notional=None, limit_price=120)
    response = client.post("/risk/check-order", json=risk_payload(intent["id"]))
    assert response.status_code == 201
    assert response.json()["hard_rule_passed"] is False
    rule = next(item for item in response.json()["rules_json"]["rules"] if item["rule"] == "trusted_account_state")
    assert "sell_exceeds_server_position" in rule["details"]["errors"]
    draft = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft.status_code == 422
    assert client.get("/paper-executions").json() == []


def test_paper_cash_dividend_updates_cash_and_journal(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    draft = create_approved_draft(client, asset=asset, account=account, quantity=10, notional=None, limit_price=100)
    buy = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 100, "fee_bps": 0},
    )
    assert buy.status_code == 201

    response = client.post(
        "/paper-corporate-actions/cash-dividend",
        json={"account_id": account["id"], "asset_id": asset["id"], "amount_per_share": 1.5, "note": "Quarterly dividend."},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["corporate_action"]["action_type"] == "cash_dividend"
    assert payload["corporate_action"]["cash_effect"] == 15
    assert payload["journal_entry"]["title"] == "Paper dividend AAPL"

    actions = client.get("/paper-corporate-actions").json()
    assert len(actions) == 1
    positions = client.get("/positions").json()
    cash_positions = [position for position in positions if position["asset_id"] != asset["id"]]
    assert cash_positions[0]["quantity"] == 99015
    audit_actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert "paper_corporate_action.cash_dividend_applied" in audit_actions


def test_paper_stock_split_adjusts_position_and_tax_lots(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    draft = create_approved_draft(client, asset=asset, account=account, quantity=10, notional=None, limit_price=100)
    buy = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 100, "fee_bps": 0},
    )
    assert buy.status_code == 201

    response = client.post(
        "/paper-corporate-actions/stock-split",
        json={"account_id": account["id"], "asset_id": asset["id"], "ratio_numerator": 2, "ratio_denominator": 1},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["corporate_action"]["action_type"] == "stock_split"
    assert payload["corporate_action"]["quantity_before"] == 10
    assert payload["corporate_action"]["quantity_after"] == 20
    assert payload["corporate_action"]["cash_effect"] == 0

    positions = client.get("/positions").json()
    asset_positions = [position for position in positions if position["asset_id"] == asset["id"]]
    assert asset_positions[0]["quantity"] == 20
    assert asset_positions[0]["average_cost"] == 50
    assert asset_positions[0]["market_price"] == 50
    assert asset_positions[0]["market_value"] == 1000
    tax_lots = client.get(f"/paper-tax-lots?account_id={account['id']}&asset_id={asset['id']}").json()
    assert tax_lots[0]["quantity_remaining"] == 20
    assert tax_lots[0]["average_cost"] == 50
    assert tax_lots[0]["cost_basis_remaining"] == 1000


def test_playbook_update_proposal_from_review_requires_manual_approval(client: TestClient) -> None:
    playbook = create_strategy_playbook(client)
    draft = create_approved_draft(client, strategy_playbook_id=playbook["id"])
    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12},
    )
    assert execute_response.status_code == 201
    review = execute_response.json()["post_trade_review"]
    update_response = client.patch(
        f"/post-trade-reviews/{review['id']}",
        json={"status": "completed", "review_json": {"lesson": "Wait for thesis confirmation before adding size."}},
    )
    assert update_response.status_code == 200

    proposal_response = client.post(f"/playbook-update-proposals/from-post-trade-review/{review['id']}")

    assert proposal_response.status_code == 201
    proposal = proposal_response.json()
    assert proposal["source_type"] == "post_trade_review"
    assert proposal["source_id"] == review["id"]
    assert proposal["status"] == "pending"
    assert proposal["requires_user_approval"] is True
    assert proposal["proposal_json"]["safe_apply_mode"] == "manual_only"
    assert "not mutate StrategyPlaybook automatically" in proposal["proposal_json"]["not_implemented"]

    approve_response = client.post(
        f"/playbook-update-proposals/{proposal['id']}/approve",
        json={"reviewer_id": "human-user", "decision_reason": "Useful guardrail, but apply manually later."},
    )
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "approved_pending_manual_apply"
    audit_actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert "playbook_update_proposal.created_from_post_trade_review" in audit_actions
    assert "playbook_update_proposal.approved_no_auto_apply" in audit_actions


def test_approved_playbook_proposal_can_be_previewed_and_applied_manually(client: TestClient) -> None:
    playbook = create_strategy_playbook(client)
    draft = create_approved_draft(client, strategy_playbook_id=playbook["id"])
    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12},
    )
    assert execute_response.status_code == 201
    review = execute_response.json()["post_trade_review"]
    proposal = client.post(f"/playbook-update-proposals/from-post-trade-review/{review['id']}").json()
    approve_response = client.post(
        f"/playbook-update-proposals/{proposal['id']}/approve",
        json={"reviewer_id": "human-user", "decision_reason": "Ready for manual patch preview."},
    )
    assert approve_response.status_code == 200

    preview_response = client.post(
        f"/playbook-update-proposals/{proposal['id']}/preview-manual-apply",
        json={"target_strategy_playbook_id": playbook["id"]},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["auto_applied"] is False
    assert preview["patch_json"]["operation"] == "append"
    assert preview["patch_json"]["after"]["requires_human_approval"] is True

    apply_response = client.post(
        f"/playbook-update-proposals/{proposal['id']}/apply-manually",
        json={
            "reviewer_id": "human-user",
            "decision_reason": "Patch accepted by human.",
            "edited_rule_json": {
                "name": "Require review before repeat AAPL setup",
                "condition": "A similar AAPL setup appears within 10 trading days.",
                "action": "Attach the prior post-trade review before creating a new draft.",
            },
        },
    )
    assert apply_response.status_code == 200
    payload = apply_response.json()
    assert payload["proposal"]["status"] == "applied_manually"
    assert payload["playbook"]["requires_human_approval"] is True
    rules = payload["playbook"]["risk_rules_json"]["manual_review_rules"]
    assert rules[-1]["name"] == "Require review before repeat AAPL setup"
    assert rules[-1]["source_proposal_id"] == proposal["id"]
    assert rules[-1]["auto_execution_allowed"] is False
    assert payload["playbook"]["risk_rules_json"]["manual_revision"] == 1
    assert payload["playbook"]["risk_rules_json"]["version_history"][-1]["proposal_id"] == proposal["id"]

    second_apply = client.post(
        f"/playbook-update-proposals/{proposal['id']}/apply-manually",
        json={"reviewer_id": "human-user"},
    )
    assert second_apply.status_code == 422
    audit_actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert "playbook_update_proposal.applied_manually" in audit_actions
    assert "strategy_playbook.rule_patch_applied_from_review" in audit_actions


def test_applied_playbook_proposal_can_publish_new_version(client: TestClient) -> None:
    playbook = create_strategy_playbook(client)
    draft = create_approved_draft(client, strategy_playbook_id=playbook["id"])
    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12},
    )
    assert execute_response.status_code == 201
    review = execute_response.json()["post_trade_review"]
    proposal = client.post(f"/playbook-update-proposals/from-post-trade-review/{review['id']}").json()
    approve_response = client.post(
        f"/playbook-update-proposals/{proposal['id']}/approve",
        json={"reviewer_id": "human-user", "decision_reason": "Approve for publish."},
    )
    assert approve_response.status_code == 200
    apply_response = client.post(
        f"/playbook-update-proposals/{proposal['id']}/apply-manually",
        json={
            "reviewer_id": "human-user",
            "decision_reason": "Apply before publish.",
            "edited_rule_json": {
                "name": "Publish-ready guardrail",
                "condition": "Setup repeats within 5 days.",
                "action": "Require previous review attachment.",
            },
        },
    )
    assert apply_response.status_code == 200

    publish_response = client.post(
        f"/playbook-update-proposals/{proposal['id']}/publish-version",
        json={
            "reviewer_id": "human-user",
            "decision_reason": "Promote to active version.",
            "publish_note": "Quarterly rules refresh.",
        },
    )
    assert publish_response.status_code == 200
    payload = publish_response.json()
    assert payload["proposal"]["status"] == "published_as_new_version"
    assert payload["previous_playbook"]["is_active"] is False
    assert payload["published_playbook"]["is_active"] is True
    assert payload["published_playbook"]["risk_rules_json"]["playbook_version"] == 2
    assert payload["publish_metadata"]["publish_note"] == "Quarterly rules refresh."
