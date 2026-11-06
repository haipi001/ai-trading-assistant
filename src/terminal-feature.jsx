import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {App} from './main.jsx';
import './terminal-feature.css';
import '../../terminal-ui/integration/appearance.tokens.css';
import {applyEmbeddedAppearance} from './terminal-appearance.js';
function Feature(){
 const [packet,setPacket]=useState(null);
 const current=useRef(null);
 const pendingSelection=useRef(null);
 useEffect(()=>{const focus=()=>parent.postMessage({type:'terminal:feature-focus'},location.origin);document.addEventListener('pointerdown',focus);const selection=event=>{pendingSelection.current={...pendingSelection.current,...event.detail};queueMicrotask(()=>{if(!pendingSelection.current||!current.current)return;const patch=pendingSelection.current;pendingSelection.current=null;parent.postMessage({type:'terminal:feature-edit',contextVersion:current.current.context.contextVersion,patch},location.origin);});};window.addEventListener('terminal:selection',selection);const receive=event=>{if(event.origin!==location.origin||event.source!==parent)return;if(event.data?.type==='terminal:feature-appearance'){applyEmbeddedAppearance(event.data.appearance);return;}if(event.data?.type==='terminal:feature-research'){if(typeof event.data.question==='string'&&event.data.contextVersion===current.current?.context.contextVersion)window.dispatchEvent(new CustomEvent('terminal:research',{detail:{question:event.data.question}}));return;}if(event.data?.type!=='terminal:feature-context')return;const value=event.data;if(!value.target||typeof value.target.page!=='string'||!value.context||!['stocks','cex','onchain'].includes(value.context.market))return;applyEmbeddedAppearance(value.appearance);current.current=value;window.TerminalFeatureContext=Object.freeze({...value.context});setPacket(value);};window.addEventListener('message',receive);parent.postMessage({type:'terminal:feature-ready'},location.origin);return()=>{window.removeEventListener('message',receive);window.removeEventListener('terminal:selection',selection);document.removeEventListener('pointerdown',focus);};},[]);
 if(packet?.context.market==='onchain'&&packet.target.page==='market')return <section className="feature-loading"><h2>链上行情</h2><p>链 ID：{packet.context.chainId} · 合约：{packet.context.contractAddress||'未选择'}</p><p>链上报价适配器尚未接入。请通过链上研究功能查看已支持的页面，当前不使用 CEX 报价代替链上合约价格。</p></section>;
 return packet?<App embedded terminalTarget={packet.target} terminalContext={packet.context}/>:<p className="feature-loading">正在连接终端工作区…</p>;
}
createRoot(document.getElementById('feature-root')).render(<Feature/>);
