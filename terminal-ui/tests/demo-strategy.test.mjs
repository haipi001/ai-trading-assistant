import test from 'node:test';
import assert from 'node:assert/strict';
import {STRATEGY_TEMPLATES,validateStrategy,demoCandles,replayStrategy,readDemoStrategies,saveDemoStrategy} from '../../src/demo-strategy-model.js';
import {demoPageData} from '../../src/demo-page-data.js';

test('strategy rules reject malformed input instead of silently selecting a branch',()=>{
 for(const patch of [{kind:'unknown'},{allocation:101},{allocation:0},{lookback:2.5},{stopLoss:100},{feeBps:-1},{threshold:''},{name:''},{lookback:Infinity}])assert.throws(()=>validateStrategy({...STRATEGY_TEMPLATES[0],...patch}));
 assert.throws(()=>validateStrategy({...STRATEGY_TEMPLATES[2],direction:'invalid'}));
});
test('known price path accounts for next-close execution, fees, and final valuation',()=>{
 const rule={...STRATEGY_TEMPLATES[2],lookback:2,allocation:100,threshold:100,stopLoss:90,takeProfit:999,feeBps:100};
 const prices=[90,95,110,120,130,90,80];const candles=prices.map((close,i)=>({time:`2026-01-0${i+1}`,close}));
 const result=replayStrategy(rule,candles,{capital:1000});
 assert.equal(result.trades[0].time,'2026-01-04');assert.equal(result.trades[0].price,120);
 assert.equal(result.trades[1].time,'2026-01-07');assert.equal(result.trades[1].price,80);
 assert.ok(Math.abs(result.equity-(1000/1.01/120*80*.99))<1e-8);
 assert.equal(result.openQuantity,0);assert.equal(result.execution,'READ_ONLY');assert.ok(result.fees>0);
});
test('future bars never change earlier fills and equity',()=>{
 const bars=demoCandles();const full=replayStrategy(STRATEGY_TEMPLATES[0],bars),prefix=replayStrategy(STRATEGY_TEMPLATES[0],bars.slice(0,40));
 assert.deepEqual(full.curve.slice(0,40),prefix.curve);assert.deepEqual(full.trades.filter(item=>item.time<=bars[39].time),prefix.trades);
});
test('all templates run deterministically across three markets and scenarios',()=>{
 for(const market of ['stocks','cex','onchain'])for(const scenario of ['trend','range','fall'])for(const rule of STRATEGY_TEMPLATES){const bars=demoCandles(market,scenario),a=replayStrategy(rule,bars),b=replayStrategy(rule,bars);assert.deepEqual(a,b);assert.ok(a.equity>=0);assert.ok(a.maxDrawdown>=0&&a.maxDrawdown<=100);assert.equal(a.curve.length,72);}
});
test('invalid or unsorted candles fail closed',()=>{
 const bars=demoCandles();assert.throws(()=>replayStrategy(STRATEGY_TEMPLATES[0],[...bars].reverse()));assert.throws(()=>replayStrategy(STRATEGY_TEMPLATES[0],bars.map((b,i)=>i===8?{...b,close:NaN}:b)));assert.throws(()=>replayStrategy(STRATEGY_TEMPLATES[0],bars,{capital:0}));
});
test('strategy save updates by identity, supports copy, and rejects storage corruption',()=>{
 const map=new Map(),storage={getItem:key=>map.get(key),setItem:(key,value)=>map.set(key,value)};
 let rows=saveDemoStrategy(storage,[],STRATEGY_TEMPLATES[0]);rows=saveDemoStrategy(storage,rows,{...rows[0],name:'Updated'});assert.equal(rows.length,1);assert.equal(readDemoStrategies(storage)[0].name,'Updated');
 rows=saveDemoStrategy(storage,rows,{...rows[0],id:undefined,name:'Copy'});assert.equal(rows.length,2);
 assert.deepEqual(readDemoStrategies({getItem:()=>'{bad'}),[]);
 assert.throws(()=>saveDemoStrategy({setItem:()=>{throw Error('quota');}},[],STRATEGY_TEMPLATES[0]));
});
test('all registered business entries have renderable page-specific demo data',async()=>{
 globalThis.window={};await import('../integration/registry.js');const entries=window.TERMINAL_FEATURES;assert.equal(entries.length,68);
 for(const target of entries){const data=demoPageData(target,{market:'cex',instrumentId:'BTC/USDT'});assert.equal(data.source,'demo');assert.equal(data.rows.length,3);assert.equal(data.columns.length,4);assert.equal(data.candles.length,72);assert.ok(data.action);}
 delete globalThis.window;
});

test('demo audit is bounded, isolated and cannot create an execution action',async()=>{
 const {appendDemoAudit,DEMO_AUDIT_KEY}=await import('../../src/demo-strategy-model.js');const map=new Map(),storage={getItem:key=>map.get(key),setItem:(key,value)=>map.set(key,value)};
 for(let i=0;i<105;i++)assert.equal(appendDemoAudit(storage,'strategy_replayed',{index:i}),true);
 const rows=JSON.parse(map.get(DEMO_AUDIT_KEY));assert.equal(rows.length,100);assert.equal(rows[0].detail.index,104);assert.equal(rows[0].execution,'READ_ONLY');assert.throws(()=>appendDemoAudit(storage,'execute_order',{}));assert.equal(appendDemoAudit({getItem:()=>null,setItem:()=>{throw Error('quota');}},'strategy_saved',{}),false);
});
