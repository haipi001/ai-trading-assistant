export const MANUAL_THESIS_LIMITS=Object.freeze({reason:4000,drivers:10000,invalidation:10000,horizon:64,target:2000,lossPct:128,confidence:128});
export function emptyManualThesisForm(){return Object.fromEntries(Object.keys(MANUAL_THESIS_LIMITS).map(key=>[key,'']));}
export function checkedManualThesisDraft(value,accountId,assetId){
 const allowed=[...Object.keys(MANUAL_THESIS_LIMITS),'accountId','assetId','outcome'];
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!allowed.includes(key))||!accountId||!assetId||typeof accountId!=='string'||typeof assetId!=='string'||accountId.length>128||assetId.length>128||value.accountId!==accountId||value.assetId!==assetId||!['draft','unconfirmed'].includes(value.outcome))throw Error('人工假设暂存范围或状态无效');
 for(const [key,limit] of Object.entries(MANUAL_THESIS_LIMITS))if(typeof value[key]!=='string'||value[key].length>limit)throw Error('人工假设暂存字段无效');
 return structuredClone(value);
}
