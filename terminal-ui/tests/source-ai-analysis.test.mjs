import {test} from 'node:test';
import assert from 'node:assert/strict';
import {analyzeSource,analyzeDepth,analyzeTrades,analyzeCandles,analyzeProfile,analyzeEtf,analyzeNews,analysisQuestion,emptyAnalysis} from '../../src/source-ai-analysis.js';

const bars = count => Array.from({length:count},(_,index)=>{const price=100+index;return {time:index,open:price,high:price+1,low:price-1,close:price+0.5,volume:100+index*4};});

test('depth reports spread, imbalance and does not invent missing levels',()=>{
 const value=analyzeDepth({asks:[{price:101,quantity:5}],bids:[{price:99,quantity:15}]});
 assert.equal(value.ready,true);
 assert.equal(value.metrics.find(row=>row.label==='中间价').value,'100');
 assert.match(value.summary,/买卖挂单比 3/);
 assert.match(value.findings.join(' '),/买方挂单占优/);
 assert.ok(value.gaps.some(row=>/只读取到 1 档/.test(row)));
 assert.ok(value.risks.some(row=>/买盘挂单量只有/.test(row))===false,'买盘多时不报卖盘薄');
});

test('depth refuses empty or crossed-side input instead of filling zeros',()=>{
 assert.equal(analyzeDepth({asks:[],bids:[]}).ready,false);
 assert.equal(analyzeDepth(null).ready,false);
 assert.equal(analyzeDepth({asks:[{price:0,quantity:1}],bids:[{price:99,quantity:1}]}).ready,false);
});

test('trade flow separates buy and sell and flags small samples',()=>{
 const value=analyzeTrades({recent_public_trades:[
  {price:10,quantity:2,side:'买入',time:1000},
  {price:10,quantity:1,side:'卖出',time:900},
 ]});
 assert.equal(value.ready,true);
 const net=value.metrics.find(row=>row.label==='净流入').value;
 assert.equal(net,'+10.00');
 assert.ok(value.risks.some(row=>/样本过小/.test(row)));
 assert.ok(value.gaps.some(row=>/不是交易所资金流入流出/.test(row)));
});

test('candles compute change, moving averages and RSI from provided bars',()=>{
 const value=analyzeCandles({candles:bars(25)});
 assert.equal(value.ready,true);
 assert.equal(value.metrics.find(row=>row.label==='样本根数').value,'25');
 assert.equal(value.metrics.find(row=>row.label==='MA5').value,'122.5');
 assert.match(value.summary,/均线多头排列/);
 assert.ok(value.gaps.some(row=>/不构成对未来价格的预测/.test(row)));
});

test('candles need at least two bars and reject non numeric closes',()=>{
 assert.equal(analyzeCandles({candles:[{open:1,high:1,low:1,close:1,volume:1}]}).ready,false);
 assert.equal(analyzeCandles({candles:[{close:'x'},{close:'y'}]}).ready,false);
});

test('profile combines VWAP and volume concentration without trades',()=>{
 const value=analyzeProfile({candles:bars(20)});
 assert.equal(value.ready,true);
 assert.ok(value.metrics.some(row=>row.label==='样本 VWAP'));
 assert.ok(value.metrics.some(row=>row.label==='成交密集区'));
 assert.ok(value.gaps.some(row=>/没有成交样本/.test(row)));
});

test('etf has no source so it reports gaps and stays not ready',()=>{
 const value=analyzeEtf();
 assert.equal(value.ready,false);
 assert.equal(value.metrics.length,0);
 assert.ok(value.gaps.length>=3);
 assert.match(value.summary,/没有已接入的来源/);
});

test('news counts publishers and never claims sentiment',()=>{
 const value=analyzeNews({articles:[
  {title:'a',publisher:'X',publishedAt:new Date().toISOString()},
  {title:'b',publisher:'Y',publishedAt:new Date(Date.now()-3600000).toISOString()},
 ]});
 assert.equal(value.ready,true);
 assert.equal(value.metrics.find(row=>row.label==='发布方').value,'2');
 assert.ok(value.gaps.some(row=>/没有做情绪或主题分类/.test(row)));
});

test('unknown source and missing material degrade to a gap, never to sample data',()=>{
 const value=analyzeSource('unknown',{});
 assert.equal(value.ready,false);
 assert.equal(analyzeSource('depth',null).ready,false);
 assert.equal(emptyAnalysis('').ready,false);
});

test('question built from analysis carries facts, gaps and the no-trade constraint',()=>{
 const analysis=analyzeDepth({asks:[{price:101,quantity:5}],bids:[{price:99,quantity:5}]});
 const text=analysisQuestion(analysis,'订单与成交',{source:'test feed'});
 assert.match(text,/不是模型证据/);
 assert.match(text,/资料缺口/);
 assert.match(text,/不得给出确定性买卖建议/);
 assert.match(text,/来源标识：test feed/);
 assert.ok(text.length<4000,'prepared question must stay within the input limit');
});
