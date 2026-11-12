import {strategyMoneyContext} from './strategy-money-context.js';
import {strategyParameterReview} from './strategy-parameter-review.js';
export function strategyMaterialRequest(form,context){
 if(!context?.identityUserId||!context.accountVerified||!context.accountId||!['stocks','cex'].includes(context.market)||!Number.isSafeInteger(context.contextVersion)||context.contextVersion<0)throw Error('请先在顶部选择已校验的股票或CEX账户');
 const parameters=strategyParameterReview(form,context).parameters,units=strategyMoneyContext(parameters.coin,context);
 for(const [field,expected] of [['budget_currency',units.budgetCurrency],['quote_currency',units.quoteCurrency]])if(expected){if(parameters[field]&&parameters[field]!==expected)throw Error('参数币种与当前工作区不一致，请重新准备');parameters[field]=expected;}
 return {account_id:context.accountId,market:context.market,context_version:context.contextVersion,parameters};
}
export function strategyMaterialPacket(packet,request){
 const m=packet?.material;
 if(typeof packet?.snapshot_id!=='string'||!packet.snapshot_id||packet.snapshot_id.length>128||packet.execution_available!==false||m?.schema_version!==1||m.source!=='user_local_strategy_parameters'||m.execution_available!==false||m.usable_for_trading!==false||m.independently_verified!==false||!Number.isFinite(Date.parse(m.captured_at))||!/^[a-f0-9]{64}$/.test(m.content_hash||''))throw Error('策略参数材料响应无效');
 for(const key of ['account_id','market','context_version'])if(m[key]!==request[key])throw Error('策略参数材料范围已变化');
 const keys=Object.keys(request.parameters);
 if(!m.parameters||Object.keys(m.parameters).length!==keys.length||keys.some(key=>JSON.stringify(m.parameters[key])!==JSON.stringify(request.parameters[key])))throw Error('策略参数材料与当前编辑内容不一致');
 return structuredClone(packet);
}
