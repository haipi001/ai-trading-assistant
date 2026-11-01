export function selectLargeTrades(trades,threshold,side='全部'){
 if(!Number.isFinite(threshold)||threshold<0||threshold>1e12)throw new Error('请输入0至一万亿之间的USDT门槛');
 return trades.map(row=>({...row,notional:row.price*row.quantity})).filter(row=>Number.isFinite(row.notional)&&row.notional>=threshold&&(side==='全部'||row.side===side));
}
