import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import {JSDOM} from 'jsdom';
const html=await readFile(new URL('../terminal-ui/index.html',import.meta.url),'utf8');
const dom=new JSDOM(html,{url:'http://localhost:8851/index.html#WEI',runScripts:'outside-only',pretendToBeVisual:true});const {window}=dom;const errors=[];window.addEventListener('error',event=>errors.push(String(event.error?.message||event.message)));
window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}});window.ResizeObserver=class{observe(){}disconnect(){}unobserve(){}};window.HTMLElement.prototype.scrollIntoView=function(){};
window.HTMLCanvasElement.prototype.getContext=function(){const gradient={addColorStop(){}};return new Proxy({canvas:this,measureText:text=>({width:String(text).length*7}),createLinearGradient:()=>gradient,createRadialGradient:()=>gradient,getImageData:()=>({data:new Uint8ClampedArray(4)})},{get(target,key){return key in target?target[key]:()=>{};},set(target,key,value){target[key]=value;return true;}});};
window.eval(await readFile(new URL('../terminal-ui/integration/registry.js',import.meta.url),'utf8'));window.eval(await readFile(new URL('../terminal-ui/app.js',import.meta.url),'utf8'));
await new Promise(resolve=>window.setTimeout(resolve,20));assert.ok(window.TerminalWorkspace,'terminal must boot');

for(const name of ['window','document','localStorage','MutationObserver','CustomEvent'])globalThis[name]=name==='window'?window:window[name];
globalThis.requestAnimationFrame=callback=>setTimeout(callback,0);globalThis.confirm=()=>true;
window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};window.HTMLDialogElement.prototype.close=function(){this.open=false;};
await import('../terminal-ui/integration/workspace-tab-bar.mjs');
const flush=()=>new Promise(resolve=>setTimeout(resolve,20)),doc=window.document;
const run=value=>{doc.getElementById('cmd').value=value;doc.getElementById('gobtn').click();};
const activeFrame=()=>doc.querySelector('#view > iframe:not([hidden])');
const tab=text=>[...doc.querySelectorAll('[role=tab]')].find(node=>node.textContent===text);
const choose=label=>{const button=[...doc.querySelector('.workspace-tab-menu').querySelectorAll('button')].find(node=>node.textContent===label);assert.ok(button,label);button.click();};
await flush();run('R009');await flush();const original=activeFrame();assert.ok(tab('图表'));run('R010');await flush();assert.ok(tab('深度'));tab('图表').click();await flush();assert.equal(activeFrame(),original);
tab('图表').dispatchEvent(new window.MouseEvent('contextmenu',{bubbles:true}));choose('固定标签');assert.ok(tab('⌖ 图表'));
tab('⌖ 图表').dispatchEvent(new window.MouseEvent('contextmenu',{bubbles:true}));choose('新建同功能实例');await flush();assert.notEqual(activeFrame(),original);assert.equal(doc.querySelectorAll('#view > iframe[data-terminal-feature="R009"]').length,2);assert.ok(tab('⌖ 图表'));tab('⌖ 图表').click();await flush();assert.equal(activeFrame(),original);
tab('⌖ 图表').dispatchEvent(new window.MouseEvent('contextmenu',{bubbles:true}));choose('关闭其他标签');await flush();assert.ok(tab('⌖ 图表'));assert.equal(doc.querySelectorAll('[role=tab]').length,1);assert.equal(activeFrame(),original);
await import('../terminal-ui/integration/workspace-cache.mjs');let suspendedId;
for(const code of ['R001','R002','R003','R004','R005','R006','R007','R008','R009']){run(code);await flush();const frame=activeFrame();if(code==='R001')suspendedId=frame.dataset.workspaceInstance;frame.dataset.cacheDirty='false';frame.dataset.cacheRunning='false';window.dispatchEvent(new window.CustomEvent('terminal:cache-state'));await flush();}
assert.ok(doc.querySelectorAll('#view > iframe').length<=8,'clean background frames respect budget');const sleeping=[...doc.querySelectorAll('[role=tab]')].find(node=>node.textContent.includes('休眠'));assert.ok(sleeping,'suspended page retains a tab');sleeping.click();await flush();assert.ok(activeFrame());assert.equal(activeFrame().dataset.workspaceInstance,suspendedId,'sleeping tab restores original identity');
console.log('PASS actual cache DOM: confirmed-clean background eviction retains tab and restores instance');assert.deepEqual(errors,[]);
console.log('PASS actual app + tab DOM: open, activate, pin, duplicate instance, return and pinned-safe batch close');dom.window.close();
