import React,{useEffect,useMemo,useState} from 'react';
import {STRATEGY_TEMPLATES,readDemoStrategies,saveDemoStrategy,DEMO_STRATEGY_KEY,replayStrategy,appendDemoAudit} from './demo-strategy-model.js';
import {demoPageData} from './demo-page-data.js';
import './demo-workspace.css';
const number=value=>Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2});
function LineChart({values,label}){
 const min=Math.min(...values),max=Math.max(...values),span=max-min||1;
 const points=values.map((v,i)=>`${10+i/(values.length-1)*580},${140-(v-min)/span*125}`).join(' ');
 return <svg className="demo-chart" viewBox="0 0 600 160" role="img" aria-label={label}><title>{label}</title><path d="M10 145H590" stroke="currentColor" opacity=".2"/><polyline points={points} fill="none" stroke="var(--ui-accent)" strokeWidth="2"/><text x="10" y="158">{number(min)}</text><text x="590" y="12" textAnchor="end">{number(max)}</text></svg>;
}
function StrategyWorkbench({data}){
 const [rule,setRule]=useState({...STRATEGY_TEMPLATES[0],id:undefined});
 const [saved,setSaved]=useState(()=>readDemoStrategies(localStorage));
 useEffect(()=>{const sync=event=>{if(event.type==='focus'||event.key===DEMO_STRATEGY_KEY)setSaved(readDemoStrategies(localStorage));};window.addEventListener('storage',sync);window.addEventListener('focus',sync);return()=>{window.removeEventListener('storage',sync);window.removeEventListener('focus',sync);};},[]);
 const [resultSlot,setResultSlot]=useState(null),[message,setMessage]=useState(''),[capital,setCapital]=useState(10000);
 const result=resultSlot?.candles===data.candles?resultSlot.result:null;
 const setResult=value=>setResultSlot(value?{candles:data.candles,result:value}:null);
 const update=(key,value)=>{setRule(old=>({...old,[key]:value}));setResult(null);setMessage('参数已更改，请重新回放。');};
 const run=()=>{try{const output=replayStrategy(rule,data.candles,{capital:Number(capital)});setResult(output);appendDemoAudit(localStorage,'strategy_replayed',{rule:output.rule,scenario:data.scenario,market:data.market,symbol:data.symbol,trades:output.trades.length,equity:output.equity});setMessage('回放完成。信号使用上一日及更早数据，在下一日收盘模拟成交；手续费已扣除。');}catch(error){setResult(null);setMessage(error.message);}};
 const save=()=>{try{const next=saveDemoStrategy(localStorage,readDemoStrategies(localStorage),rule);setSaved(next);setRule(next[0]);appendDemoAudit(localStorage,'strategy_saved',{id:next[0].id,name:next[0].name});setMessage('已保存至独立演示策略库，可在其他页面继续使用。');}catch(error){setMessage('保存失败：'+error.message);}};
 const remove=()=>{try{const next=readDemoStrategies(localStorage).filter(item=>item.id!==rule.id);localStorage.setItem(DEMO_STRATEGY_KEY,JSON.stringify(next));setSaved(next);appendDemoAudit(localStorage,'strategy_deleted',{id:rule.id,name:rule.name});setRule({...STRATEGY_TEMPLATES[0],id:undefined});setResult(null);setMessage('已删除选中的演示策略。');}catch{setMessage('本地存储不可用，删除未完成。');}};
 return <section className="demo-strategy"><header><div><small>SHARED STRATEGY ENGINE</small><h2>通用策略工作台</h2></div><span>只读回放</span></header><p>相同规则适用于股票、交易所资产和链上价格样例。策略模板可跨页面、跨市场复用；每次回放使用当前页面的模拟行情。</p>
 <div className="demo-strategy-layout"><form onSubmit={event=>{event.preventDefault();run();}}>
 <label>策略模板<select value={rule.kind} onChange={event=>{setRule({...STRATEGY_TEMPLATES.find(item=>item.kind===event.target.value),id:undefined,threshold:data.candles[0].close});setResult(null);setMessage('已载入模板。');}}>{STRATEGY_TEMPLATES.map(item=><option key={item.kind} value={item.kind}>{item.name}</option>)}</select></label>
 <label>策略名称<input value={rule.name} maxLength={80} required onChange={event=>update('name',event.target.value)}/></label>
 <div className="demo-fields"><label>观察周期（日）<input type="number" min="2" max="30" step="1" value={rule.lookback} onChange={event=>update('lookback',event.target.value)} required/></label><label>计划仓位（%）<input type="number" min="0.01" max="100" step="any" value={rule.allocation} onChange={event=>update('allocation',event.target.value)} required/></label>
 <label>止损（%）<input type="number" min="0.01" max="99" step="any" value={rule.stopLoss} onChange={event=>update('stopLoss',event.target.value)} required/></label><label>止盈（%）<input type="number" min="0.01" max="1000" step="any" value={rule.takeProfit} onChange={event=>update('takeProfit',event.target.value)} required/></label>
 <label>手续费（基点）<input type="number" min="0" max="100" step="any" value={rule.feeBps} onChange={event=>update('feeBps',event.target.value)} required/></label><label>模拟初始资金<input type="number" min="1" max="1000000000" step="any" value={capital} onChange={event=>{setCapital(event.target.value);setResult(null);}} required/></label></div>
 {rule.kind==='price'&&<div className="demo-fields"><label>价格方向<select value={rule.direction} onChange={event=>update('direction',event.target.value)}><option value="above">高于或等于</option><option value="below">低于或等于</option></select></label><label>价格阈值<input type="number" min="0.000001" step="any" value={rule.threshold} onChange={event=>update('threshold',event.target.value)} required/></label></div>}
 <p className="demo-rule">{rule.kind==='trend'?'入场：前一日收盘高于此前均线；退出：跌破均线或触及止盈止损。':rule.kind==='breakout'?'入场：前一日收盘突破此前区间最高价；退出：跌破区间最低价或触及止盈止损。':'满足价格条件时入场；条件失效或触及止盈止损时退出。'} 仅做多，最多一笔持仓。</p>
 <div className="demo-buttons"><button className="demo-primary" type="submit">运行模拟回放</button><button type="button" onClick={save}>保存策略</button><button type="button" onClick={()=>{setRule({...rule,id:undefined,name:rule.name+' 副本'});setResult(null);setMessage('已复制，请保存副本。');}}>复制</button><button type="button" disabled={!rule.id} onClick={remove}>删除</button></div>
 <label>演示策略库<select aria-label="载入演示策略" value={rule.id||''} onChange={event=>{const selected=saved.find(item=>item.id===event.target.value);if(selected){setRule(selected);setResult(null);setMessage('已载入保存的策略。');}}}><option value="">选择已保存策略（{saved.length}）</option>{saved.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
 <p role="status">{message}</p></form>
 <div className="demo-results">{result?<><div className="demo-metrics"><div><small>模拟收益率</small><b>{number(result.returnPct)}%</b></div><div><small>最大回撤</small><b>{number(result.maxDrawdown)}%</b></div><div><small>期末权益</small><b>{number(result.equity)}</b></div><div><small>累计手续费</small><b>{number(result.fees)}</b></div></div><LineChart values={result.curve.map(item=>item.equity)} label="模拟策略权益曲线"/><p>{result.trades.length} 条模拟成交记录 · 期末未平仓 {number(result.openQuantity)} 单位（按末日收盘估值）</p><div className="demo-table-wrap"><table><thead><tr><th>日期</th><th>方向 / 原因</th><th>成交价</th><th>数量</th><th>手续费</th></tr></thead><tbody>{result.trades.map((item,index)=><tr key={index}><td>{item.time}</td><td>{item.action} · {item.reason}</td><td>{number(item.price)}</td><td>{item.quantity.toPrecision(4)}</td><td>{number(item.fee)}</td></tr>)}</tbody></table>{!result.trades.length&&<p>此参数与场景没有触发成交，可更换场景或调整条件。</p>}</div></>:<div className="demo-result-empty"><h3>先定义规则，再验证行为</h3><p>回放会展示权益曲线、回撤、手续费与逐笔记录。可切换上涨、震荡、下跌样例比较策略表现。</p><LineChart values={data.candles.map(item=>item.close)} label="模拟输入价格曲线"/></div>}</div></div>
 <footer>固定生成的72日模拟行情，非真实历史回测。使用日线收盘模拟，未建模滑点、盘中成交及市场冲击；不据此推断未来收益，不产生订单。</footer></section>;
}
function DemoNotes({context}){
 const key='terminal.demo.notes.v1:'+context.market+':'+context.instrumentId;
 const sample='【模拟笔记】观察价格趋势与成交量；记录入场理由、风险上限与失效条件。下次复盘对照原始判断。';
 const [text,setText]=useState(()=>{try{return localStorage.getItem(key)??sample;}catch{return sample;}}),[status,setStatus]=useState('');
 return <section className="demo-page-panel"><h2>投资笔记 · 本机模拟</h2><label>研究与复盘笔记<textarea aria-label="模拟投资笔记" rows={5} value={text} onChange={event=>setText(event.target.value)} style={{width:'100%'}}/></label><button onClick={()=>{try{localStorage.setItem(key,text);setStatus('笔记已保存到本机，刷新后保留。');}catch{setStatus('保存失败，本机存储不可用。');}}}>保存笔记</button><p role="status">{status}</p></section>;
}
export default function DemoWorkspace({target,context,onExit}){
 const [scenario,setScenario]=useState('trend'),[query,setQuery]=useState(''),[selected,setSelected]=useState(null),[completed,setCompleted]=useState([]),[message,setMessage]=useState('');
 const [strategyOpen,setStrategyOpen]=useState(target.page==='strategy');
 const data=useMemo(()=>demoPageData(target,context,scenario),[target,context,scenario]);
 const rows=data.rows.filter(item=>Object.values(item).join(' ').toLowerCase().includes(query.toLowerCase()));
 return <main className="demo-workspace"><header className="demo-heading"><div><small>LOCAL DEMO / 模拟数据</small><h1>{target.label||target.tab} · 功能演示</h1><p>{context.market} · {data.symbol} · 固定示例，非实时数据</p></div><button onClick={onExit}>返回业务页面</button></header>
 <p className="demo-notice">演示操作保存在独立策略库或本次页面会话中，不读取账户凭证，不调用 AI、行情或交易接口。</p>
 <DemoNotes key={context.market+context.instrumentId} context={context}/>
 <div className="demo-toolbar"><label>行情场景<select value={scenario} onChange={event=>{setScenario(event.target.value);setMessage('已切换场景，请重新运行策略回放。');}}><option value="trend">上涨趋势</option><option value="range">区间震荡</option><option value="fall">持续回落</option></select></label><button aria-expanded={strategyOpen} onClick={()=>setStrategyOpen(value=>!value)}>{strategyOpen?'收起通用策略':'打开通用策略'}</button></div>
 {strategyOpen&&<StrategyWorkbench key={context.market+context.instrumentId} data={data}/>}
 {target.page!=='strategy'&&<section className="demo-page-panel"><header><h2>{target.tab} / {data.title}</h2><label>筛选样例<input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索名称、状态"/></label></header>
 {['home','market'].includes(target.page)&&<LineChart values={data.candles.map(item=>item.close)} label={`${target.tab}模拟价格走势`}/>}
 <div className="demo-table-wrap"><table><thead><tr>{data.columns.map(item=><th key={item}>{item}</th>)}<th>操作</th></tr></thead><tbody>{rows.map(item=><tr key={item.name}><td>{item.name}</td><td>{item.value}</td><td>{item.change}</td><td>{completed.includes(item.name)?'已完成演示':item.status}</td><td><button onClick={()=>setSelected(item)}>查看详情</button> <button disabled={completed.includes(item.name)} onClick={()=>{setCompleted(old=>[...old,item.name]);setMessage(`${item.name}：${data.action}完成，仅影响演示。`);}}>{data.action}</button></td></tr>)}</tbody></table>{!rows.length&&<p>没有匹配的模拟记录。</p>}</div>
 {selected&&<aside className="demo-detail"><h3>{selected.name}</h3><p>{data.columns[1]}：{selected.value} · {data.columns[2]}：{selected.change}</p><p>来源：本地模拟样例。此记录只用于体验{target.tab}的浏览、筛选与操作流程。</p><button onClick={()=>setSelected(null)}>关闭详情</button></aside>}<p role="status">{message}</p><button onClick={()=>{setCompleted([]);setQuery('');setSelected(null);setMessage('本页演示操作已重置，保存的策略仍保留。');}}>重置本页演示</button></section>}
 </main>;
}
