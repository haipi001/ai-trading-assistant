export const CONSTITUTION_LIMITS = [
 ['max_single_position_pct','单一持仓上限',20],['max_asset_class_pct','单一资产类别上限',60],
 ['max_crypto_pct','加密资产上限',20],['max_single_exchange_pct','单一交易所上限',30],
 ['max_daily_loss_pct','每日亏损上限',2],['max_monthly_drawdown_pct','月度回撤上限',8],
];
export const CONSTITUTION_DEFAULT = {
 name:'我的投资宪章',investment_style:'长期投资与纪律交易',allowed_markets:['stock','etf','crypto'],
 forbidden_assets:[],forbidden_actions:[],...Object.fromEntries(CONSTITUTION_LIMITS.map(([k,,v])=>[k,v/100])),
 leverage_allowed:false,derivatives_allowed:false,auto_execution_allowed:false,human_approval_required:true,cooldown_rules_json:{},
};
export function constitutionFields(record){return Object.fromEntries(Object.keys(CONSTITUTION_DEFAULT).map(k=>[k,structuredClone(record[k]??CONSTITUTION_DEFAULT[k])]))}
export function constitutionChanges(before,after){return Object.keys(CONSTITUTION_DEFAULT).filter(k=>k!=='cooldown_rules_json'&&JSON.stringify(before[k])!==JSON.stringify(after[k])).map(key=>({key,before:before[key],after:after[key]}))}
export function validateConstitution(form){
 if(!form.name.trim()||!form.investment_style.trim())return '请填写宪章名称和投资风格';
 for(const [key,label] of CONSTITUTION_LIMITS)if(!Number.isFinite(form[key])||form[key]<0||form[key]>1)return `${label}应在 0–100% 之间`;
 if(!form.allowed_markets.length)return '请至少选择一个允许市场';
 return '';
}
export function memoryEvidence(notes,ids){return ids.map(id=>notes.find(note=>note.id===id)).filter(Boolean).map(note=>({id:note.id,title:note.title,body:note.body||'',tags:note.tags||[],kind:note.kind||'note',captured_at:new Date().toISOString()}))}
export function revisionPayload(form,{userId,reason,evidence,baseId,principles}){
 if(validateConstitution(form))throw Error(validateConstitution(form));
 if(!reason.trim())throw Error('请填写本次迭代理由');
 return {...constitutionFields(form),user_id:userId,version:new Date().toISOString(),is_active:true,
 cooldown_rules_json:{...form.cooldown_rules_json,constitution_memory_v1:{reason:reason.trim(),principles,base_id:baseId||null,evidence}}};
}
