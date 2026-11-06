from test_paper_execution import create_approved_draft


def test_review_context_is_owned_and_matches_atomic_fill(client):
    draft = create_approved_draft(client)
    response = client.post(f"/paper-executions/drafts/{draft['id']}/execute",
                          json={'fill_price':225.12,'approver_id':'human-reviewer'})
    assert response.status_code == 201, response.text
    fill = response.json()
    path = f"/paper-executions/{fill['execution']['id']}/review-context"
    result = client.get(path)
    assert result.status_code == 200, result.text
    value = result.json()
    assert value['execution']['id'] == fill['execution']['id']
    assert value['post_trade_review']['user_id'] == 'default-user'
    assert value['post_trade_review']['execution_id'] == fill['execution']['id']
    assert value['journal_entry']['id'] == value['post_trade_review']['trade_journal_entry_id']
    assert value['post_trade_review']['status'] == 'pending'
    assert value['execution_available'] is False
    assert client.get(path, headers={'X-AI-Trading-User':'foreign'}).status_code == 404
    assert client.get('/paper-executions/missing/review-context').status_code == 404
    from app.main import app
    from app.db.session import get_db
    from app.models import TradeJournalEntry
    database = app.dependency_overrides[get_db]()
    db = next(database)
    try:
        journal = db.get(TradeJournalEntry, value['journal_entry']['id'])
        journal.user_id = 'foreign'
        db.commit()
    finally:
        database.close()
    assert client.get(path).status_code == 409
