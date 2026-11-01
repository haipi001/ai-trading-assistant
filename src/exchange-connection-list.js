export function connectionListPage(connections,{query='',exchange='all',status='all',page=0}={}){
 const needle=String(query).trim().normalize('NFKC').toLowerCase();
 const filtered=connections.filter(row=>(exchange==='all'||row.exchange===exchange)&&(status==='all'||(status==='enabled'?row.credentials_persisted&&row.status!=='disabled':row.status==='disabled'))&&(!needle||`${row.label} ${row.exchange}`.normalize('NFKC').toLowerCase().includes(needle)));
 const pages=Math.max(1,Math.ceil(filtered.length/25)),current=Math.min(Math.max(Number.isInteger(page)?page:0,0),pages-1);
 return {rows:filtered.slice(current*25,current*25+25),total:filtered.length,pages,current};
}
