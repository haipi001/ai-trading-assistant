import {spotDcaConfiguration} from './spot-dca-configuration.js';
import {gridConfiguration,checkGridParameters} from './grid-parameter-check.js';
export function strategyContext(value){
 if(value?.schema_version!==1||value.source!=='user_local_strategy_parameters'||value.execution_available!==false||value.usable_for_trading!==false||value.independently_verified!==false||!['stocks','cex'].includes(value.market)||typeof value.account_id!=='string'||!value.account_id||!Number.isSafeInteger(value.context_version)||value.context_version<0||!/^[a-f0-9]{64}$/.test(value.content_hash||'')||!Number.isFinite(Date.parse(value.captured_at)))throw Error('invalid strategy material');
 const limits={name:200,coin:128,type:128,amount:30,platform:200,risk:64,trigger:200,invalidation:200,constraints:400};
 if(!value.parameters||Object.keys(value.parameters).length!==(9+(value.parameters.grid?1:0)+(value.parameters.dca?1:0)+['budget_currency','quote_currency'].filter(key=>value.parameters[key]!=null).length)||Object.entries(limits).some(([key,max])=>typeof value.parameters[key]!=='string'||value.parameters[key].length>max)||!value.parameters.name||!value.parameters.coin||!/^\d+(\.\d+)?$/.test(value.parameters.amount)||Number(value.parameters.amount)<=0)throw Error('invalid strategy parameters');
 for(const key of ['budget_currency','quote_currency'])if(value.parameters[key]!=null&&!/^[A-Z0-9]{2,12}$/.test(value.parameters[key]))throw Error('invalid parameter currency');
 if(value.parameters.grid){gridConfiguration(value.parameters.grid);checkGridParameters({lower:value.parameters.grid.lower,upper:value.parameters.grid.upper,gridCount:String(value.parameters.grid.intervals),amount:value.parameters.amount});}
 if(value.parameters.dca){if(value.parameters.grid)throw Error('mixed strategy configurations');spotDcaConfiguration(value.parameters.dca);}
 return value;
}
export function strategyAttachmentMatches(attachment,context,now=Date.now()){
 try{const m=strategyContext(attachment?.material),r=attachment.reference;
 return !!context&&context.accountVerified===true&&attachment.ownerUserId===context.identityUserId&&m.account_id===context.accountId&&m.market===context.market&&m.context_version===context.contextVersion&&Number.isFinite(now)&&now-Date.parse(m.captured_at)>=-30000&&now-Date.parse(m.captured_at)<=600000&&r?.snapshot_id&&['account_id','market','context_version','content_hash'].every(key=>r[key]===m[key]);
 }catch{return false;}
}
export function strategyReadiness(attachment,enabled,context,others={}){
 if(!attachment&&!enabled)return '';
 if(!enabled)return '请显式选择策略参数附件，或取消这次策略准备后手动提问。';
 if(!strategyAttachmentMatches(attachment,context))return '策略材料已过期或账户/参数范围不匹配，请回原编辑页重新准备。';
 if(others.includeMarket||others.includeOnchain||others.includePortfolio||others.includePaperReview||others.pageAction)return '策略参数暂不能与行情、链上、账本、Paper或专属页面动作混用。';
 return '';
}
