import {fileURLToPath} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,channel:'chrome'}),page=await browser.newPage();
await page.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:8850/')?route.continue():route.abort());
await page.goto('http://127.0.0.1:8850/#HELP');await page.getByRole('button',{name:'通用策略 / 页面演示',exact:true}).click();
const frameElement=page.locator('#view iframe[data-terminal-feature]:visible').first();await frameElement.waitFor();const frame=await (await frameElement.elementHandle()).contentFrame();await frame.getByRole('heading',{name:'通用策略工作台',exact:true}).waitFor();assert.equal(await frame.locator('.demo-heading').count(),1);await writeFile(fileURLToPath(new URL('./global-entry-results.json',import.meta.url)),JSON.stringify({nativeToStrategy:true,automaticDemo:true},null,2));console.log('Native HELP → shared strategy demo passed');await browser.close();
