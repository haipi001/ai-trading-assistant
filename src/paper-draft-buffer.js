const fields=['evidenceMode','accountId','assetId','reportId','thesisId','side','quantity','price','rationale'];
const fallback=new Map();
const fallbackBuffer={read:key=>fallback.has(key)?structuredClone(fallback.get(key)):null,writeBatch:rows=>{if(new Set([...fallback.keys(),...rows.map(([key])=>key)]).size>100)throw Error('票据暂存已满');for(const [key,value] of rows)fallback.set(key,structuredClone(value));}};
function buffer(){try{if(typeof window!=='undefined'&&window.parent!==window&&window.parent.location.origin===window.location.origin&&window.parent.TerminalDraftBuffer)return window.parent.TerminalDraftBuffer;}catch{}return fallbackBuffer;}
export function emptyPaperForm(){return {evidenceMode:'manual',accountId:'',assetId:'',reportId:'',thesisId:'',side:'buy',quantity:'',price:'',rationale:''};}
export function paperDraftScope({userId='local',market='legacy',symbol='',venue='',chainId='',contractAddress=''}){return JSON.stringify([userId,market,symbol,venue,chainId,contractAddress]);}
export function savePaperDraft(scope,form,store=buffer()){
 const value={};for(const key of fields){const field=form[key]??'';if(typeof field!=='string'||field.length>(key==='rationale'?4000:128))throw Error('未提交票据字段无效');value[key]=field;}
 if(!['manual','report'].includes(value.evidenceMode)||!['buy','sell'].includes(value.side))throw Error('未提交票据类型无效');
 store.writeBatch([[JSON.stringify([scope,'form',value.accountId]),value],[JSON.stringify([scope,'last']),{accountId:value.accountId}]]);
}
export function readPaperDraft(scope,accountId,store=buffer()){
 const selected=accountId??store.read(JSON.stringify([scope,'last']))?.accountId??'';
 const value=store.read(JSON.stringify([scope,'form',selected]));return value?{...emptyPaperForm(),...value}:null;
}

export function paperDraftStorageStatus(){return buffer().status?.()||'';}
