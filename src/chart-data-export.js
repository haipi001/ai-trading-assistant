import {validateMarketBars} from './market-chart-model.js';
const csvCell=value=>{let text=String(value??'');if(/^[\s]*[=+@-]/.test(text))text="'"+text;return /[",\r\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text;};
export function chartDataCsv({candles,volumeAvailable=true,symbol,venue,period,source,kind,replay=false}){
 if(!candles.length)throw new Error('当前没有可导出的K线');
 const bars=validateMarketBars(candles);
 const header=['time','open','high','low','close',...(volumeAvailable?['volume']:[]),'symbol','venue','period','source','data_kind','replay'];
 return '\uFEFF'+[header,...bars.map(bar=>[new Date(bar.time*1000).toISOString(),bar.open,bar.high,bar.low,bar.close,...(volumeAvailable?[bar.volume]:[]),symbol,venue,period,source,kind,replay?'true':'false'])].map(row=>row.map(csvCell).join(',')).join('\r\n');
}
export function downloadChartData(options){
 const body=chartDataCsv(options),url=URL.createObjectURL(new Blob([body],{type:'text/csv;charset=utf-8'}));
 const anchor=document.createElement('a');anchor.href=url;anchor.download=`${options.symbol}-${options.period}${options.replay?'-replay':''}-ohlc.csv`.replaceAll(/[\\/:*?"<>|]/g,'_');
 try{anchor.click();}finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
