import assert from 'node:assert/strict';
import {encodeChartLayout,decodeChartLayout} from '../src/chart-layout-transfer.js';
import {captureChartLayout} from '../src/chart-layout-state.js';
const state=captureChartLayout({marketMode:'web3',symbol:'BTC',venue:'币安',period:'5分',chartType:'蜡烛图',paneCount:2,paneSync:[],studies:['EMA'],paneSymbols:[],panePeriods:[],paneStudies:[]});
assert.deepEqual(decodeChartLayout(encodeChartLayout('测试布局',state)),{name:'测试布局',state});
for(const text of ['{','{}',JSON.stringify({format:'ai-trading-chart-layout',version:2,name:'x',state})])assert.throws(()=>decodeChartLayout(text));
assert.throws(()=>decodeChartLayout(' '.repeat(2*1024*1024+1)));
assert.throws(()=>decodeChartLayout(encodeChartLayout('x',{...state,drawings:[{id:'bad',x:NaN,y:0,type:'趋势线'}]})));
console.log('Layout transfer: complete roundtrip, corrupt/version/oversize/legacy drawing rejection passed');
