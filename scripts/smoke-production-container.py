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
parser.add_argument('--require-clean', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
prefix = 'terminal-smoke-' + secrets.token_hex(4)
image = 'terminal-backend:production-smoke'
containers = []
network_created = False
redactions = []
CONTROLLED_USERINFO_SERVER = "import json,os\nfrom http.server import BaseHTTPRequestHandler,ThreadingHTTPServer\nclaims=json.loads(os.environ['SMOKE_OIDC_CLAIMS'])\nclass Handler(BaseHTTPRequestHandler):\n def log_message(self,*args):pass\n def do_GET(self):\n  if self.path=='/health':status,value=200,{'status':'ok'}\n  else:\n   token=self.headers.get('Authorization','').removeprefix('Bearer ')\n   value=claims.get(token) if self.path=='/userinfo' else None\n   status=200 if value else 401\n   value=value or {'error':'unauthorized'}\n  payload=json.dumps(value).encode()\n  self.send_response(status);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(payload)\nThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()\n"
proof = {'scope': 'actual Docker production-mode smoke, not Render acceptance',
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
proof['runner'] = 'github-actions' if os.environ.get('GITHUB_ACTIONS') == 'true' else 'local'
if args.require_clean and proof['worktree_dirty']:
    raise SystemExit('A clean checkout is required for this acceptance run')

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
        session_secret = secrets.token_hex(32)
        access_tokens = [secrets.token_hex(32),secrets.token_hex(32)]
        redactions.extend([password,session_secret,*access_tokens])
        env = Path(temporary)/'database.env'
        env.write_text('POSTGRES_USER=terminal_smoke\nPOSTGRES_DB=terminal_smoke\nPOSTGRES_PASSWORD='+password+'\n')
        env.chmod(0o600)
        db, redis, api = prefix+'-db',prefix+'-redis',prefix+'-api'
        start(db,'--network-alias','db','--env-file',str(env),'postgres:16-alpine')
        start(redis,'--network-alias','redis','redis:7-alpine')
        wait_for(lambda: subprocess.run(['docker','exec',db,'pg_isready','-U','terminal_smoke'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
        identity_env=Path(temporary)/'identity.env'
        identity_env.write_text('SMOKE_OIDC_CLAIMS='+json.dumps({token:{
            'sub':'controlled-user-'+str(index),'name':'Controlled smoke user',
            'iss':'http://oidc:8080','aud':'smoke-client','role':'viewer'
        } for index,token in enumerate(access_tokens)})+'\n')
        identity_env.chmod(0o600)
        oidc=prefix+'-oidc'
        start(oidc,'--network-alias','oidc','--env-file',str(identity_env),
              '--entrypoint','python',image,'-u','-c',CONTROLLED_USERINFO_SERVER)
        wait_for(lambda: subprocess.run(['docker','exec',oidc,'python','-c',
            "import urllib.request;urllib.request.urlopen('http://localhost:8080/health',timeout=2)"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
        proof['identity_source']='isolated controlled userinfo service; not a live OIDC provider'

        env.write_text('\n'.join([
            'ENVIRONMENT=production','DEPLOYMENT_TARGET=local-container-smoke',
            'RELEASE_ID='+proof['release'],'LEGACY_TENANT_USER_ID=smoke-owner',
            'DATABASE_URL=postgresql+psycopg://terminal_smoke:'+password+'@db:5432/terminal_smoke',
            'REDIS_URL=redis://redis:6379/0','MANAGED_AUTH_REQUIRED=true',
            'AUTH_SESSION_SECRET_REF=env://AUTH_SESSION_SECRET','AUTH_SESSION_SECRET='+session_secret,
            'API_RATE_LIMIT_ENABLED=true','RUNTIME_SCHEDULER_ENABLED=false',
            'EXTERNAL_LLM_CALLS_ENABLED=false','LIVE_TRADING_ENABLED=false',
            'LIVE_EXECUTION_ENABLED=false','AUTOMATION_LEVEL=A0_READ_ONLY',
            'BACKEND_CORS_ORIGINS=https://haipi001.github.io',
            'OIDC_ISSUER=http://oidc:8080','OIDC_USERINFO_URL=http://oidc:8080/userinfo',
            'OIDC_CLIENT_ID=smoke-client',
        ])+'\n')
        start(api,'--env-file',str(env),'-p','127.0.0.1::8000',image)
        port=docker('port',api,'8000/tcp').split(':')[-1]
        base='http://127.0.0.1:'+port
        def request(path, method='GET', headers=None, data=None):
            req=urllib.request.Request(base+path,method=method,headers={'Origin':'https://haipi001.github.io',**(headers or {})},data=data)
            try:
                with urllib.request.urlopen(req,timeout=4) as response:
                    raw=response.read()
                    content_type=response.headers.get('Content-Type','').lower()
                    value=(json.loads(raw) if 'application/json' in content_type else raw.decode('utf-8')) if raw else None
                    return response.status,dict(response.headers),value
            except urllib.error.HTTPError as error:
                return error.code,dict(error.headers),json.loads(error.read())
        ready=wait_for(lambda: (value if (value:=request('/health/ready'))[0]==200 else None))
        assert ready[2]['components']['database']['status']=='ok'
        assert ready[2]['components']['redis']['status']=='ok'
        assert ready[2]['components']['authentication']=={'required':True,'status':'configuration_present'}
        proof['checks']['required_auth_configuration_present']='passed'
        proof['checks']['postgres_migrations_and_readiness']='passed'
        docker('exec',api,'alembic','check')
        proof['checks']['postgres_schema_matches_model']='passed'
        for headers in [{},{'X-AI-Trading-Role':'owner','X-AI-Trading-User':'smoke-owner'}]:
            denied=request('/api/v2/workspaces/session/options',headers=headers)
            assert denied[0]==401
            assert denied[1].get('access-control-allow-origin')=='https://haipi001.github.io'
            assert denied[1].get('access-control-allow-credentials')=='true'
        proof['checks']['anonymous_and_spoofed_identity_rejected']='passed'
        proof['checks']['authentication_errors_readable_by_hosted_frontend']='passed'
        preflight=request('/api/v2/workspaces/session/options',method='OPTIONS',headers={
            'Origin':'https://haipi001.github.io','Access-Control-Request-Method':'GET'})
        assert preflight[0]==200 and preflight[1].get('access-control-allow-origin')=='https://haipi001.github.io'
        proof['checks']['public_frontend_cors']='passed'
        sessions=[]
        for index,token in enumerate(access_tokens):
            login=request('/production/auth/login',method='POST',headers={'Content-Type':'application/json'},
                          data=json.dumps({'access_token':token}).encode())
            assert login[0]==200 and login[2]['user']['user_id']=='controlled-user-'+str(index)
            assert login[2]['user']['role']=='viewer'
            sessions.append(login[2]['session_token'])
            redactions.append(sessions[-1])
        headers=[{'Authorization':'Bearer '+token,'Content-Type':'application/json'} for token in sessions]
        for index,header in enumerate(headers):
            identity=request('/api/v2/workspaces/session/options',headers=header)
            assert identity[0]==200 and identity[2]['user_id']=='controlled-user-'+str(index)
            assert identity[2]['execution_authorized'] is False
        proof['checks']['controlled_userinfo_login_and_authenticated_identity']='passed'
        workspace='/api/v2/workspaces/controlled-shared-name'
        assert request(workspace,headers=headers[0])[0]==404
        def preference(symbol):
            return json.dumps({'expected_version':0,'context':{
                'page':'market','asset_class':'stock','symbol':symbol,'venue':'NASDAQ','mode':None}}).encode()
        first=request(workspace,method='PUT',headers=headers[0],data=preference('AAPL'))
        assert first[0]==200 and first[2]['version']==1
        assert request(workspace,headers={**headers[1],'X-AI-Trading-User':'controlled-user-0','X-AI-Trading-Role':'owner'})[0]==404
        second=request(workspace,method='PUT',headers=headers[1],data=preference('NVDA'))
        assert second[0]==200 and second[2]['version']==1
        for header,symbol in zip(headers,['AAPL','NVDA']):
            saved=request(workspace,headers=header)
            assert saved[0]==200 and saved[2]['context']['symbol']==symbol
            assert saved[2]['execution_authorized'] is False
        assert request(workspace,method='PUT',headers=headers[0],data=preference('MSFT'))[0]==409
        proof['checks']['authenticated_workspace_persistence_isolation_and_cas']='passed'
        logout=request('/production/auth/logout',method='POST',headers=headers[0],
                       data=json.dumps({'session_token':sessions[0]}).encode())
        assert logout[0]==200 and logout[2]['status']=='revoked'
        revoked=request('/api/v2/workspaces/session/options',headers=headers[0])
        assert revoked[0]==401 and revoked[1].get('access-control-allow-origin')=='https://haipi001.github.io'
        assert request('/api/v2/workspaces/session/options',headers=headers[1])[0]==200
        tampered=sessions[1][:-1]+('0' if sessions[1][-1]!='0' else '1')
        assert request('/api/v2/workspaces/session/options',headers={'Authorization':'Bearer '+tampered})[0]==401
        proof['checks']['logout_revocation_and_tampered_session_rejected']='passed'

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
except BaseException as error:
    proof['status'] = 'failed'
    proof['error_type'] = type(error).__name__
    raise
finally:
    destination=Path(args.output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    api_container = next((name for name in containers if name.endswith('-api')), None)
    if api_container:
        logs=subprocess.run(['docker','logs','--tail','200',api_container],text=True,capture_output=True)
        safe_logs=logs.stdout+logs.stderr
        for value in redactions:
            if value:
                safe_logs=safe_logs.replace(value,'[redacted]')
        destination.with_suffix('.log').write_text(safe_logs)
    for name in reversed(containers):
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if network_created:
        subprocess.run(['docker','network','rm',prefix],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    destination.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
