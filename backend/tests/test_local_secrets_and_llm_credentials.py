"""Tests for the user-imported local secret store and self-service LLM
credential import. Secret values must never appear in the database, audit
logs, or API responses — only env:// references."""

import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core import local_secrets
from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.core.local_secrets import LocalSecretError
from app.db.base import Base
from app.models import AuditLog
from app.services.human_control import HumanControlError
from app.services.human_control import HumanControlService


def owner(user_id: str = "owner-user") -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, role="owner", permissions=ROLE_PERMISSIONS["owner"], auth_required=True, token_configured=True)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    path = tmp_path / ".user_secrets.env"
    monkeypatch.setattr(local_secrets, "store_path", lambda: path)
    before = set(os.environ)
    yield path
    for name in set(os.environ) - before:
        if name.startswith("USER_") or name == "TEST_SECRET_ONE":
            os.environ.pop(name, None)


def test_secret_store_roundtrip_and_permissions(isolated_store):
    reference = local_secrets.set_user_secret("test_secret_one", "value-123")
    assert reference == "env://TEST_SECRET_ONE"
    assert os.environ["TEST_SECRET_ONE"] == "value-123"
    assert oct(isolated_store.stat().st_mode & 0o777) == "0o600"
    names = local_secrets.list_user_secret_names()
    assert {"name": "TEST_SECRET_ONE", "reference": "env://TEST_SECRET_ONE"} in names
    assert all("value-123" not in json.dumps(entry) for entry in names)
    assert local_secrets.delete_user_secret("TEST_SECRET_ONE") is True
    assert "TEST_SECRET_ONE" not in os.environ
    assert local_secrets.delete_user_secret("TEST_SECRET_ONE") is False


def test_secret_store_rejects_bad_input(isolated_store):
    with pytest.raises(LocalSecretError):
        local_secrets.set_user_secret("bad name", "x" * 10)
    with pytest.raises(LocalSecretError):
        local_secrets.set_user_secret("GOOD_NAME", "")
    with pytest.raises(LocalSecretError):
        local_secrets.set_user_secret("GOOD_NAME", "line1\nline2")


def test_llm_credentials_import_stores_reference_not_value(db, isolated_store):
    service = HumanControlService(db)
    result = service.set_llm_credentials(
        actor=owner(),
        payload={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "sk-user-supplied-test-key-123",
            "monthly_budget_usd": 10,
            "per_request_budget_usd": 0.5,
            "approved_for_research": True,
        },
    )
    assert result["status"] == "credentials_stored"
    assert result["secret_reference"].startswith("env://USER_DEEPSEEK_")
    assert result["secret_reference"] != "env://USER_DEEPSEEK_API_KEY"
    assert result["secret_value_present"] is False
    assert "sk-user-supplied-test-key-123" not in json.dumps(result)
    assert os.environ[result["secret_reference"].removeprefix("env://")] == "sk-user-supplied-test-key-123"

    config = result["config"]
    assert config["mode"] == "bring_your_own"
    assert config["provider"] == "deepseek"
    assert config["approved_for_research"] is True

    for log in db.scalars(select(AuditLog)).all():
        assert "sk-user-supplied-test-key-123" not in json.dumps(log.payload_json)


def test_llm_credentials_import_rejects_bad_provider_and_short_key(db, isolated_store):
    service = HumanControlService(db)
    with pytest.raises(HumanControlError, match="provider"):
        service.set_llm_credentials(actor=owner(), payload={"provider": "grok", "api_key": "x" * 20})
    with pytest.raises(HumanControlError, match="api_key"):
        service.set_llm_credentials(actor=owner(), payload={"provider": "deepseek", "api_key": "short"})


def test_llm_test_call_blocked_without_approval(db, isolated_store):
    service = HumanControlService(db)
    service.set_llm_credentials(
        actor=owner(),
        payload={"provider": "deepseek", "api_key": "sk-user-supplied-test-key-123", "monthly_budget_usd": 10, "per_request_budget_usd": 0.5, "approved_for_research": False},
    )
    result = service.llm_test_call(actor=owner())
    assert result["status"] == "blocked"
    assert "approval" in result["message"]


def test_llm_test_call_succeeds_through_configured_provider(db, isolated_store, monkeypatch):
    class FakeProvider:
        def generate_report(self, **kwargs):
            return json.dumps({"summary": "connectivity ok", "suggested_action": "review_only"})

    service = HumanControlService(db)
    service.set_llm_credentials(
        actor=owner(),
        payload={"provider": "deepseek", "api_key": "sk-user-supplied-test-key-123", "monthly_budget_usd": 10, "per_request_budget_usd": 0.5, "approved_for_research": True},
    )
    monkeypatch.setattr(HumanControlService, "configured_ai_provider", lambda self, *, actor: FakeProvider())
    result = service.llm_test_call(actor=owner())
    assert result["status"] == "ok"
    assert "connectivity ok" in result["message"]
    assert result["counts_as_external_evidence"] is False
    assert result["provider_mode"] == "bring_your_own"
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-flash"
    assert result["external_call_attempted"] is True


def test_local_secret_api_endpoints(client, tmp_path, monkeypatch):
    path = tmp_path / ".user_secrets.env"
    monkeypatch.setattr(local_secrets, "store_path", lambda: path)

    created = client.post("/production/local-secrets", json={"name": "user_binance_api_key", "value": "readonly-key-abc"})
    assert created.status_code == 201
    assert created.json() == {"name": "USER_BINANCE_API_KEY", "reference": "env://USER_BINANCE_API_KEY", "value_returned": False}

    listed = client.get("/production/local-secrets")
    assert listed.status_code == 200
    assert listed.json()["values_returned"] is False
    assert any(item["name"] == "USER_BINANCE_API_KEY" for item in listed.json()["secrets"])
    assert "readonly-key-abc" not in listed.text

    deleted = client.delete("/production/local-secrets/USER_BINANCE_API_KEY")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    os.environ.pop("USER_BINANCE_API_KEY", None)


def test_llm_test_call_does_not_claim_mock_connectivity(db, isolated_store, monkeypatch):
    service = HumanControlService(db)
    def unexpected(*args, **kwargs):
        raise AssertionError("mock connectivity must not invoke a provider")
    monkeypatch.setattr(HumanControlService, "configured_ai_provider", unexpected)
    result = service.llm_test_call(actor=owner())
    assert result["status"] == "blocked"
    assert result["provider_mode"] == "mock"
    assert result["external_call_attempted"] is False


@pytest.mark.parametrize("monthly,per_request", [(-1, 0), ("nan", 0), ("inf", 0), (10, "-inf"), ("invalid", 0), (10, 11)])
def test_invalid_llm_budget_does_not_replace_existing_key(db, isolated_store, monthly, per_request):
    service = HumanControlService(db)
    original = service.set_llm_credentials(actor=owner(), payload={"provider":"deepseek", "api_key":"fixture-original-key", "monthly_budget_usd":10, "per_request_budget_usd":1})
    before = isolated_store.read_bytes()
    prior_logs = len(db.scalars(select(AuditLog)).all())
    with pytest.raises(HumanControlError, match="budget"):
        HumanControlService(db).set_llm_credentials(actor=owner(), payload={
            "provider": "deepseek", "api_key": "fixture-replacement-key",
            "monthly_budget_usd": monthly, "per_request_budget_usd": per_request,
        })
    assert isolated_store.read_bytes() == before
    assert os.environ[original["secret_reference"].removeprefix("env://")] == "fixture-original-key"
    assert len(db.scalars(select(AuditLog)).all()) == prior_logs


def test_llm_keys_for_two_users_do_not_overwrite_each_other(db, isolated_store):
    service = HumanControlService(db)
    payload = {"provider":"deepseek", "monthly_budget_usd":10, "per_request_budget_usd":1}
    first = service.set_llm_credentials(actor=owner("user-one"), payload={**payload,"api_key":"fixture-user-one-key"})
    second = service.set_llm_credentials(actor=owner("user-two"), payload={**payload,"api_key":"fixture-user-two-key"})
    assert first["secret_reference"] != second["secret_reference"]
    assert os.environ[first["secret_reference"].removeprefix("env://")] == "fixture-user-one-key"
    assert os.environ[second["secret_reference"].removeprefix("env://")] == "fixture-user-two-key"


def test_research_chat_without_configuration_never_constructs_provider(db, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("unconfigured chat must not reach provider")
    monkeypatch.setattr(HumanControlService, "_provider_from_llm_config", unexpected)
    value = HumanControlService(db).research_chat(actor=owner(), payload={"question":"What data is needed?"})
    assert value["status"] == "blocked"
    assert value["reason"] == "ai_configuration_required"
    assert value["external_call_attempted"] is False


def configure_chat(service):
    return service.set_llm_credentials(actor=owner(), payload={"provider":"deepseek", "model":"fixture-model", "api_key":"fixture-chat-key-123", "monthly_budget_usd":10, "per_request_budget_usd":1, "approved_for_research":True})


def report_for(kwargs):
    return {"report_id":"fixture-report", "report_type":kwargs['report_type'], "agent_name":kwargs['agent_name'], "data_snapshot_id":kwargs['data_snapshot_id'], "summary":"Fixture research response: current market data was not supplied.", "bullish_case":"Insufficient data", "bearish_case":"Insufficient data", "key_risks":["Missing current data"], "suggested_action":"Review evidence", "confidence":0.1, "limitations":"Question and workspace labels only", "input_facts":{}, "evidence":{}}


def test_chat_uses_saved_user_model_and_validates_structured_provenance(db, isolated_store, monkeypatch):
    service=HumanControlService(db)
    saved=configure_chat(service)
    captured={}
    class Provider:
        def generate_report(self, **kwargs):
            captured['input']=kwargs
            return json.dumps(report_for(kwargs))
    def build(config):
        captured['config']=config
        return Provider()
    monkeypatch.setattr(service, '_provider_from_llm_config', build)
    value=service.research_chat(actor=owner(),payload={"question":"What data is needed?", "page":"market", "symbol":"ETH", "response_style":"detailed", "history":[{"role":"user","content":"Previous research question"},{"role":"assistant","content":"Previous research reply"}]})
    assert value['status']=='ok'
    assert value['model']=='fixture-model'
    assert value['provider']=='deepseek'
    assert value['external_call_attempted'] is True
    assert value['execution_available'] is False
    assert value['counts_as_external_evidence'] is False
    assert captured['config']['secret_reference']==saved['secret_reference']
    assert captured['input']['input_facts']['workspace']=={'page':'market','symbol':'ETH'}
    assert captured['input']['input_facts']['response_style']=='detailed'
    assert len(captured['input']['input_facts']['conversation_history'])==2
    assert 'price' not in captured['input']['input_facts']
    assert value['request_id']==captured['input']['data_snapshot_id']
    assert 'fixture-chat-key-123' not in json.dumps(value)


def test_chat_preflight_rate_block_prevents_provider_call(db, isolated_store, monkeypatch):
    service=HumanControlService(db);configure_chat(service)
    monkeypatch.setattr(service,'llm_preflight_dry_run',lambda **kwargs:{'status':'blocked','blockers':['llm_rate_limited']})
    def unexpected(*args):
        raise AssertionError('rate-limited request must not reach provider')
    monkeypatch.setattr(service,'_provider_from_llm_config',unexpected)
    value=service.research_chat(actor=owner(),payload={'question':'Research question'})
    assert value['status']=='blocked'
    assert value['external_call_attempted'] is False
    assert value['blockers']==['llm_rate_limited']


@pytest.mark.parametrize('failure',['wrong_identity','invalid_json','provider_exception'])
def test_chat_rejects_invalid_or_failed_provider_without_secret_echo(db, isolated_store, monkeypatch, failure):
    service=HumanControlService(db);configure_chat(service)
    class Provider:
        def generate_report(self,**kwargs):
            if failure=='provider_exception':raise RuntimeError('fixture-chat-key-123')
            if failure=='invalid_json':return 'fixture-chat-key-123'
            value=report_for(kwargs);value['data_snapshot_id']='another-request'
            return json.dumps(value)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:Provider())
    value=service.research_chat(actor=owner(),payload={'question':'Research question'})
    assert value['status']=='failed'
    assert value['reason']=='ai_provider_request_failed'
    assert value['external_call_attempted'] is True
    assert 'fixture-chat-key-123' not in json.dumps(value)
    for row in db.scalars(select(AuditLog)).all():
        assert 'fixture-chat-key-123' not in json.dumps(row.payload_json)


@pytest.mark.parametrize('payload',[{'question':''},{'question':'x'*4001},{'question':'question','symbol':'ETH&secret=x'},{'question':'question','page':'../config'}])
def test_chat_validates_before_any_provider_use(db, monkeypatch, payload):
    def unexpected(*args,**kwargs):
        raise AssertionError('invalid input must not reach preflight')
    service=HumanControlService(db)
    monkeypatch.setattr(service,'llm_preflight_dry_run',unexpected)
    with pytest.raises(HumanControlError,match='ai_question_invalid'):
        service.research_chat(actor=owner(),payload=payload)


@pytest.mark.parametrize('provider_name',['openai','deepseek'])
def test_chat_real_provider_adapter_uses_user_imported_key_and_model(db, isolated_store, monkeypatch, provider_name):
    from app.ai import OpenAIProvider, DeepSeekProvider
    service=HumanControlService(db)
    service.set_llm_credentials(actor=owner(),payload={'provider':provider_name,'model':'fixture-adapter-model','api_key':'fixture-adapter-key','monthly_budget_usd':10,'per_request_budget_usd':1,'approved_for_research':True})
    captured=[]
    def transport(self,payload,api_key):
        assert api_key=='fixture-adapter-key'
        assert payload['model']=='fixture-adapter-model'
        facts=json.loads(payload['input'] if provider_name=='openai' else payload['messages'][0]['content'])
        captured.append(facts)
        report=report_for(facts)
        if provider_name=='openai':
            report['input_facts']=json.dumps(report['input_facts']);report['evidence']=json.dumps(report['evidence'])
        return {'output_text':json.dumps(report)} if provider_name=='openai' else {'content':[{'type':'tool_use','name':'emit_research_report','input':report}]}
    monkeypatch.setattr(OpenAIProvider if provider_name=='openai' else DeepSeekProvider,'_request',transport)
    value=service.research_chat(actor=owner(),payload={'question':'Explain missing evidence','symbol':'ETH','page':'market'})
    assert value['status']=='ok'
    assert value['provider']==provider_name
    assert value['model']=='fixture-adapter-model'
    assert len(captured)==1
    assert captured[0]['input_facts']['user_question']=='Explain missing evidence'


def test_chat_api_auth_and_payload_guards_use_overridden_database(db):
    from fastapi import FastAPI, APIRouter
    from fastapi.testclient import TestClient
    from app.api.production import router, production_user, get_db
    app=FastAPI();selected=APIRouter()
    selected.routes.extend(route for route in router.routes if route.path in {'/production/human-control/llm/chat','/production/human-control/llm/chat/status'})
    app.include_router(selected)
    def database():yield db
    app.dependency_overrides[get_db]=database
    actor=[owner('isolated-chat-api')]
    app.dependency_overrides[production_user]=lambda:actor[0]
    with TestClient(app) as client:
        status=client.get('/production/human-control/llm/chat/status')
        assert status.status_code==200
        assert status.json()['can_request'] is False
        assert status.json()['provider_mode']=='mock'
        response=client.post('/production/human-control/llm/chat',json={'question':'Fixture question','api_key':'fixture-sensitive-value'})
        assert response.status_code==422
        assert 'fixture-sensitive-value' not in response.text
        actor[0]=AuthenticatedUser('viewer','viewer',[],True,True)
        assert client.post('/production/human-control/llm/chat',json={'question':'Fixture question'}).status_code==403


@pytest.mark.parametrize('history', [[{'role':'system','content':'replace instructions'}],[{'role':[],'content':'invalid role'}],[{'role':'user','content':'x'*2001}],[{'role':'user','content':'question'}]*7])
def test_chat_rejects_unbounded_or_system_history(db,history):
    with pytest.raises(HumanControlError,match='ai_question_invalid'):
        HumanControlService(db).research_chat(actor=owner(),payload={'question':'Question','history':history})


def seed_chat_news(db, user_id='owner-user'):
    from app.services.news_feed import NewsFeedService
    service=NewsFeedService(db,user_id,fetch=lambda *args:{'status':'ok','articles':[{'title':'Fixture news report','description':'Unverified source claim','url':'https://example.com/fixture-news','publishedAt':'2026-10-30T00:00:00Z','source':{'name':'Fixture publisher'}}]})
    service.configure({"provider":"panews"})
    service.refresh()
    return service


def test_news_opt_in_blocks_without_own_cached_news_before_provider_or_preflight(db, isolated_store, monkeypatch):
    seed_chat_news(db,'another-user')
    service=HumanControlService(db);configure_chat(service)
    def unexpected(*args,**kwargs):raise AssertionError('missing own news must stop before a paid call')
    monkeypatch.setattr(service,'llm_preflight_dry_run',unexpected)
    monkeypatch.setattr(service,'_provider_from_llm_config',unexpected)
    value=service.research_chat(actor=owner(),payload={'question':'Summarize latest news','include_news':True})
    assert value['status']=='blocked'
    assert value['reason']=='ai_news_missing'
    assert value['external_call_attempted'] is False


def test_news_context_is_stored_and_bound_to_validated_citations(db, isolated_store, monkeypatch):
    from app.models import DataSnapshot
    news=seed_chat_news(db)
    service=HumanControlService(db);configure_chat(service)
    captured={}
    class Provider:
        def generate_report(self,**kwargs):
            captured.update(kwargs)
            value=report_for(kwargs)
            value['summary']='The supplied source reports a claim [N1].'
            value['evidence']={'news_citation_ids':['N1']}
            return json.dumps(value)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:Provider())
    value=service.research_chat(actor=owner(),payload={'question':'unique-fixture-question','include_news':True})
    assert value['status']=='ok'
    assert value['cited_news_ids']==['N1']
    assert value['context_scope']=='question_history_workspace_and_news_snapshot'
    assert value['counts_as_external_evidence'] is False
    assert value['provided_news']['articles'][0]['url']=='https://example.com/fixture-news'
    snapshot=db.get(DataSnapshot,value['news_context_snapshot_id'])
    assert snapshot.user_id=='owner-user'
    assert snapshot.snapshot_type=='research_chat_news_context'
    assert snapshot.id==captured['data_snapshot_id']
    assert snapshot.data_json==captured['input_facts']['news_context']
    assert 'unique-fixture-question' not in json.dumps(snapshot.data_json)
    before=json.dumps(snapshot.data_json,sort_keys=True)
    cached=news._read('cache');cached['articles']=[];news._write('cache',cached)
    db.expire_all()
    assert json.dumps(db.get(DataSnapshot,snapshot.id).data_json,sort_keys=True)==before


@pytest.mark.parametrize('summary,ids', [('Unknown source [N99]',['N99']),('Undeclared source [N1]',[]),('No marked reference',['N1'])])
def test_unknown_or_mismatched_news_citations_fail_response_validation(db, isolated_store, monkeypatch, summary, ids):
    seed_chat_news(db)
    service=HumanControlService(db);configure_chat(service)
    class Provider:
        def generate_report(self,**kwargs):
            value=report_for(kwargs);value.update(summary=summary,evidence={'news_citation_ids':ids})
            return json.dumps(value)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:Provider())
    value=service.research_chat(actor=owner(),payload={'question':'News question','include_news':True})
    assert value['status']=='failed'
    assert value['reason']=='ai_provider_request_failed'
    assert value['external_call_attempted'] is True


def test_news_context_preserves_stale_failure_and_publication_boundaries(db):
    from app.services.research_chat_context import load_news_context
    from datetime import datetime,timedelta,timezone
    news=seed_chat_news(db)
    cached=news._read('cache')
    cached['fetched_at']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    cached['last_error']='news_source_unavailable'
    news._write('cache',cached)
    context=load_news_context(db,'owner-user')
    assert context['stale'] is True
    assert context['last_refresh_failed'] is True
    assert context['articles'][0]['published_at']=='2026-10-30T00:00:00+00:00'
    assert context['fetched_at']!=context['articles'][0]['published_at']
    assert len(context['content_hash'])==64


def test_news_opt_in_requires_boolean(db):
    with pytest.raises(HumanControlError,match='ai_question_invalid'):
        HumanControlService(db).research_chat(actor=owner(),payload={'question':'Question','include_news':'yes'})


def test_model_update_can_preserve_own_saved_key_without_rewriting_store(db, isolated_store):
    service=HumanControlService(db);saved=configure_chat(service)
    before=isolated_store.read_bytes()
    result=service.set_llm_credentials(actor=owner(),payload={'provider':'deepseek','model':'deepseek-flash','api_key':''})
    assert result['credential_written'] is False
    assert result['model']=='deepseek-flash'
    assert result['secret_reference']==saved['secret_reference']
    assert result['approved_for_research'] is True
    assert result['monthly_budget_usd']==saved['monthly_budget_usd']
    assert isolated_store.read_bytes()==before
    with pytest.raises(HumanControlError,match='api_key'):
        service.set_llm_credentials(actor=owner('another-user'),payload={'provider':'deepseek','model':'deepseek-flash'})
    with pytest.raises(HumanControlError,match='api_key'):
        service.set_llm_credentials(actor=owner(),payload={'provider':'openai','model':'fixture-model'})


def test_private_context_not_listed_by_generic_snapshot_or_preference_apis(db):
    from app.models import DataSnapshot,LocalUserConfig
    from app.services.data_sources import DataSourceService
    from app.services.daily_use import DailyUseService,DailyUseError
    row=DataSnapshot(user_id='owner-user',snapshot_type='research_chat_news_context',data_json={'articles':[{'title':'Owner source'}]},metadata_json={'request_id':'fixture-request'})
    public=DataSnapshot(snapshot_type='market_data',data_json={'price':1},metadata_json={})
    db.add_all([row,public,LocalUserConfig(user_id='owner-user',config_key='news_feed:cache',value_json={'articles':[]}),LocalUserConfig(user_id='owner-user',config_key='human_control:research_evidence',value_json={'mode':'mock'}),LocalUserConfig(user_id='owner-user',config_key='theme',value_json={'theme':'light'})]);db.commit()
    assert [item.id for item in DataSourceService(db).list_snapshots()]==[public.id]
    assert DataSourceService(db).list_snapshots(snapshot_type='research_chat_news_context')==[]
    assert [item.config_key for item in DailyUseService(db).list_local_config(user_id='owner-user')]==['theme']
    with pytest.raises(DailyUseError):DailyUseService(db).upsert_local_config(config_key='news_feed:settings',user_id='owner-user',value_json={},description=None)
    service=HumanControlService(db)
    assert service.research_news_snapshot(actor=owner(),snapshot_id=row.id)['provided_news']['articles'][0]['title']=='Owner source'
    with pytest.raises(HumanControlError,match='not_found'):service.research_news_snapshot(actor=owner('another-user'),snapshot_id=row.id)


def test_news_context_api_binds_snapshot_to_authenticated_owner(db):
    from fastapi import FastAPI,APIRouter
    from fastapi.testclient import TestClient
    from app.api.production import router,production_user,get_db
    from app.models import DataSnapshot
    row=DataSnapshot(user_id='owner-user',snapshot_type='research_chat_news_context',data_json={'articles':[{'title':'Private fixture context'}]},metadata_json={'request_id':'fixture-request'})
    db.add(row);db.commit()
    app=FastAPI();selected=APIRouter()
    selected.routes.extend(route for route in router.routes if route.path=='/production/human-control/llm/chat/news-context/{snapshot_id}')
    app.include_router(selected)
    def database():yield db
    actor=[owner()]
    app.dependency_overrides[get_db]=database
    app.dependency_overrides[production_user]=lambda:actor[0]
    with TestClient(app) as client:
        path=f'/production/human-control/llm/chat/news-context/{row.id}'
        response=client.get(path)
        assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
        assert response.json()['provided_news']['articles'][0]['title']=='Private fixture context'
        actor[0]=owner('another-user')
        response=client.get(path)
        assert response.status_code==404
        assert 'Private fixture context' not in response.text
