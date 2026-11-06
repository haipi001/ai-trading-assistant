const KEY='terminal-unsent-paper-forms-v1';
const fields=['evidenceMode','accountId','assetId','reportId','thesisId','side','quantity','price','rationale'];
function checked(key,value){
 if(typeof key!=='string'||key.length>2000)throw Error('票据范围键无效');
 const parts=JSON.parse(key);if(!Array.isArray(parts)||typeof parts[0]!=='string')throw Error('票据范围键无效');
 const scope=JSON.parse(parts[0]);
 if(!Array.isArray(scope)||scope.length!==6||scope.some(v=>typeof v!=='string'||v.length>128)||!Array.isArray(parts)||!['form','last'].includes(parts[1])||!value||typeof value!=='object'||Array.isArray(value))throw Error('票据草稿格式无效');
 if(parts[1]==='last'){if(parts.length!==2||Object.keys(value).some(k=>k!=='accountId')||typeof value.accountId!=='string'||value.accountId.length>128)throw Error('票据账户格式无效');}
 else{if(parts.length!==3||parts[2]!==value.accountId||Object.keys(value).some(k=>!fields.includes(k))||fields.some(k=>typeof value[k]!=='string'||value[k].length>(k==='rationale'?4000:128))||!['manual','report'].includes(value.evidenceMode)||!['buy','sell'].includes(value.side))throw Error('票据字段格式无效');}
 return [key,structuredClone(value)];
}
export function createPersistentPaperDrafts(storage){
 let values=new Map(),warning='';
 try{const raw=storage.getItem(KEY);if(raw){if(raw.length>512*1024)throw Error();const packet=JSON.parse(raw);if(!packet||Object.keys(packet).some(key=>!['schema','rows'].includes(key))||packet.schema!==1||!Array.isArray(packet.rows)||packet.rows.length>100)throw Error();const rows=packet.rows.map(([key,value])=>checked(key,value));if(new Set(rows.map(([key])=>key)).size!==rows.length)throw Error();values=new Map(rows);}}catch{warning='未能恢复未提交票据：存储不可用或内容损坏，请重新填写。';try{storage.removeItem(KEY);}catch{}}
 return Object.freeze({status:()=>warning,read:key=>values.has(key)?structuredClone(values.get(key)):null,size:()=>values.size,
  writeBatch:rows=>{if(!Array.isArray(rows)||rows.length>100||rows.some(row=>!Array.isArray(row)||row.length!==2))throw Error('票据批次格式无效');const next=new Map(values);for(const [key,value] of rows)next.set(...checked(key,value));if(next.size>100)throw Error('票据暂存已满');const raw=JSON.stringify({schema:1,rows:[...next]});if(raw.length>512*1024)throw Error('票据暂存超过512KB');storage.setItem(KEY,raw);values=next;warning='';},
  clear:()=>{values.clear();warning='';try{storage.removeItem(KEY);}catch{}}
 });
}
