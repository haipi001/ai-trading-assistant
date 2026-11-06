"""Exercise the actual Docker entrypoint against disposable PostgreSQL/Redis.

No user data, account credentials, model calls or live orders are involved.
All containers/networks are removed, including on failure. Image remains cached.
"""
import argparse
import json
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--skip-build', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
prefix = 'terminal-smoke-' + secrets.token_hex(4)
image = 'terminal-backend:production-smoke'
containers = []
network_created = False
proof = {'scope': 'local actual Docker production-mode smoke, not Render acceptance',
         'release': subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
         'live_execution': False, 'status': 'incomplete', 'checks': {}}

source_files = [root/'backend'/name for name in ['Dockerfile','.dockerignore','pyproject.toml','alembic.ini']]
source_files += sorted((root/'backend/app').rglob('*.py'))
source_files += sorted((root/'backend/alembic').rglob('*.py'))
fingerprint = hashlib.sha256()
for path in source_files:
    fingerprint.update(str(path.relative_to(root)).encode()+b'\0'+path.read_bytes()+b'\0')
proof['backend_source_sha256'] = fingerprint.hexdigest()
proof['worktree_dirty'] = bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True))

def docker(*arguments):
    return subprocess.check_output(['docker', *arguments], text=True).strip()

def wait_for(check, timeout=90):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except Exception as error:
            last = type(error).__name__
        time.sleep(1)
    raise RuntimeError('smoke check timed out: ' + str(last))

def start(name, *arguments):
    containers.append(name)
    docker('run','-d','--name',name,'--network',prefix,*arguments)

try:
    if not args.skip_build:
        subprocess.run(['docker','build','-t',image,str(root/'backend')],check=True)
    proof['image_id'] = docker('image','inspect',image,'--format','{{.Id}}')
    assert docker('image','inspect',image,'--format','{{.Config.User}}') not in {'','0','root'}
    proof['checks']['non_root_image']='passed'
    docker('network','create',prefix)
    network_created = True
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        password = secrets.token_hex(24)
        env = Path(temporary)/'database.env'
        env.write_text('POSTGRES_USER=terminal_smoke\nPOSTGRES_DB=terminal_smoke\nPOSTGRES_PASSWORD='+password+'\n')
        env.chmod(0o600)
        db, redis, api = prefix+'-db',prefix+'-redis',prefix+'-api'
        start(db,'--network-alias','db','--env-file',str(env),'postgres:16-alpine')
        start(redis,'--network-alias','redis','redis:7-alpine')
        wait_for(lambda: subprocess.run(['docker','exec',db,'pg_isready','-U','terminal_smoke'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
        env.write_text('\n'.join([
            'ENVIRONMENT=production','DEPLOYMENT_TARGET=local-container-smoke',
            'RELEASE_ID='+proof['release'],'LEGACY_TENANT_USER_ID=smoke-owner',
            'DATABASE_URL=postgresql+psycopg://terminal_smoke:'+password+'@db:5432/terminal_smoke',
            'REDIS_URL=redis://redis:6379/0','MANAGED_AUTH_REQUIRED=true',
            'AUTH_SESSION_SECRET_REF=env://AUTH_SESSION_SECRET','AUTH_SESSION_SECRET='+secrets.token_hex(32),
            'API_RATE_LIMIT_ENABLED=true','RUNTIME_SCHEDULER_ENABLED=false',
            'EXTERNAL_LLM_CALLS_ENABLED=false','LIVE_TRADING_ENABLED=false',
            'LIVE_EXECUTION_ENABLED=false','AUTOMATION_LEVEL=A0_READ_ONLY',
            'BACKEND_CORS_ORIGINS=https://haipi001.github.io',
        ])+'\n')
        start(api,'--env-file',str(env),'-p','127.0.0.1::8000',image)
        port=docker('port',api,'8000/tcp').split(':')[-1]
        base='http://127.0.0.1:'+port
        def request(path, method='GET', headers=None, data=None):
            req=urllib.request.Request(base+path,method=method,headers=headers or {},data=data)
            try:
                with urllib.request.urlopen(req,timeout=4) as response:
                    raw=response.read()
                    return response.status,dict(response.headers),json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                return error.code,dict(error.headers),json.loads(error.read())
        ready=wait_for(lambda: (value if (value:=request('/health/ready'))[0]==200 else None))
        assert ready[2]['components']['database']['status']=='ok'
        assert ready[2]['components']['redis']['status']=='ok'
        proof['checks']['postgres_migrations_and_readiness']='passed'
        docker('exec',api,'alembic','check')
        proof['checks']['postgres_schema_matches_model']='passed'
        for headers in [{},{'X-AI-Trading-Role':'owner','X-AI-Trading-User':'smoke-owner'}]:
            assert request('/api/v2/workspaces/session/options',headers=headers)[0]==401
        proof['checks']['anonymous_and_spoofed_identity_rejected']='passed'
        preflight=request('/api/v2/workspaces/session/options',method='OPTIONS',headers={
            'Origin':'https://haipi001.github.io','Access-Control-Request-Method':'GET'})
        assert preflight[0]==200 and preflight[1].get('access-control-allow-origin')=='https://haipi001.github.io'
        proof['checks']['public_frontend_cors']='passed'
        flags=json.loads(docker('exec',api,'python','-c',
            'import json;from app.core.config import get_settings;s=get_settings();print(json.dumps([s.live_trading_enabled,s.live_execution_enabled,s.external_llm_calls_enabled,s.managed_auth_required]))'))
        assert flags==[False,False,False,True]
        proof['checks']['live_and_external_model_disabled']='passed'
        docker('stop',db)
        unavailable=request('/health/ready')
        assert unavailable[0]==503 and unavailable[2]['components']['database']['status']=='unavailable'
        proof['checks']['database_outage_readiness_fails_closed']='passed'
        docker('start',db)
        wait_for(lambda: request('/health/ready')[0]==200)
        proof['checks']['database_recovery']='passed'
        counts=docker('exec',db,'psql','-U','terminal_smoke','-d','terminal_smoke','-t','-A','-c',
            'SELECT (SELECT count(*) FROM order_intents), (SELECT count(*) FROM executions);')
        assert counts=='0|0'
        proof['checks']['no_orders_or_executions']='passed'
        proof['status']='passed'
finally:
    for name in reversed(containers):
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if network_created:
        subprocess.run(['docker','network','rm',prefix],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    destination=Path(args.output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
