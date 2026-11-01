import assert from 'node:assert/strict';
import {DEFAULT_CHART_AXIS,chartAxisOptions,validateChartAxis,updatePaneAxis,parsePriceRange,storedPriceRange,applyExactPriceRange} from '../src/chart-axis.js';
import {captureChartLayout,validateChartLayout} from '../src/chart-layout-state.js';
assert.deepEqual(chartAxisOptions(DEFAULT_CHART_AXIS),{mode:0,invertScale:false,autoScale:true});
assert.equal(chartAxisOptions({...DEFAULT_CHART_AXIS,mode:'logarithmic'}).mode,1);
assert.equal(chartAxisOptions({...DEFAULT_CHART_AXIS,mode:'percentage'}).mode,2);
assert.throws(()=>validateChartAxis({...DEFAULT_CHART_AXIS,mode:'unknown'}));
assert.throws(()=>validateChartAxis({...DEFAULT_CHART_AXIS,mode:'percentage',autoScale:false}));
const next={mode:'logarithmic',inverted:true,autoScale:true};
const axes=Array.from({length:18},()=>({...DEFAULT_CHART_AXIS}));
const independent=updatePaneAxis(axes,1,next,false);assert.equal(independent[0].mode,'linear');assert.equal(independent[1].inverted,true);
const synced=updatePaneAxis(axes,1,next,true);assert(synced.every(axis=>axis.mode==='logarithmic'&&axis.inverted));assert.notEqual(synced[0],synced[1]);assert.equal(axes[1].mode,'linear');
const saved=captureChartLayout({marketMode:'web3',symbol:'BTC',venue:'币安',period:'5分',chartType:'蜡烛图',paneCount:2,paneSync:['坐标轴'],studies:[],paneSymbols:[],panePeriods:[],paneStudies:[],paneAxes:independent});
assert.deepEqual(validateChartLayout(JSON.parse(JSON.stringify(saved))),saved);
assert.throws(()=>validateChartLayout({...saved,paneAxes:[]}));
assert.deepEqual(parsePriceRange('3100','3250'),{from:3100,to:3250});
for(const [a,b] of [['','2'],['0','2'],['3','2'],['1','Infinity']])assert.throws(()=>parsePriceRange(a,b));
const view={key:'ETH:币安:4时:full',priceMode:'logarithmic',priceRange:{from:3100,to:3250}};
assert.deepEqual(storedPriceRange(view,view.key,{mode:'logarithmic',autoScale:false}),view.priceRange);
assert.equal(storedPriceRange(view,'SOL:币安:4时:full',{mode:'logarithmic',autoScale:false}),null);
assert.equal(storedPriceRange(view,view.key,{mode:'logarithmic',autoScale:true}),null);
assert.equal(storedPriceRange(view,view.key,{mode:'linear',autoScale:false}),null);
// Reproduce the public5.2 raw-set/log-get mismatch, including small-price offset.
for(const offset of [4,7]){
 let range=null;const scale={options:()=>({mode:1}),applyOptions:()=>{},setVisibleRange:value=>{range=value;},getVisibleRange:()=>({from:10**(range.from-offset)-10**-offset,to:10**(range.to-offset)-10**-offset})};
 const expected=offset===4?{from:3100,to:3250}:{from:.1,to:.2};
 applyExactPriceRange(scale,expected);const actual=scale.getVisibleRange();assert(Math.abs(actual.from-expected.from)<1e-8);assert(Math.abs(actual.to-expected.to)<1e-8);
}
let nativeRange=null;const correctedScale={options:()=>({mode:1}),setVisibleRange:value=>{nativeRange=value;},getVisibleRange:()=>nativeRange};applyExactPriceRange(correctedScale,{from:140,to:155});assert.deepEqual(nativeRange,{from:140,to:155});
console.log('Axis checks: library mode mapping, independent/synced updates, percentage guard and immutable layout roundtrip passed');
