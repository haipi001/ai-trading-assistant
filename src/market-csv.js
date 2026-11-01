import {parseCandleCsv} from './chart-analysis.js';
import {validateMarketBars} from './market-chart-model.js';
export function parseMarketCsv(text){
 const rows=parseCandleCsv(text);
 if(rows.some(row=>!['open','high','low','close'].every(field=>typeof row[field]==='number'&&row[field]>0)))throw new Error('主图CSV必须包含正数open/high/low/close列');
 return {candles:validateMarketBars(rows),volumeAvailable:rows.every(row=>Object.hasOwn(row,'volume'))};
}
