import {test} from 'node:test';
import assert from 'node:assert/strict';
import {positionSize,drawdownTable,recoveryNeeded,RISK_PRESETS} from '../../src/risk-calculator.js';
import {newQuickNote,filterQuickNotes,quickNoteTitle,quickNotePreview,quickNoteTags,quickNotePrompt,noteSymbolLabel} from '../../src/quick-notes.js';

test('position size derives quantity from risk budget, not from notional',()=>{
 const v=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'95'});
 assert.equal(v.ready,true);
 assert.equal(v.riskAmount,100);
 assert.equal(v.quantity,20);
 assert.equal(v.notional,2000);
 assert.equal(v.leverage,0.2);
});

test('a short position inverts the stop direction',()=>{
 const v=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'105',side:'卖出'});
 assert.equal(v.ready,true);
 assert.equal(v.quantity,20);
});

test('a stop on the wrong side of entry refuses instead of returning a negative size',()=>{
 const long=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'105'});
 assert.equal(long.ready,false);
 assert.match(long.gaps[0],/买入时止损价必须低于进场价/);
 const short=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'95',side:'卖出'});
 assert.equal(short.ready,false);
 assert.match(short.gaps[0],/卖出时止损价必须高于进场价/);
});

test('a zero-distance stop is rejected rather than dividing by zero',()=>{
 const v=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'100'});
 assert.equal(v.ready,false);
 assert.match(v.gaps[0],/止损价不能等于进场价/);
});

test('missing inputs are listed as gaps and never defaulted',()=>{
 const v=positionSize({account:'',riskPercent:'',entry:'',stop:''});
 assert.equal(v.ready,false);
 assert.equal(v.gaps.length,4);
 assert.equal(positionSize({account:'abc',riskPercent:'1',entry:'1',stop:'0.9'}).ready,false);
});

test('take profit adds reward and risk-reward ratio only when favourable',()=>{
 const v=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'95',takeProfit:'120'});
 assert.ok(v.metrics.some(m=>m.label==='潜在盈利'&&m.value==='400.00'));
 assert.ok(v.metrics.some(m=>m.label==='盈亏比'&&m.value==='4.00 : 1'));
 const bad=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'95',takeProfit:'90'});
 assert.equal(bad.ready,true);
 assert.ok(bad.warnings.some(w=>/止盈价应高于进场价/.test(w)));
});

test('leverage and tight stops raise warnings',()=>{
 const v=positionSize({account:'1000',riskPercent:'5',entry:'100',stop:'99'});
 assert.ok(v.warnings.some(w=>/杠杆|倍/.test(w)));
 const tight=positionSize({account:'10000',riskPercent:'1',entry:'100',stop:'99.9'});
 assert.ok(tight.warnings.some(w=>/止损距离只有/.test(w)));
});

test('drawdown table compounds and grows faster than linear',()=>{
 const rows=drawdownTable({account:'10000',riskPercent:'5',losses:20});
 assert.ok(rows.length>0);
 const last=rows[rows.length-1];
 assert.equal(last.round,20);
 assert.ok(Number(last.drawdown)>100-100*Math.pow(0.95,20)-0.01);
 assert.deepEqual(drawdownTable({account:'',riskPercent:'5'}),[]);
});

test('recovery percent is mathematically correct and rejects impossible values',()=>{
 assert.equal(recoveryNeeded(20),'25.00');
 assert.equal(recoveryNeeded(50),'100.00');
 assert.equal(recoveryNeeded(0),null);
 assert.equal(recoveryNeeded(100),null);
 assert.equal(recoveryNeeded('x'),null);
});

test('risk presets stay plain numbers',()=>{
 assert.ok(RISK_PRESETS.every(v=>typeof v==='number'));
});

test('a new quick note starts empty so nothing looks pre-filled',()=>{
 const note=newQuickNote('1');
 assert.equal(note.title,'');
 assert.equal(note.body,'');
 assert.equal(quickNoteTitle(note),'未命名笔记');
 assert.equal(quickNotePreview(note),'还没有内容');
});

test('title falls back to the first non-empty body line',()=>{
 assert.equal(quickNoteTitle({title:'',body:'\n\n  观察突破  \n第二行'}),'观察突破');
 assert.equal(quickNoteTitle({title:' 明确标题 ',body:'x'}),'明确标题');
});

test('search covers title, body, symbol and inline tags',()=>{
 const notes=[
  {id:'a',title:'突破',body:'看多 #BTC',symbol:'ETH',updated:'2026-01-01T00:00:00Z'},
  {id:'b',title:'风控',body:'止损纪律',symbol:'',updated:'2026-01-02T00:00:00Z'},
 ];
 assert.equal(filterQuickNotes(notes,'').length,2);
 assert.equal(filterQuickNotes(notes,'btc').length,1);
 assert.equal(filterQuickNotes(notes,'止损').length,1);
 assert.equal(filterQuickNotes(notes,'eth').length,1);
 assert.equal(filterQuickNotes(notes,'不存在').length,0);
});

test('notes sort newest first and drop non objects',()=>{
 const rows=filterQuickNotes([null,{id:'old',updated:'2020-01-01T00:00:00Z',body:'a'},{id:'new',updated:'2026-01-01T00:00:00Z',body:'b'}],'');
 assert.deepEqual(rows.map(r=>r.id),['new','old']);
 assert.deepEqual(filterQuickNotes(null,''),[]);
});

test('symbol label never renders a dangling separator',()=>{
 assert.equal(noteSymbolLabel({symbol:''}),'未关联标的');
 assert.equal(noteSymbolLabel({symbol:'  '}),'未关联标的');
 assert.equal(noteSymbolLabel({symbol:'BTC'}),'BTC');
 assert.equal(noteSymbolLabel(null),'未关联标的');
});

test('prompt carries the standing no-advice constraints',()=>{
 const text=quickNotePrompt({id:'a',title:'T',body:'看多 #BTC',symbol:'BTC'},{instrumentId:'BTC/USDT'});
 assert.match(text,/待核对资料/);
 assert.match(text,/不给出确定性买卖建议/);
 assert.match(text,/不声称已完成验证/);
 assert.match(text,/当前工作区标的：BTC\/USDT/);
 assert.ok(text.length<4000);
});

test('inline tags dedupe and ignore plain words',()=>{
 assert.deepEqual(quickNoteTags({body:'#BTC #btc #风控 无标签'}),['BTC','btc','风控']);
 assert.deepEqual(quickNoteTags({body:'没有标签'}),[]);
});
