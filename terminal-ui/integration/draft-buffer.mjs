export function createDraftBuffer(limit=100){
 const values=new Map();
 return Object.freeze({read:key=>values.has(key)?structuredClone(values.get(key)):null,writeBatch:rows=>{
  if(!Array.isArray(rows)||rows.some(([key,value])=>typeof key!=='string'||key.length>2000||JSON.stringify(value).length>16000))throw Error('票据暂存格式无效');
  if(new Set([...values.keys(),...rows.map(([key])=>key)]).size>limit)throw Error('票据暂存已满，请先保存或清理已有草稿');
  const copies=rows.map(([key,value])=>[key,structuredClone(value)]);for(const [key,value] of copies)values.set(key,value);
 },clear:()=>values.clear(),size:()=>values.size});
}
