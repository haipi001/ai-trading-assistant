from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.auth import AuthenticatedUser, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Account, AuditLog, TerminalWorkspace, Wallet
from app.models.core import utc_now
from app.adapters.evm_rpc_readonly import resolve_chain, EvmRpcError

router = APIRouter(prefix='/api/v2/workspaces', tags=['workspaces'])


def account_markets(account):
    # Account types are existing domain metadata, not execution permissions.
    return {'brokerage':['stocks'], 'broker':['stocks'],
            'exchange':['cex'], 'exchange_account':['cex'], 'crypto_exchange':['cex']}.get(account.account_type, [])


def wallet_chain_id(wallet):
    try:
        return str(resolve_chain(wallet.chain)[0])
    except EvmRpcError:
        return None


class WorkspaceContext(BaseModel):
    model_config = {'extra':'forbid'}
    page: Literal['home','market','flash','news','strategy','chain','assets','auth','data','more']
    tab: str | None = Field(default=None,max_length=128)
    asset_class: Literal['crypto_spot','crypto_derivative','stock','etf','onchain','other']
    symbol: str | None = Field(default=None,max_length=128)
    venue: str | None = Field(default=None,max_length=128)
    timeframe: str | None = Field(default=None,max_length=128)
    source: str | None = Field(default=None,max_length=128)
    account_id: str | None = Field(default=None,max_length=128)
    mode: Literal['DEMO','PAPER','LIVE'] | None = None
    market: Literal['stocks','cex','onchain'] | None = None
    chain_id: str | None = Field(default=None,pattern=r'^[1-9][0-9]{0,19}$')
    contract_address: str | None = Field(default=None,pattern=r'^0x[0-9a-fA-F]{40}$')
    wallet_id: str | None = Field(default=None,max_length=128)
    context_version: int | None = Field(default=None,ge=0)

    @model_validator(mode='after')
    def validate_market_identity(self):
        if self.market != 'onchain' and any((self.chain_id,self.contract_address,self.wallet_id)):
            raise ValueError('chain identity requires onchain market')
        if self.market == 'onchain' and (not self.chain_id or self.asset_class != 'onchain' or self.mode == 'LIVE'):
            raise ValueError('onchain workspace requires chain and readonly asset identity')
        return self


class WorkspacePanel(BaseModel):
    model_config = {'extra':'forbid'}
    panel_id: int = Field(ge=0,le=3)
    function_code: str = Field(pattern=r'^[A-Z][A-Z0-9_]{0,31}$')
    terminal_symbol: str = Field(default='',max_length=128,pattern=r'^[-A-Za-z0-9./:_]*$')
    locked: bool = False
    context: WorkspaceContext


class WorkspaceLock(BaseModel):
    model_config = {'extra':'forbid'}
    key: str = Field(pattern=r'^(main|[0-3]):[A-Z][A-Z0-9_]{0,31}$')
    context: WorkspaceContext


class WorkspaceMarketView(BaseModel):
    model_config = {'extra':'forbid'}
    market: Literal['stocks','cex','onchain']
    panel_count: Literal[1,2,4]
    focused_panel: int = Field(ge=0,le=3)
    last_function_code: str = Field(pattern=r'^[A-Z][A-Z0-9_]{0,31}$')
    last_terminal_symbol: str = Field(default='',max_length=128,pattern=r'^[-A-Za-z0-9./:_]*$')
    panels: list[WorkspacePanel] = Field(min_length=4,max_length=4)
    locked_contexts: list[WorkspaceLock] = Field(default_factory=list,max_length=300)
    split_columns: float = Field(default=.5,ge=.2,le=.8)
    split_rows: float = Field(default=.5,ge=.2,le=.8)

    @model_validator(mode='after')
    def validate_market_view(self):
        if self.focused_panel>=self.panel_count or {panel.panel_id for panel in self.panels}!={0,1,2,3}:
            raise ValueError('invalid market panel identity or focus')
        keys=[lock.key for lock in self.locked_contexts]
        if len(set(keys))!=len(keys):
            raise ValueError('duplicate market panel lock')
        return self


class WorkspaceLayout(BaseModel):
    model_config = {'extra':'forbid'}
    agent_open: bool = False
    density: Literal['standard','compact'] = 'standard'
    panel_count: Literal[1,2,4] = 1
    focused_panel: int = Field(default=0,ge=0,le=3)
    panels: list[WorkspacePanel] = Field(default_factory=list,max_length=4)
    market_contexts: list[WorkspaceContext] = Field(default_factory=list,max_length=3)
    market_workspaces: list[WorkspaceMarketView] = Field(default_factory=list,max_length=3)
    split_columns: float = Field(default=.5,ge=.2,le=.8)
    split_rows: float = Field(default=.5,ge=.2,le=.8)

    @model_validator(mode='after')
    def validate_panels(self):
        markets=[context.market for context in self.market_contexts]
        if any(market is None for market in markets) or len(set(markets)) != len(markets):
            raise ValueError('invalid market context list')
        views=[view.market for view in self.market_workspaces]
        if len(set(views))!=len(views):
            raise ValueError('duplicate market workspace')
        ids=[panel.panel_id for panel in self.panels]
        if len(set(ids)) != len(ids) or any(value >= self.panel_count for value in ids) or self.focused_panel >= self.panel_count:
            raise ValueError('invalid panel identity or focus')
        return self


class WorkspaceSave(BaseModel):
    model_config = {'extra':'forbid'}
    expected_version: int = Field(ge=0)
    context: WorkspaceContext
    layout: WorkspaceLayout = Field(default_factory=WorkspaceLayout)


def packet(row):
    return {'workspace_id':row.workspace_id,'version':row.version,'context':row.context_json,
            'layout':row.layout_json,'updated_at':row.updated_at,'source':'server_workspace_preferences',
            'execution_authorized':False}


@router.get('/session/context')
def workspace_session_context(actor: AuthenticatedUser = Depends(require_permission('read'))):
    return {'user_id':actor.user_id,'role':actor.role,
            'auth_mode':'managed' if get_settings().managed_auth_required else 'local',
            'execution_authorized':False}


@router.get('/session/options')
def workspace_identity_options(actor: AuthenticatedUser = Depends(require_permission('read')), db: Session = Depends(get_db)):
    accounts=list(db.scalars(select(Account).where(Account.user_id==actor.user_id).order_by(Account.name,Account.id).limit(501)))
    wallets=list(db.scalars(select(Wallet).where(Wallet.user_id==actor.user_id,Wallet.is_active.is_(True)).order_by(Wallet.id).limit(501)))
    if len(accounts)>500 or len(wallets)>500:
        raise HTTPException(413,'workspace identity list exceeds selection limit')
    return {'user_id':actor.user_id,'execution_authorized':False,'source':'owned_workspace_identities',
            'accounts':[{'id':a.id,'label':a.name,'account_type':a.account_type,'broker':a.broker,
                         'base_currency':a.base_currency,'mode':a.mode,'markets':account_markets(a),
                         'paper_eligible':a.mode=='paper' and not a.live_trading_enabled and bool(account_markets(a))} for a in accounts],
            'wallets':[{'id':w.id,'label':w.label or w.address[:8]+'…'+w.address[-6:],
                        'chain':w.chain,'chain_id':wallet_chain_id(w)} for w in wallets]}


@router.get('/{workspace_id}')
def read_workspace(workspace_id: str = Path(pattern=r'^[A-Za-z0-9_-]{1,128}$'),
                   actor: AuthenticatedUser = Depends(require_permission('read')), db: Session = Depends(get_db)):
    row = db.scalar(select(TerminalWorkspace).where(TerminalWorkspace.user_id == actor.user_id, TerminalWorkspace.workspace_id == workspace_id))
    if row is None: raise HTTPException(404,'workspace not found')
    return packet(row)


@router.put('/{workspace_id}')
def save_workspace(payload: WorkspaceSave, workspace_id: str = Path(pattern=r'^[A-Za-z0-9_-]{1,128}$'),
                   actor: AuthenticatedUser = Depends(require_permission('read')), db: Session = Depends(get_db)):
    contexts=[payload.context,*(panel.context for panel in payload.layout.panels),*payload.layout.market_contexts]
    for view in payload.layout.market_workspaces:
        contexts.extend(panel.context for panel in view.panels)
        contexts.extend(lock.context for lock in view.locked_contexts)
    for context in contexts:
        if context.account_id:
            account = db.get(Account,context.account_id)
            if account is None or account.user_id != actor.user_id: raise HTTPException(404,'workspace account not found')
            if context.market and context.market not in account_markets(account): raise HTTPException(422,'workspace account market mismatch')
        if context.wallet_id:
            wallet = db.get(Wallet,context.wallet_id)
            if wallet is None or wallet.user_id != actor.user_id: raise HTTPException(404,'workspace wallet not found')
            if not wallet.is_active or context.chain_id != wallet_chain_id(wallet): raise HTTPException(422,'workspace wallet chain mismatch or inactive wallet')
    now = utc_now()
    values = {'context_json':payload.context.model_dump(),'layout_json':payload.layout.model_dump(),'updated_at':now,'version':payload.expected_version+1}
    try:
        if payload.expected_version == 0:
            db.add(TerminalWorkspace(user_id=actor.user_id,workspace_id=workspace_id,**values))
            db.flush()
        else:
            result = db.execute(update(TerminalWorkspace).where(TerminalWorkspace.user_id==actor.user_id,
                TerminalWorkspace.workspace_id==workspace_id,TerminalWorkspace.version==payload.expected_version).values(**values))
            if result.rowcount != 1:
                db.rollback()
                raise HTTPException(409,'workspace changed; reload before saving')
        db.add(AuditLog(actor_type='user',actor_id=actor.user_id,action='workspace.saved',entity_type='TerminalWorkspace',
                        entity_id=workspace_id,payload_json={'version':values['version']}))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,'workspace changed; reload before saving') from exc
    return read_workspace(workspace_id,actor,db)
