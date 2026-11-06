import assert from 'node:assert/strict';
import {workspaceSaveBody,workspaceRestorePlan} from '../src/workspace-sync.js';
const value={page:'market',tab:'图表',asset_class:'crypto_spot',symbol:'BTC',venue:'欧易OKX',timeframe:'1h',mode:null,account_id:null,user_id:'private',identity:'local',context_version:4};
const body=workspaceSaveBody(value,2,true);assert.equal(body.expected_version,2);assert.equal(body.context.user_id,undefined);assert.equal(body.context.identity,undefined);
assert.equal(workspaceRestorePlan({context:body.context,layout:body.layout}).period,'1时');
assert.equal(workspaceRestorePlan({context:{...body.context,timeframe:'1wk'}}).period,'1周');
for(const override of [{mode:'LIVE'},{account_id:'a'},{venue:'unknown'},{timeframe:'javascript:bad'},{page:'missing'}])assert.throws(()=>workspaceRestorePlan({context:{...body.context,...override}}));
console.log('Workspace persistence: bounded DTO, optimistic version, restore periods and no implicit account/trading authorization passed');
