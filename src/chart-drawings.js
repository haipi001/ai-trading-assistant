export const DRAWING_POINT_COUNTS={水平线:1,文本:1,趋势线:2,矩形:2,测量:2,斐波那契:2,平行线:3};
export function drawingScope(symbol,venue,marketMode){return `${marketMode}:${venue}:${symbol}`;}
export function validAnchor(point){return !!point&&Number.isSafeInteger(point.time)&&point.time>0&&point.time<=253402300799&&Number.isFinite(point.price)&&point.price>0;}
export function validateAnchoredDrawing(value){
  const count=DRAWING_POINT_COUNTS[value?.type];
  if(value?.schema!==2||typeof value.id!=='string'||typeof value.scope!=='string'||value.scope.length>300||!Array.isArray(value.points)||!value.points.every(validAnchor)||(value.type==='画笔'?(value.points.length<2||value.points.length>1000):value.points.length!==count)||value.type==='文本'&&(typeof value.text!=='string'||!value.text.trim()||value.text.length>200))throw new Error('绘图锚点无效');
  if(["locked","hidden"].some(key=>value[key]!==undefined&&typeof value[key]!=="boolean"))throw new Error("绘图锁定或可见设置无效");
  if(value.style && (!/^#[0-9a-f]{6}$/i.test(value.style.color)||!Number.isInteger(value.style.width)||value.style.width<1||value.style.width>5))throw new Error("绘图样式无效");
  return structuredClone(value);
}
export function anchorAt({x,y,width,height},candles,coordinateToLogical,coordinateToPrice,magnet=false){
  if(![x,y,width,height].every(Number.isFinite)||x<0||x>=width||y<0||y>=height)return null;
  const logical=coordinateToLogical(x);if(!Number.isFinite(logical))return null;
  const candle=candles[Math.round(logical)];if(!candle)return null;
  let price=coordinateToPrice(y);if(!Number.isFinite(price)||price<=0)return null;
  if(magnet)price=[candle.open,candle.high,candle.low,candle.close].reduce((best,value)=>Math.abs(value-price)<Math.abs(best-price)?value:best,candle.close);
  return {time:candle.time,price};
}
export function anchorLogical(time,candles){
  if(!candles.length)return null;
  let low=0,high=candles.length-1;
  while(low<=high){const mid=(low+high)>>1;if(candles[mid].time===time)return mid;if(candles[mid].time<time)low=mid+1;else high=mid-1;}
  if(high<0||low>=candles.length)return null;
  return high+(time-candles[high].time)/(candles[low].time-candles[high].time);
}
export function measurement(points){if(points.length<2||!validAnchor(points[0])||!validAnchor(points[1]))return null;return {price:points[1].price-points[0].price,percent:100*(points[1].price/points[0].price-1),seconds:points[1].time-points[0].time};}
export function parseAnchorFields(time,price){
  if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(time))throw new Error('请输入完整UTC时间');
  const normalized=time.length===16?`${time}:00`:time,date=new Date(`${normalized}Z`),value=Number(price);
  if(!Number.isFinite(date.getTime())||date.toISOString().slice(0,19)!==normalized||String(price).trim()===''||!Number.isFinite(value)||value<=0)throw new Error('锚点时间或价格无效');
  const point={time:date.getTime()/1000,price:value};if(!validAnchor(point))throw new Error('锚点时间超出范围');return point;
}
export function moveDrawing(drawing,start,end,candles){
  if(!validAnchor(start)||!validAnchor(end)||!candles.length)return null;
  const time=end.time-start.time,price=end.price-start.price;
  const points=drawing.points.map(point=>({time:point.time+time,price:point.price+price}));
  if(points.some(point=>!validAnchor(point)||point.time<candles[0].time||point.time>candles.at(-1).time))return null;
  return validateAnchoredDrawing({...drawing,points});
}
export function replaceDrawing(drawings,input){
 const next=validateAnchoredDrawing(input),existing=drawings.find(item=>item.id===next.id);
 if(!existing||existing.scope!==next.scope)throw new Error('绘图对象已变化，请重新选择');
 if(existing.locked){if(next.locked!==false)throw new Error('该绘图已锁定，请先解锁');return drawings.map(item=>item.id===next.id?{...existing,locked:false}:item);}
 return drawings.map(item=>item.id===next.id?next:item);
}
