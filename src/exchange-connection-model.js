export const exchangeErrors={probe_snapshot_mismatch:'后端返回的交易所或保存状态与本次请求不一致，未接受此连接结果；请检查下方已保存连接，避免重复保存。',invalid_exchange_snapshot:'后端连接结果字段校验失败，请重新验证。',key_permission_identity_unavailable:'交易所未返回可与当前Key精确匹配的权限记录，未完成只读验证。',unsupported_account_mode:'当前连接入口不支持此账户模式。',exchange_access_restricted:'交易所拒绝当前网络或地区访问，请核对官方适用区域和账户站点。',invalid_passphrase:'Passphrase格式不正确。',invalid_credentials_fields:'请填写完整的API Key和Secret。',invalid_credentials_format:'密钥格式不正确。',reading_permission_missing:'交易所未授予读取权限。',withdrawal_permission_not_disabled:'提现权限未明确关闭，拒绝接入。',readonly_key_required:'此入口仅接受只读API Key，请关闭交易、转账等权限。',readonly_permissions_incomplete_or_enabled:'只读权限不完整或含交易/转账权限，拒绝接入。',key_ip_or_permissions_rejected:'交易所拒绝请求，请检查Key、IP白名单和权限。',exchange_rate_limited:'交易所限流，请稍后重试。',exchange_network_unavailable:'后端暂时无法访问交易所。',exchange_request_rejected:'交易所拒绝了签名请求。',exchange_redirect_rejected:'交易所返回重定向，连接已停止。'};
export const EXCHANGES=['binance','okx','bybit','bitget','gate'];
export function connectionError(error){return exchangeErrors[error?.code]||(error?.status===403?'当前后端身份没有凭证管理权限。':error?.status===401?'请先登录交易后端。':'请求未完成，请检查后端与网络后重试。');}
export function validateExchangeSnapshot(value){
 const invalid=()=>{throw Object.assign(new Error('invalid_exchange_snapshot'),{code:'invalid_exchange_snapshot'});};
 if(!value||value.status!=='verified_readonly'||!EXCHANGES.includes(value.exchange)||!Number.isFinite(Date.parse(value.checked_at))||value.permissions?.reading!==true||['trading','transfers','withdrawals'].some(key=>value.permissions?.[key]!==false)||!Array.isArray(value.balances)||value.balances.length>10000)invalid();
 const seen=new Set();
 const amount=value=>value===null||value===undefined?null:typeof value==='string'&&value.length<=128&&/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value)&&Number.isFinite(Number(value))?value:invalid();
 const balances=value.balances.map(row=>{if(!row||typeof row.asset!=='string'||!/^[a-z\d._-]{1,32}$/i.test(row.asset)||seen.has(row.asset.toUpperCase()))invalid();seen.add(row.asset.toUpperCase());return {asset:row.asset,free:amount(row.free),locked:amount(row.locked),wallet_balance:amount(row.wallet_balance),equity:amount(row.equity)};});
 return {id:typeof value.id==='string'?value.id:undefined,exchange:value.exchange,status:value.status,checked_at:value.checked_at,permissions:{reading:true,trading:false,transfers:false,withdrawals:false},balance_scope:typeof value.balance_scope==='string'?value.balance_scope:undefined,credentials_persisted:value.credentials_persisted===true,balances};
}
export function validateConnectionList(value){
 const invalid=()=>{throw Object.assign(new Error('invalid_connections_list'),{code:'invalid_connections_list'});};
 if(!Array.isArray(value)||value.length>1000)invalid();
 const seen=new Set();
 return value.map(row=>{
  if(!row||typeof row.id!=='string'||!row.id||row.id.length>80||seen.has(row.id)||!EXCHANGES.includes(row.exchange)||typeof row.label!=='string'||row.label.length>255||typeof row.status!=='string'||row.status.length>64||typeof row.credentials_persisted!=='boolean'||(row.checked_at!==null&&!Number.isFinite(Date.parse(row.checked_at))))invalid();
  seen.add(row.id);
  return {id:row.id,label:row.label,exchange:row.exchange,status:row.status,checked_at:row.checked_at,credentials_persisted:row.credentials_persisted};
 });
}

export function validateConnectionSnapshot(value,connection){
 const result=validateExchangeSnapshot(value);
 if(!connection||result.id!==connection.id||result.exchange!==connection.exchange||!result.credentials_persisted)throw Object.assign(new Error('connection_snapshot_mismatch'),{code:'connection_snapshot_mismatch'});
 return result;
}

export function validateProbeSnapshot(value,exchange,persisted){
 const result=validateExchangeSnapshot(value);
 if(!EXCHANGES.includes(exchange)||typeof persisted!=='boolean'||result.exchange!==exchange||typeof value.credentials_persisted!=='boolean'||result.credentials_persisted!==persisted||(persisted&&(!result.id||result.id.length>80)))throw Object.assign(new Error('probe_snapshot_mismatch'),{code:'probe_snapshot_mismatch'});
 return result;
}
