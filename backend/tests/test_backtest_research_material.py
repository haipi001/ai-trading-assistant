from test_backtests import create_playbook
from test_server_account_risk import edit_db
from app.models import BacktestRun,DataSnapshot


def test_owned_backtest_material_freezes_source_and_detects_tampering(client):
    playbook=create_playbook(client)
    run=client.post('/backtest-runs',json={'strategy_playbook_id':playbook['id'],'name':'Frozen backtest','date_from':'2026-01-01','date_to':'2026-01-08','initial_capital':100,'parameters_json':{}}).json()
    path=f"/backtest-runs/{run['id']}/research-material"
    response=client.post(path)
    assert response.status_code==201,response.text
    packet=response.json();assert response.headers['cache-control']=='no-store'
    assert packet['material']['usable_for_trading'] is False
    assert packet['material']['parameters']=={}
    listing=client.get(path)
    assert listing.status_code==200 and listing.headers['cache-control']=='no-store'
    assert listing.json()['items'][0]['snapshot_id']==packet['snapshot_id']
    assert client.get(path,headers={'X-AI-Trading-User':'foreign'}).status_code==404
    read_path=path+'/'+packet['snapshot_id']
    edit_db(lambda db:setattr(db.get(BacktestRun,run['id']),'parameters_json',{'changed':True}))
    saved=client.get(read_path)
    assert saved.status_code==200 and saved.json()==packet
    assert saved.headers['cache-control']=='no-store'
    assert client.get(read_path,headers={'X-AI-Trading-User':'foreign'}).status_code==404
    assert client.post(path,headers={'X-AI-Trading-User':'foreign'}).status_code==404
    assert client.get(f"/backtest-runs/other/research-material/{packet['snapshot_id']}").status_code==404
    def tamper(db):
        snapshot=db.get(DataSnapshot,packet['snapshot_id'])
        from app.services.backtest_research_material import digest
        changed={k:v for k,v in snapshot.data_json.items() if k!='content_hash'}
        changed['parameters']={'changed':True}
        snapshot.data_json={**changed,'content_hash':digest(changed)}
    edit_db(tamper)
    assert client.get(read_path).status_code==409
    assert client.get('/orders/drafts').json()==[]
