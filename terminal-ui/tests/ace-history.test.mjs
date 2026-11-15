import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizeThreads,createThread,appendMessage,removeThread,renameThread,toggleArchived,clearScopeThreads,filterThreads,threadTitle,threadPreview,threadStats,makeMessage,relativeTime,messagePreview,scopeOf,scopeLabel,THREAD_LIMIT,STARTER_QUESTIONS} from '../../src/ace-history.js';

const msg = (question, extra = {}) => makeMessage({question, answer: '回复', ...extra});

test('scope maps markets and never leaks one into the other',()=>{
 assert.equal(scopeOf('stocks'),'stocks');
 assert.equal(scopeOf('web3'),'web3');
 assert.equal(scopeOf(undefined),'web3');
 assert.equal(scopeLabel('stocks'),'股票');
 assert.equal(scopeLabel('web3'),'加密');
 assert.equal(scopeLabel('bogus'),'未知市场');
});

test('an empty question is never turned into a message',()=>{
 assert.equal(msg('   '),null);
 assert.equal(msg(null),null);
});

test('a failed request keeps its reason so the cost stays visible',()=>{
 const row=makeMessage({question:'问',answer:'',status:'failed',reason:'未获得有效回复'});
 assert.equal(row.status,'failed');
 assert.equal(row.reason,'未获得有效回复');
});

test('a new thread starts empty and titled by its market',()=>{
 const threads=createThread([],{scope:'stocks'});
 assert.equal(threads.length,1);
 assert.equal(threads[0].scope,'stocks');
 assert.deepEqual(threads[0].messages,[]);
 assert.equal(threadTitle(threads[0]),'新对话');
 assert.equal(threadPreview(threads[0]),'还没有提问');
});

test('appending a message lifts the thread to the top and reopens it',()=>{
 let threads=createThread([],{scope:'web3'});
 threads=createThread(threads,{scope:'web3'});
 const older=threads[1].id, newer=threads[0].id;
 threads=toggleArchived(threads,older);
 threads=appendMessage(threads,older,msg('旧对话里的问题'));
 assert.equal(threads[0].id,older,'touch lifts the thread to the top');
 assert.equal(threads[0].archived,false,'answering a thread reopens it');
 assert.equal(threads[1].id,newer);
 assert.equal(threads[0].messages.length,1);
});

test('threads are titled after the first question, not the latest',()=>{
 let threads=createThread([],{scope:'web3'});
 const id=threads[0].id;
 threads=appendMessage(threads,id,msg('第一个问题是什么'));
 threads=appendMessage(threads,id,msg('第二个问题'));
 assert.equal(threadTitle(threads[0]),'第一个问题是什么');
});

test('a user rename wins over the first question',()=>{
 let threads=createThread([],{scope:'web3'});
 const id=threads[0].id;
 threads=appendMessage(threads,id,msg('原始问题'));
 threads=renameThread(threads,id,'  自定义名称  ');
 assert.equal(threadTitle(threads[0]),'自定义名称');
});

test('market scope filters stock threads out of the crypto list',()=>{
 let threads=createThread([],{scope:'stocks'});
 threads=createThread(threads,{scope:'web3'});
 threads=appendMessage(threads,threads[0].id,msg('加密问题'));
 threads=appendMessage(threads,threads[1].id,msg('股票问题'));
 assert.equal(filterThreads(threads,{scope:'web3'}).length,1);
 assert.equal(filterThreads(threads,{scope:'stocks'}).length,1);
 assert.equal(filterThreads(threads,{scope:'all'}).length,2);
});

test('archived threads leave the active list but stay addressable',()=>{
 let threads=createThread([],{scope:'web3'});
 const id=threads[0].id;
 threads=appendMessage(threads,id,msg('问题'));
 threads=toggleArchived(threads,id);
 assert.equal(filterThreads(threads,{archived:'active'}).length,0);
 assert.equal(filterThreads(threads,{archived:'archived'}).length,1);
 assert.equal(filterThreads(threads,{archived:'all'}).length,1);
});

test('search covers title, questions and answers',()=>{
 let threads=createThread([],{scope:'web3'});
 const id=threads[0].id;
 threads=appendMessage(threads,id,msg('BTC 突破',{answer:'观察 64200 一带'}));
 assert.equal(filterThreads(threads,{query:'btc'}).length,1);
 assert.equal(filterThreads(threads,{query:'64200'}).length,1);
 assert.equal(filterThreads(threads,{query:'不存在'}).length,0);
});

test('clearing one scope leaves the other market intact',()=>{
 let threads=createThread([],{scope:'stocks'});
 threads=createThread(threads,{scope:'web3'});
 threads=appendMessage(threads,threads[0].id,msg('A'));
 threads=appendMessage(threads,threads[1].id,msg('B'));
 const left=clearScopeThreads(threads,'stocks');
 assert.equal(left.length,1);
 assert.equal(left[0].scope,'web3');
 assert.equal(clearScopeThreads(threads,'all').length,0);
});

test('storage corruption degrades to an empty list instead of crashing',()=>{
 assert.deepEqual(normalizeThreads(null),[]);
 assert.deepEqual(normalizeThreads('nope'),[]);
 assert.deepEqual(normalizeThreads([null,{}]),[]);
 // A freshly created thread has no messages yet and must survive a reload,
 // otherwise "新建对话" would vanish the moment it is stored.
 const empty=normalizeThreads([{id:'t',scope:'web3',messages:[]}]);
 assert.equal(empty.length,1);
 assert.deepEqual(empty[0].messages,[]);
 const rows=normalizeThreads([{id:'t',scope:'weird',messages:[{question:'q'}]}]);
 assert.equal(rows.length,1);
 assert.equal(rows[0].scope,'web3');
});

test('empty or blank messages inside a thread are dropped',()=>{
 const rows=normalizeThreads([{id:'t',scope:'web3',messages:[{question:'ok'},null,{question:'  '}]}]);
 assert.equal(rows[0].messages.length,1);
});

test('thread count stays bounded',()=>{
 let threads=[];
 for(let index=0;index<THREAD_LIMIT+10;index+=1) threads=createThread(threads,{scope:'web3'});
 assert.equal(threads.length,THREAD_LIMIT);
});

test('stats count threads, messages, archives and failures',()=>{
 let threads=createThread([],{scope:'stocks'});
 threads=createThread(threads,{scope:'web3'});
 threads=appendMessage(threads,threads[0].id,msg('ok'));
 threads=appendMessage(threads,threads[0].id,makeMessage({question:'bad',answer:'',status:'failed',reason:'x'}));
 threads=toggleArchived(threads,threads[1].id);
 const stats=threadStats(threads);
 assert.equal(stats.threads,2);
 assert.equal(stats.messages,2);
 assert.equal(stats.failed,1);
 assert.equal(stats.archived,1);
 assert.equal(stats.active,1);
 assert.equal(stats.stocks,1);
 assert.equal(stats.web3,1);
});

test('relative time is human readable and never negative',()=>{
 const now=Date.now();
 assert.equal(relativeTime(new Date(now-10_000).toISOString(),now),'刚刚');
 assert.equal(relativeTime(new Date(now-5*60_000).toISOString(),now),'5 分钟前');
 assert.equal(relativeTime(new Date(now-3*3600_000).toISOString(),now),'3 小时前');
 assert.equal(relativeTime(new Date(now+60_000).toISOString(),now),'刚刚');
 assert.equal(relativeTime('garbage',now),'时间未知');
});

test('message preview falls back to the failure reason',()=>{
 assert.equal(messagePreview({answer:'',status:'failed',reason:'后端连接失败'}),'后端连接失败');
 assert.equal(messagePreview({answer:'',status:'ok'}),'尚无回复内容');
 assert.ok(messagePreview({answer:'长'.repeat(200)}).endsWith('…'));
});

test('removing a thread keeps the rest and drops its messages',()=>{
 let threads=createThread([],{scope:'web3'});
 threads=createThread(threads,{scope:'web3'});
 const target=threads[0].id;
 threads=appendMessage(threads,target,msg('A'));
 threads=appendMessage(threads,threads[1].id,msg('B'));
 const left=removeThread(threads,target);
 assert.equal(left.length,1);
 assert.equal(left[0].messages[0].question,'B');
});

test('each market gets its own starter questions',()=>{
 assert.ok(STARTER_QUESTIONS.stocks.length>0);
 assert.ok(STARTER_QUESTIONS.web3.length>0);
 assert.notDeepEqual(STARTER_QUESTIONS.stocks,STARTER_QUESTIONS.web3);
});
