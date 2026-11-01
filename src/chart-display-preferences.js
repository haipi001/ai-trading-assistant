const styles={'K线图':'蜡烛图','K线图 (HLC)':'K线图(HLC)','美国线':'美国线','收盘价线':'折线图','平均K线':'平均K线'};
export function chartDisplayPreferences(settings){
 if(!styles[settings.candle])throw new Error('K线样式无效');
 return {chartType:styles[settings.candle],priceLine:Boolean(settings.realtimePrice),countdown:Boolean(settings.countdown),grid:Boolean(settings.grid),revision:Date.now()};
}
export function applyChartDisplayPreferences(studies,preferences){
 if(!preferences)return studies;
 let next=[...studies];
 for(const [key,label] of [['priceLine','价格线'],['countdown','倒计时'],['grid','网格线']])next=preferences[key]?[...new Set([...next,label])]:next.filter(x=>x!==label);
 return next;
}
