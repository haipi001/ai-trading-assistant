import {fileURLToPath} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,channel:'chrome'}),page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:8850/')?route.continue():route.abort());
await page.goto('http://127.0.0.1:8850/#HELP');await page.waitForFunction(()=>window.TerminalWorkspace&&window.TERMINAL_FEATURES);
const codes=await page.evaluate(()=>window.TerminalWorkspace.codes().filter(code=>!window.TERMINAL_FEATURES.some(item=>item.code===code)));
const results=[];
for(const code of codes){await page.goto('http://127.0.0.1:8850/?native-check='+code+'#'+code);await page.waitForFunction(()=>window.TerminalWorkspace);const content=await page.locator('#view').innerText();assert.ok(content.trim().length>10,code);results.push(code);}
assert.deepEqual(errors,[]);console.log(JSON.stringify({count:codes.length,codes:results,errors}));await writeFile(fileURLToPath(new URL('./native-results.json',import.meta.url)),JSON.stringify({count:codes.length,codes:results,errors},null,2));await browser.close();
