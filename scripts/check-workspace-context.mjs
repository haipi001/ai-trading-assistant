import assert from 'node:assert/strict';
import {nextWorkspaceContext,workspaceHistory} from '../src/workspace-context.js';
const base={page:'market',tab:'图表',asset_class:'crypto_spot',symbol:'BTC',venue:'OKX',timeframe:'1h',source:'online'};
const first=nextWorkspaceContext(null,base,0);
assert.equal(first.mode,null);assert.equal(first.account_id,null);assert.equal(first.context_version,1);
assert.equal(nextWorkspaceContext(first,{...base},1).context_version,1);
for(const [key,value] of Object.entries({symbol:'ETH',venue:'Bitget',timeframe:'5m',page:'news',account_id:'paper-a',mode:'PAPER',tab:'深度',user_id:'another-user',source:'csv'})){
 const changed=nextWorkspaceContext(first,{...base,[key]:value},2);
 assert.equal(changed.context_version,2,key);
 assert.deepEqual(workspaceHistory([{workspaceIdentity:first.identity,text:'BTC analysis'}],changed),[]);
}
const second=nextWorkspaceContext(first,{...base,symbol:'ETH'},3);
const back=nextWorkspaceContext(second,base,4);assert.equal(back.context_version,3);
assert.equal(workspaceHistory([{workspaceIdentity:first.identity,text:'BTC'},{workspaceIdentity:second.identity,text:'ETH'}],back)[0].text,'BTC');
assert.ok(Object.isFrozen(first));
console.log('Workspace context: unknown execution mode, stable tick identity, market/account isolation, monotonic versions and history filtering passed');
