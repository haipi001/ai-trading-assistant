export function chartContextAt({x,y,width,height,symbol,marketMode,decimals=2,demo},coordinateToPrice) {
  if(![x,y,width,height].every(Number.isFinite)||x<0||y<0||x>=width||y>=height)return null;
  const price=coordinateToPrice(y);
  if(!Number.isFinite(price)||price<=0)return null;
  const precision=Math.min(8,Math.max(0,Number.isInteger(decimals)?decimals:2));
  const rounded=Number(price.toFixed(precision));if(rounded<=0)return null;
  return {symbol,instrument:marketMode==='stocks'?symbol:`${symbol}/USDT`,price:rounded,decimals:precision,demo:!!demo};
}
