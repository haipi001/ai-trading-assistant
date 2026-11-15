import {test} from 'node:test';
import assert from 'node:assert/strict';
import {noteTags,parseWikiLinks,buildLinkIndex,noteConnections,linkSuggestions,tradeMetrics,journalStats,openPositions,journalGaps,noteAnalysisPrompt,strategyDraftFromNote,newNote,newTrade,noteKind,normalizeTitle} from '../../src/trade-journal.js';

const note = (id,title,body,extra={}) => ({id,title,body,kind:'note',tags:[],links:[],...extra});
const trade = (id,extra={}) => ({id,title:'t',body:'理由',kind:'trade',symbol:'BTC',side:'买入',status:'已平仓',entryPrice:100,quantity:1,exitPrice:110,stopLoss:95,...extra});

test('tags merge declared and inline hashtags without duplicates',()=>{
 assert.deepEqual(noteTags({tags:['BTC','风控'],body:'看 #btc 和 #突破 #风控'}).map(t=>t.toLowerCase()).sort(),['btc','突破','风控']);
 assert.deepEqual(noteTags({body:'无标签'}),[]);
});

test('wiki links parse, dedupe and ignore blanks',()=>{
 assert.deepEqual(parseWikiLinks('见 [[风险清单]] 与 [[风险清单]] 还有 [[ 突破 观察 ]]'),['风险清单','突破 观察']);
 assert.deepEqual(parseWikiLinks('没有链接'),[]);
 assert.deepEqual(parseWikiLinks(null),[]);
});

test('link index builds forward links, backlinks and reports broken targets',()=>{
 const notes=[note('a','突破观察','关联 [[风险清单]] 和 [[不存在]]'),note('b','风险清单','回应 [[突破观察]]')];
 const index=buildLinkIndex(notes);
 assert.deepEqual([...index.outgoing.get('a')],['b']);
 assert.deepEqual([...index.backlinks.get('b')],['a']);
 assert.deepEqual([...index.backlinks.get('a')],['b']);
 assert.equal(index.broken.length,1);
 assert.equal(index.broken[0].title,'不存在');
 assert.equal(index.edgeCount,2);
 assert.deepEqual([...index.orphans],[]);
});

test('link index is case and space insensitive on titles',()=>{
 const index=buildLinkIndex([note('a','A','[[  risk   LIST ]]'),note('b','Risk List','')]);
 assert.deepEqual([...index.outgoing.get('a')],['b']);
 assert.equal(normalizeTitle('  Risk   List '),'risk list');
});

test('self links never create an edge',()=>{
 const index=buildLinkIndex([note('a','自指','[[自指]]')]);
 assert.equal(index.edgeCount,0);
 assert.deepEqual([...index.orphans],['a']);
});

test('connections separate outgoing, incoming and tag-only relations',()=>{
 const notes=[note('a','A','[[B]]',{tags:['x']}),note('b','B','',{tags:['x']}),note('c','C','',{tags:['x']})];
 const index=buildLinkIndex(notes);
 const rel=noteConnections(index,'a');
 assert.deepEqual(rel.outgoing.map(r=>r.id),['b']);
 assert.deepEqual(rel.incoming,[]);
 assert.deepEqual(rel.related.map(r=>r.id),['c']);
});

test('tag index groups notes and never duplicates a tag per note',()=>{
 const index=buildLinkIndex([note('a','A','#btc #BTC'),note('b','B','#btc')]);
 assert.equal(index.tagIndex.size,1);
 assert.deepEqual([...index.tagIndex.get('btc').ids].sort(),['a','b']);
});

test('link suggestions exclude self and already linked notes',()=>{
 const index=buildLinkIndex([note('a','A','[[B]]'),note('b','B',''),note('c','C','')]);
 assert.deepEqual(linkSuggestions(index,'a','b'),[]);
 assert.deepEqual(linkSuggestions(index,'a','c').map(r=>r.id),['c']);
 assert.deepEqual(linkSuggestions(index,'a',''),[]);
});

test('trade metrics compute cost, risk, reward and R multiple',()=>{
 const m=tradeMetrics(trade('t',{takeProfit:120,fees:2}));
 assert.equal(m.cost,100);
 assert.equal(m.risk,5);
 assert.equal(m.reward,20);
 assert.equal(m.riskReward,4);
 assert.equal(m.realized,8);
 assert.equal(m.realizedPct,8);
 assert.equal(m.rMultiple,1.6);
});

test('a short trade inverts the pnl direction',()=>{
 const m=tradeMetrics(trade('t',{side:'卖出',exitPrice:90,fees:0}));
 assert.equal(m.realized,10);
});

test('unclosed or exit-less trades never fabricate realized pnl',()=>{
 assert.equal(tradeMetrics(trade('t',{status:'持有中'})).realized,null);
 assert.equal(tradeMetrics(trade('t',{exitPrice:''})).realized,null);
 assert.equal(tradeMetrics(trade('t',{entryPrice:''})).realized,null);
 assert.equal(tradeMetrics(trade('t',{quantity:0})).valid,false);
});

test('a stop above entry yields no risk figure instead of a negative one',()=>{
 assert.equal(tradeMetrics(trade('t',{stopLoss:150})).risk,null);
});

test('journal stats split open and closed and ignore unknown exits',()=>{
 const entries=[
  trade('a',{exitPrice:110,fees:0}),
  trade('b',{exitPrice:90,fees:0}),
  trade('c',{status:'持有中'}),
  trade('d',{exitPrice:'',fees:0}),
  note('n','心得','一些想法'),
 ];
 const s=journalStats(entries);
 assert.equal(s.trades,4);
 assert.equal(s.notes,1);
 assert.equal(s.open,1);
 assert.equal(s.closed,3);
 assert.equal(s.decided,2);
 assert.equal(s.wins,1);
 assert.equal(s.losses,1);
 assert.equal(s.unknown,1);
 assert.equal(s.winRate,50);
 assert.equal(s.realized,0);
 assert.equal(s.profitFactor,1);
});

test('profit factor is null when there is no loss to divide by',()=>{
 const s=journalStats([trade('a',{exitPrice:120,fees:0})]);
 assert.equal(s.profitFactor,null);
 assert.equal(s.winRate,100);
});

test('stats group realized pnl by symbol',()=>{
 const s=journalStats([trade('a',{exitPrice:110}),trade('b',{symbol:'ETH',exitPrice:90})]);
 assert.equal(s.bySymbol.length,2);
 assert.equal(s.bySymbol[0].symbol,'BTC');
});

test('open positions average entry by quantity and flag mixed sides',()=>{
 const rows=openPositions([
  trade('a',{status:'持有中',entryPrice:100,quantity:1}),
  trade('b',{status:'持有中',entryPrice:200,quantity:3}),
  trade('c',{status:'持有中',side:'卖出',entryPrice:100,quantity:1}),
 ]);
 assert.equal(rows.length,1);
 assert.equal(rows[0].quantity,5);
 assert.equal(rows[0].averageEntry,160);
 assert.equal(rows[0].mixedSides,true);
});

test('gaps surface missing stop, missing reason and thin samples',()=>{
 const gaps=journalGaps([trade('a',{stopLoss:'',body:''})]);
 assert.ok(gaps.some(g=>/没有填写止损价/.test(g)));
 assert.ok(gaps.some(g=>/没有写下进场理由/.test(g)));
 assert.ok(gaps.some(g=>/样本/.test(g)));
 assert.ok(journalGaps([]).some(g=>/还没有任何交易记录/.test(g)));
});

test('prompt carries facts, missing pnl and the no-advice constraint',()=>{
 const notes=[note('a','突破','[[风险]]'),note('b','风险','')];
 const text=noteAnalysisPrompt(notes[0],buildLinkIndex(notes));
 assert.match(text,/待核对资料/);
 assert.match(text,/本笔记链接到：风险/);
 assert.match(text,/不给出确定性买卖建议/);
 const tradeText=noteAnalysisPrompt(trade('t',{status:'持有中'}),buildLinkIndex([]));
 assert.match(tradeText,/已实现盈亏未计算/);
});

test('strategy draft from a note stays a draft and carries no execution fields',()=>{
 const draft=strategyDraftFromNote(trade('t',{stopLoss:95,tags:['BTC']}),{instrumentId:'BTC/USDT'});
 assert.equal(draft.status,'草稿');
 assert.equal(draft.coin,'BTC');
 assert.match(draft.invalidation,/95/);
 assert.match(draft.constraints,/未经独立核验/);
 assert.equal(draft.amount,'');
});

test('new note and trade templates start empty rather than with fake data',()=>{
 assert.equal(newNote('1').body.includes('[['),true);
 assert.equal(newTrade('2').entryPrice,'');
 assert.equal(noteKind({kind:'trade'}),'trade');
 assert.equal(noteKind({}),'note');
});
