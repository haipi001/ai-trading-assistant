export function balanceListPage(balances,query='',page=0){
 const needle=String(query).trim().normalize('NFKC').toUpperCase();
 const filtered=balances.filter(row=>row.asset.normalize('NFKC').toUpperCase().includes(needle));
 const pages=Math.max(1,Math.ceil(filtered.length/50)),current=Math.min(Math.max(Number.isInteger(page)?page:0,0),pages-1);
 return {rows:filtered.slice(current*50,current*50+50),total:filtered.length,pages,current};
}
