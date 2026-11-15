from test_self_logic_models import create_constitution


def test_constitution_revision_retains_evidence_and_history(client):
    original = create_constitution(client)
    payload = {key: value for key, value in original.items() if key not in ('id', 'created_at', 'updated_at')}
    payload.update(version='v2-memory', max_single_position_pct=0.12)
    payload['cooldown_rules_json']['constitution_memory_v1'] = {
        'base_id': original['id'], 'reason': '复盘后降低集中度',
        'principles': '保留决策依据',
        'evidence': [{'id': 'note-1', 'title': '止损复盘', 'body': '追涨造成额外损失'}],
    }
    response = client.post('/investment-constitutions', json=payload)
    assert response.status_code == 201
    saved = response.json()
    rows = client.get('/investment-constitutions').json()
    assert any(row['id'] == original['id'] and row['max_single_position_pct'] == 0.2 for row in rows)
    restored = next(row for row in rows if row['id'] == saved['id'])
    assert restored['max_single_position_pct'] == 0.12
    assert restored['cooldown_rules_json']['constitution_memory_v1']['evidence'][0]['title'] == '止损复盘'
    assert restored['cooldown_rules_json']['after_loss_minutes'] == 60


def test_constitution_rejects_out_of_range_limits(client):
    original = create_constitution(client)
    for value in (-0.01, 1.01):
        assert client.post('/investment-constitutions', json={**original, 'max_daily_loss_pct': value}).status_code == 422
