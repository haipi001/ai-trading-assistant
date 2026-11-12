import test from 'node:test';
import assert from 'node:assert/strict';
import {workbenchFormKey,readWorkbenchForm,saveWorkbenchForm} from '../../src/workbench-form-buffer.js';
test('manual strategy inputs survive refresh only for the same user/account/instrument/panel and exclude results',()=>{
 const c={identityUserId:'owner',accountId:'a',market:'cex',instrumentId:'ETH/BTC',panelId:'0:STR3'};
 const key=workbenchFormKey('grid','ETH',c),defaults={amount:'',lower:'',upper:'',gridCount:'24'};
 const values=new Map(),storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};
 saveWorkbenchForm(storage,key,{amount:'invalid pending input',lower:'100',upper:'200',gridCount:'10',calculated:true,api_key:'secret'},defaults);
 assert.equal(readWorkbenchForm(storage,key,defaults).amount,'invalid pending input');assert.doesNotMatch(values.get(key),/secret|calculated/);
 for(const patch of [{accountId:'b'},{identityUserId:'foreign'},{instrumentId:'ETH/USDT'},{panelId:'1:STR3'}]){
  const other=workbenchFormKey('grid','ETH',{...c,...patch});assert.notEqual(other,key);assert.deepEqual(readWorkbenchForm(storage,other,defaults),defaults);
 }
 assert.equal(workbenchFormKey('grid','ETH',{market:'cex'}),null);
});
