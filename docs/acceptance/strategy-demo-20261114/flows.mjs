import {fileURLToPath} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
import assert from 'node:assert/strict';
import {writeFile,mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,channel:'chrome'});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('requestfailed',request=>{if(request.url().startsWith(base))console.log('REQUESTFAILED',request.url(),request.failure());});page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.message);});process.on('uncaughtException',async e=>{console.log('FAILED',e.message);console.log((await page.locator('body').innerText()).slice(0,3500));console.log('frames',page.frames().map(f=>f.url()));await page.screenshot({path:fileURLToPath(new URL('./failure.png',import.meta.url))});await browser.close();process.exit(1);});
// No account/API service required for all demo flows.
await page.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:8850/')?route.continue():route.abort());
const base='http://127.0.0.1:8850/';
await page.goto(base+'#R038');
const frame=async()=>{const el=page.locator('#view iframe[data-terminal-feature]:visible').first();await el.waitFor();return (await el.elementHandle()).contentFrame();};
await page.waitForFunction(()=>document.querySelector('iframe[data-terminal-feature]'));
await page.getByRole('button',{name:'通用策略 / 页面演示',exact:true}).click();
let f=await frame();await f.getByRole('heading',{name:'通用策略工作台',exact:true}).waitFor();
await f.getByLabel('策略名称',{exact:true}).fill('跨页面策略验收');await f.getByRole('button',{name:'保存策略',exact:true}).click();
await f.getByRole('button',{name:'运行模拟回放',exact:true}).click();assert.ok((await f.locator('.demo-results').innerText()).includes('模拟收益率'));
await page.screenshot({path:fileURLToPath(new URL('./strategy-desktop.png',import.meta.url))});
await f.getByLabel('行情场景').selectOption('fall');assert.equal(await f.getByLabel('策略名称',{exact:true}).inputValue(),'跨页面策略验收');assert.equal(await f.locator('.demo-results table').count(),0);await f.getByRole('button',{name:'运行模拟回放',exact:true}).click();
await f.getByRole('button',{name:'复制',exact:true}).click();await f.getByRole('button',{name:'保存策略',exact:true}).click();assert.equal(await f.getByLabel('载入演示策略').locator('option').count(),3);await f.getByRole('button',{name:'删除',exact:true}).click();assert.equal(await f.getByLabel('载入演示策略').locator('option').count(),2);
assert.ok(await f.evaluate(()=>JSON.parse(localStorage.getItem('terminal-demo-audit-v1')).some(row=>row.action==='strategy_deleted')));
// Cross-page saved strategy reuse and per-page operations.
const coverage=[];
for(const code of ['R001','R009','R014','R026','R042','R045','R051','R054','R056']){
 console.log('checking',code);await page.goto(base+'?demo-check='+code+'#'+code);await page.waitForLoadState('networkidle');await page.waitForFunction(()=>document.querySelector('iframe[data-terminal-feature]'));
 f=await frame();await f.getByRole('button',{name:'功能演示 · 模拟数据',exact:true}).click();await f.locator('.demo-page-panel tbody tr').first().waitFor();
 const count=await f.locator('.demo-page-panel tbody tr').count();assert.equal(count,3);
 await f.locator('.demo-page-panel tbody tr').first().getByRole('button',{name:'查看详情',exact:true}).click();await f.locator('.demo-detail').waitFor();
 await f.locator('.demo-page-panel tbody tr').first().locator('button').nth(1).click();assert.ok((await f.locator('.demo-page-panel tbody tr').first().innerText()).includes('已完成演示'));
 await f.getByLabel('筛选样例').fill('non-existent');assert.equal(await f.locator('.demo-page-panel tbody tr').count(),0);await f.getByRole('button',{name:'重置本页演示',exact:true}).click();assert.equal(await f.locator('.demo-page-panel tbody tr').count(),3);
 await f.getByRole('button',{name:'打开通用策略',exact:true}).click();await f.getByLabel('载入演示策略').selectOption({label:'跨页面策略验收'});assert.equal(await f.getByLabel('策略名称',{exact:true}).inputValue(),'跨页面策略验收');coverage.push(code);
}
await page.setViewportSize({width:390,height:844});await page.screenshot({path:fileURLToPath(new URL('./strategy-mobile.png',import.meta.url))});assert.ok(await f.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
await f.getByRole('button',{name:'返回业务页面',exact:true}).click();await f.getByRole('button',{name:'功能演示 · 模拟数据',exact:true}).waitFor();
assert.deepEqual(errors,[]);
console.log(JSON.stringify({coverage,errors,mobileOverflow:false,saveReplayReuse:true,apiBlocked:true},null,2));
await writeFile(fileURLToPath(new URL('./browser-results.json',import.meta.url)),JSON.stringify({coverage,errors,mobileOverflow:false,saveReplayReuse:true,apiBlocked:true},null,2));await browser.close();
