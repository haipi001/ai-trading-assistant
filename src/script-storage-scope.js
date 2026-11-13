import {SCRIPT_STORE_KEY,SCRIPT_BUFFER_KEY} from './script-drafts.js';
export function scriptStorageKey(key,userId){
 if(typeof userId!=='string'||!userId||userId.length>128)throw Error('脚本身份尚未校验，不能读取私人草稿。');
 if(![SCRIPT_STORE_KEY,SCRIPT_BUFFER_KEY].includes(key))throw Error('unsupported script storage key');
 return key+':user:'+JSON.stringify(userId);
}
export function scopedScriptStorage(storage,userId){
 return {getItem:key=>storage.getItem(scriptStorageKey(key,userId)),setItem:(key,value)=>storage.setItem(scriptStorageKey(key,userId),value),removeItem:key=>storage.removeItem(scriptStorageKey(key,userId))};
}
export function sessionBoundScriptStorage(storage,readIdentity){
 const identity=readIdentity();
 const check=()=>{if(identity!==readIdentity())throw Error('脚本会话已变化');};
 return {getItem:key=>{check();return storage.getItem(key);},setItem:(key,value)=>{check();storage.setItem(key,value);},removeItem:key=>{check();storage.removeItem(key);}};
}
