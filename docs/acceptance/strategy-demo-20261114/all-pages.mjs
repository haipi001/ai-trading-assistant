import {fileURLToPath} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage({viewport:{width:1200,height:900}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
await page.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:8850/')?route.continue():route.abort());
await page.goto('http://127.0.0.1:8850/features/terminal-feature.html');
const targets=await page.evaluate(async()=>{await import('/integration/registry.js');return window.TERMINAL_FEATURES;});
const coverage=[];
for(const target of targets){
 await page.evaluate(target=>{window.postMessage({type:'terminal:feature-context',target,context:{market:'cex',instrumentId:'BTC/USDT',venue:'demo',timeframe:'1D',contextVersion:1,executionMode:'READ_ONLY'},appearance:{colorMode:'dark',palette:'AMBER'}},location.origin);window.postMessage({type:'terminal:feature-demo'},location.origin);},target);
 await page.locator('.demo-heading h1').filter({hasText:target.label+' · 功能演示'}).waitFor();
 if(target.page==='strategy'){await page.getByRole('button',{name:'运行模拟回放',exact:true}).click();await page.locator('.demo-metrics').waitFor();}
 else {assert.equal(await page.locator('.demo-page-panel tbody tr').count(),3);await page.locator('.demo-page-panel tbody tr').first().getByRole('button',{name:'查看详情',exact:true}).click();await page.locator('.demo-detail').waitFor();}
 coverage.push(target.code);
}
for(const market of ['stocks','cex','onchain']){
 const target=targets.find(item=>item.code==='R038');await page.evaluate(({target,market})=>{window.postMessage({type:'terminal:feature-context',target,context:{market,instrumentId:market==='stocks'?'AAPL':market==='cex'?'BTC/USDT':'DEMO-TOKEN',timeframe:'1D',contextVersion:2,executionMode:'READ_ONLY'},appearance:{colorMode:'light',palette:'ICE'}},location.origin);window.postMessage({type:'terminal:feature-demo'},location.origin);},{target,market});await page.getByRole('heading',{name:'通用策略工作台',exact:true}).waitFor();await page.getByRole('button',{name:'运行模拟回放',exact:true}).click();await page.locator('.demo-metrics').waitFor();
}
assert.equal(coverage.length,68);assert.deepEqual(errors,[]);
await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
await page.screenshot({path:fileURLToPath(new URL('./demo-mobile-fullwidth.png',import.meta.url))});
await writeFile(fileURLToPath(new URL('./all-pages-results.json',import.meta.url)),JSON.stringify({coverage,count:coverage.length,errors},null,2));console.log('68 business entries rendered and interacted; zero page errors; mobile width passed');await browser.close();
