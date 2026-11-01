export function depthChartModel(data,precision=.001,mode='累计深度'){
 const asks=data?.asks||[],bids=data?.bids||[];
 if(!asks.length||!bids.length)return null;
 const mid=(asks[0].price+bids[0].price)/2,step=mid*precision;
 if(!Number.isFinite(step)||step<=0)throw new Error('invalid precision');
 const group=(rows,buy)=>{
   const bins=new Map();
   for(const row of rows){const bucket=(buy?Math.floor(row.price/step):Math.ceil(row.price/step))*step;bins.set(bucket,(bins.get(bucket)||0)+row.quantity);}
   let total=0;return [...bins].sort((a,b)=>buy?b[0]-a[0]:a[0]-b[0]).map(([price,quantity])=>{total+=quantity;return {price,quantity,total,value:mode==='累计深度'?total:quantity};});
 };
 const buy=group(bids,true),sell=group(asks,false),all=[...buy,...sell];
 const min=Math.min(...all.map(row=>row.price)),max=Math.max(...all.map(row=>row.price)),peak=Math.max(...all.map(row=>row.value),1e-12);
 const points=rows=>rows.map(row=>`${40+(row.price-min)/(max-min||1)*720},${260-row.value/peak*220}`).join(' ');
 return {buy,sell,mid,buyTotal:buy.at(-1).total,sellTotal:sell.at(-1).total,min,max,peak,buyPoints:points([...buy].reverse()),sellPoints:points(sell)};
}
