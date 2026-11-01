import {validateMarketBars,periodDefinition} from './market-chart-model.js';
import {replayCloseTime} from './chart-replay.js';
export function marketResearchCapture({symbol,venue,period,marketMode='web3',feed,replay=null,now=Date.now()}){
 try{
  if(!replay&&(!feed||!['connected','local'].includes(feed.status)||!feed.candles?.length))return null;
  if(/demo|mock|seed|演示|模拟/i.test(replay?.source||feed?.source||'')||replay?.demo)return null;
  const kind=replay?'replay':feed.status==='local'?'csv':'online';
  const cutoff=replay?.cutoff??null;
  let bars=replay?replay.bars.filter(bar=>replayCloseTime(bar,period)<=cutoff):feed.candles;
  bars=validateMarketBars(bars).slice(-240).map(({time,open,high,low,close,volume})=>({time,open,high,low,close,volume}));
  if(!bars.length||bars.some(bar=>[bar.open,bar.high,bar.low,bar.close].some(value=>value<=0)))return null;
  const definition=periodDefinition(period);
  return {schema:1,origin:'browser_chart',data_semantics:'raw_ohlcv',kind,market_type:marketMode==='stocks'?'stock':'spot',symbol,venue,quote_currency:marketMode==='stocks'?'USD':'USDT',timeframe:definition.timeframe,source_label:kind==='csv'?'本地CSV（用户导入）':(replay&&/csv/i.test(replay.source||'')?'历史复盘（本地CSV原始K线）':String(replay?.source||feed.source||'后端图表快照').slice(0,300)),observed_at:replay?.observedAt||(replay?null:feed?.observedAt||feed?.fetchedAt)||null,captured_at:new Date(now).toISOString(),volume_available:replay?.volumeAvailable??feed?.volumeAvailable??true,replay_cutoff:kind==='replay'?cutoff:null,bars};
 }catch{return null;}
}
export function selectMarketCapture(capture,count=60){if(!capture||![30,60,120,240].includes(count))return null;return {...capture,bars:capture.bars.slice(-count).map(bar=>({...bar}))};}
