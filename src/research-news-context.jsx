import React,{useEffect,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {newsSnapshot} from './news-feed-model.js';
const localTime=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'未知';
export function ResearchNewsContext({enabled,onChange,onReady,disabled=false}){
 const [preview,setPreview]=useState(null),[error,setError]=useState('');
 useEffect(()=>{
  if(!enabled){onReady(true);return;}
  let controller;
  const load=()=>{controller?.abort();const request=new AbortController();controller=request;onReady(false);setPreview(null);setError('');apiRequest('/news-feed/latest',{signal:request.signal}).then(raw=>{const value=newsSnapshot(raw);if(request.signal.aborted)return;setPreview(value);onReady(!!value.fetchedAt&&value.articles.length>0);}).catch(()=>{if(!request.signal.aborted){setError('无法读取资讯缓存，请检查后端连接。');onReady(false);}});};
  load();window.addEventListener('news-feed-settings-saved',load);
  return()=>{controller?.abort();window.removeEventListener('news-feed-settings-saved',load);};
 },[enabled,onReady]);

 return <section className="research-news-context"><label><input type="checkbox" aria-label="附带已获取资讯" checked={enabled} disabled={disabled} onChange={event=>onChange(event.target.checked)}/>附带最近已获取资讯（最多 5 条）</label>{enabled&&<div className="research-news-preview">{error?<p role="alert">{error}</p>:!preview?<p>正在读取后端资讯缓存…</p>:!preview.fetchedAt||!preview.articles.length?<p>尚无可用资讯，请先在快讯页获取消息，或取消附带资讯。</p>:<><p>{preview.provider} · {localTime(preview.fetchedAt)} 获取{preview.stale?' · 缓存已陈旧':''}{preview.status==='error'?' · 最近刷新失败':''}</p><ol>{preview.articles.slice(0,5).map((item,index)=><li key={item.id}><span>N{index+1}</span><span>{item.title}</span></li>)}</ol><small>点击发送时使用后端当前缓存，实际发送清单随回复显示。获取时间不等于消息发布时间。</small></>}</div>}</section>;
}
export function ResearchNewsSources({result}){
 const context=result?.provided_news;
 if(!context)return null;
 return <section className="research-news-sources"><h4>本次提供的资讯</h4><p>{context.provider} · {localTime(context.fetched_at)} 获取{context.stale?' · 陈旧缓存':''}{context.last_refresh_failed?' · 最近刷新失败':''}</p><p>这些是来源报道，未独立核实。模型标注的引用不代表结论已获验证。</p><ul>{context.articles.map(item=><li key={item.id}><a href={item.url} target="_blank" rel="noopener noreferrer">[{item.id}] {item.title}</a><small>{result.cited_news_ids?.includes(item.id)?'模型所列引用 · ':''}{item.publisher} · {item.published_at?localTime(item.published_at):item.published_at_raw||'发布时间未提供'}</small></li>)}</ul><small>资讯快照：{result.news_context_snapshot_id}</small></section>;
}
