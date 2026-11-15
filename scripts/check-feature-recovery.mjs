import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {FeatureErrorBoundary} from '../src/feature-error-boundary.js';
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost:8851'});
globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true;
let fail=true;const original=console.error;console.error=()=>{};
function Page(){if(fail)throw Error('sensitive internal diagnostic');return React.createElement('p',null,'Recovered page');}
const root=createRoot(document.getElementById('root'));
try{
 await act(async()=>root.render(React.createElement(FeatureErrorBoundary,null,React.createElement(Page))));
 assert.match(document.body.textContent,/页面暂时无法显示/);assert.ok(!document.body.textContent.includes('sensitive'));
 fail=false;await act(async()=>document.querySelector('button').click());assert.equal(document.body.textContent,'Recovered page');
 await act(async()=>root.unmount());
 console.log('PASS render exception fallback, safe diagnostics and retry recovery');
}finally{console.error=original;dom.window.close();}

const startupHtml=await readFile(new URL('../terminal-feature.html',import.meta.url),'utf8');
const startup=new JSDOM(startupHtml,{url:'http://localhost:8851',runScripts:'outside-only'});
startup.window.eval(startup.window.document.querySelector('script:not([src])').textContent);
const startupDoc=startup.window.document,resource=startupDoc.querySelector('script[src]');
resource.dispatchEvent(new startup.window.Event('error'));
assert.match(startupDoc.getElementById('feature-startup').textContent,/功能资源加载失败/);
assert.equal(startupDoc.getElementById('feature-startup-reload').hidden,false);
startup.window.dispatchEvent(new startup.window.Event('terminal:feature-mounted'));
assert.equal(startupDoc.getElementById('feature-startup').hidden,true);
startup.window.close();
console.log('PASS pre-React resource failure notice and mounted cleanup');
