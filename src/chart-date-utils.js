export function utcDatePresets(now=Date.now()){
 const date=new Date(now);if(!Number.isFinite(date.getTime()))throw new Error('当前时间无效');
 const end=date.toISOString().slice(0,10),day=Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),date.getUTCDate());
 return {今天:[end,end],近7天:[new Date(day-6*86400000).toISOString().slice(0,10),end],近30天:[new Date(day-29*86400000).toISOString().slice(0,10),end],今年:[`${date.getUTCFullYear()}-01-01`,end]};
}
