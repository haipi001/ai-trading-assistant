from test_paper_execution import create_approved_draft


def executed(client):
    draft=create_approved_draft(client)
    response=client.post(f"/paper-executions/drafts/{draft['id']}/execute",json={'fill_price':225.12,'approver_id':'human-user'})
    assert response.status_code==201,response.text
    return response.json()['post_trade_review']


def test_review_save_conflict_and_explicit_completion_do_not_execute(client):
    review=executed(client)
    executions=client.get('/paper-executions').json()
    drafts=client.get('/orders/drafts').json()
    path=f"/post-trade-reviews/{review['id']}"
    body={'expected_updated_at':review['updated_at'],'review_json':{'terminal_manual_review':{'notes':'Original rationale held; slippage recorded.','source':'human'}}}
    saved=client.patch(path,json=body)
    assert saved.status_code==200,saved.text
    assert saved.json()['status']==review['status']
    assert saved.json()['updated_at']!=review['updated_at']
    stale=client.patch(path,json={**body,'status':'completed'})
    assert stale.status_code==409
    current=client.get(f"/paper-executions/{review['execution_id']}/review-context").json()['post_trade_review']
    assert current==saved.json()
    completed=client.patch(path,json={'expected_updated_at':current['updated_at'],'status':'completed','review_json':current['review_json']})
    assert completed.status_code==200,completed.text
    assert completed.json()['status']=='completed'
    assert client.get('/paper-executions').json()==executions
    assert client.get('/orders/drafts').json()==drafts


def test_review_foreign_user_cannot_write_even_with_exact_id_and_version(client):
    review=executed(client)
    response=client.patch(f"/post-trade-reviews/{review['id']}",headers={'X-AI-Trading-User':'foreign-user'},
        json={'expected_updated_at':review['updated_at'],'status':'completed','review_json':{'notes':'foreign'}})
    assert response.status_code==404,response.text
    own=client.get(f"/paper-executions/{review['execution_id']}/review-context").json()['post_trade_review']
    assert own==review
