import assert from 'node:assert/strict';
import {aceReviewPlan,aceReviewUnavailable,noticeUpdate} from '../src/ace-status.js';
const notice={source_kind:'order_draft',source_id:'draft',source_revision:'a'.repeat(64),disposition_version:2,
 account_id:'paper-account',mode:'paper',order_type:'limit',quantity:1,limit_price:225.12,
 instrument:{asset_id:'aapl-id',symbol:'AAPL',asset_type:'stock',market:'US',venue:'NASDAQ',currency:'USD'}};
const plan=aceReviewPlan(notice);
assert.deepEqual(plan,{page:'market',tab:'图表',marketMode:'stocks',symbol:'AAPL',venue:'NASDAQ',draftId:'draft',assetId:'aapl-id',accountId:'paper-account'});
for(const patch of [{mode:'live'},{source_kind:'agent_proposal'},{order_type:'market'},{quantity:null},{limit_price:0}])assert.ok(aceReviewUnavailable({...notice,...patch}));
for(const patch of [{venue:'UNMAPPED'},{currency:'EUR'},{market:'EU'},{symbol:'<script>'}])assert.throws(()=>aceReviewPlan({...notice,instrument:{...notice.instrument,...patch}}),error=>error.local);
const crypto={...notice,instrument:{asset_id:'btc-id',symbol:'BTC/USDT',asset_type:'crypto',market:'GLOBAL',venue:'OKX',currency:'USDT'}};
assert.equal(aceReviewPlan(crypto).venue,'欧易OKX');assert.equal(aceReviewPlan(crypto).symbol,'BTC');
assert.equal(aceReviewPlan({...notice,instrument:{...notice.instrument,symbol:'TUSD'}}).symbol,'TUSD');
assert.deepEqual(noticeUpdate(notice,'ACKNOWLEDGED'),{source_revision:'a'.repeat(64),expected_version:2,status:'ACKNOWLEDGED'});
assert.throws(()=>noticeUpdate(notice,'approved'));assert.equal(plan.execution_authorized,undefined);
console.log('Ace status: supported instrument navigation, exact account/asset handoff, unmapped/live refusal and notification-only state update passed');
