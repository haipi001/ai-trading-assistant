import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyAttachmentMatches,strategyReadiness} from '../../src/research-strategy.js';
const now=Date.now(),material={schema_version:1,source:'user_local_strategy_parameters',execution_available:false,usable_for_trading:false,independently_verified:false,market:'cex',account_id:'account',context_version:4,content_hash:'a'.repeat(64),captured_at:new Date(now).toISOString(),parameters:{name:'DCA',coin:'ETH',type:'DCA',amount:'10',platform:'mock',risk:'low',trigger:'weekly',invalidation:'manual stop',constraints:'no leverage'}};
const context={identityUserId:'owner',accountVerified:true,accountId:'account',market:'cex',contextVersion:4};
const attachment={material,ownerUserId:'owner',reference:{snapshot_id:'snapshot',...Object.fromEntries(['account_id','market','context_version','content_hash'].map(k=>[k,material[k]]))}};
test('strategy attachment requires explicit selection, same user/account/version and freshness',()=>{
 assert.ok(strategyAttachmentMatches(attachment,context,now));
 assert.ok(strategyReadiness(attachment,false,context));assert.equal(strategyReadiness(attachment,true,context),'');
 for(const patch of [{identityUserId:'foreign'},{accountId:'other'},{contextVersion:5},{market:'stocks'},{accountVerified:false}])assert.equal(!!strategyAttachmentMatches(attachment,{...context,...patch},now),false);
 assert.equal(!!strategyAttachmentMatches(attachment,context,now+600001),false);
 assert.ok(strategyReadiness(attachment,true,context,{includePaperReview:true}));
 assert.equal(strategyReadiness(null,false,context),'');
});
