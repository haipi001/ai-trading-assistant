export function candleAgeLabel(candle,now=Date.now()) {
 const timestamp=Number(candle?.time)*1000;
 if(!Number.isFinite(timestamp)||timestamp<=0||!Number.isFinite(now))return '';
 const date=new Date(timestamp);if(!Number.isFinite(date.getTime()))return '';
 const days=Math.floor((now-timestamp)/86400000);
 return `末根开始 ${date.toISOString().replace('T',' ').slice(0,19)} UTC${days>=1?` · 距今${days}天`:''} · 快照不保证实时`;
}
