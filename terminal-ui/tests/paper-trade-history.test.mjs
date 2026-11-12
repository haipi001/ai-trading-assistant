import test from 'node:test';
import assert from 'node:assert/strict';
import {paperTradeHistory,paperTradeCsv} from '../../src/paper-trade-history.js';
test('Paper history requires the original account and preserves decimal strings and safe CSV cells',()=>{
 const row={execution_id:'fill',order_draft_id:'draft',asset_id:'asset',symbol:'=UNTRUSTED()',venue:'mock',asset_currency:'USD',side:'buy',status:'filled',execution_mode:'paper',quantity:'0.0000000001',price:'123.4567891234',fee:'0.01',realized_pnl:'-1.2',recorded_at:new Date().toISOString()};
 const packet={source:'owned_application_paper_ledger',account_id:'a',market:'stocks',captured_at:row.recorded_at,execution_available:false,has_more:false,entries:[row]};
 assert.equal(paperTradeHistory(packet,{accountId:'a',market:'stocks'}),packet);
 assert.throws(()=>paperTradeHistory(packet,{accountId:'foreign',market:'stocks'}));
 assert.throws(()=>paperTradeHistory({...packet,entries:[{...row,execution_mode:'live'}]},{accountId:'a',market:'stocks'}));
 const csv=paperTradeCsv(packet);assert.match(csv,/0.0000000001/);assert.match(csv,/'=UNTRUSTED/);assert.match(csv,/paper/);assert.equal(row.symbol,'=UNTRUSTED()');
});

test('historical review requires the same execution/draft/account/asset/journal chain',async()=>{
 const {paperHistoryReview}=await import('../../src/paper-trade-history.js');
 const row={execution_id:'fill',order_draft_id:'draft',asset_id:'asset'};
 const context={execution_available:false,execution:{id:'fill',execution_mode:'paper',order_draft_id:'draft'},journal_entry:{id:'journal',account_id:'a',asset_id:'asset',title:'Paper',notes:'recorded'},post_trade_review:{id:'review',execution_id:'fill',order_draft_id:'draft',trade_journal_entry_id:'journal',status:'pending',updated_at:new Date().toISOString()}};
 assert.equal(paperHistoryReview(context,row,{accountId:'a'}),context);
 assert.throws(()=>paperHistoryReview(context,row,{accountId:'other'}));
 for(const patch of [{execution_id:'other'},{order_draft_id:'other'},{asset_id:'other'}])assert.throws(()=>paperHistoryReview(context,{...row,...patch},{accountId:'a'}));
 assert.throws(()=>paperHistoryReview({...context,execution:{...context.execution,execution_mode:'live'}},row,{accountId:'a'}));
});

test('Paper pages append without losing exact values and reject repeated rows',async()=>{
 const {appendPaperHistory}=await import('../../src/paper-trade-history.js');
 const context={accountId:'a',market:'stocks'},time=new Date().toISOString();
 const row=id=>({execution_id:id,order_draft_id:'draft',asset_id:'asset',symbol:'AAPL',venue:'mock',asset_currency:'USD',side:'buy',status:'filled',execution_mode:'paper',quantity:'0.0000000001',price:'1',fee:'0',realized_pnl:'0',recorded_at:time});
 const first={source:'owned_application_paper_ledger',account_id:'a',market:'stocks',captured_at:time,execution_available:false,has_more:true,next_cursor:'99',entries:Array.from({length:100},(_,i)=>row(String(i)))};
 const last={...first,has_more:false,next_cursor:null,entries:[row('100')]};
 const combined=appendPaperHistory(first,last,context);
 assert.equal(combined.entries.length,101);assert.equal(first.entries.length,100);assert.equal(combined.entries[100].quantity,'0.0000000001');
 assert.equal(paperTradeCsv(combined).split('\r\n').length,102);
 assert.throws(()=>appendPaperHistory(first,{...last,entries:[row('99')]},context));
 assert.throws(()=>appendPaperHistory(first,last,{...context,accountId:'foreign'}));
 assert.throws(()=>paperTradeHistory({...first,next_cursor:'98'},context));
});
