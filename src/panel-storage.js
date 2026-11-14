export function instanceChartStorage(storage,instanceId='',profile='GUEST'){
 const scoped=key=>typeof key==='string'&&(key.startsWith('ai-trading-assistant-chart-')||key==='ai-trading-assistant-market-order-split'||key==='terminal-bottom-work-height');
 const keyFor=key=>instanceId&&scoped(key)?`${key}:profile:${encodeURIComponent(profile)}:instance:${encodeURIComponent(instanceId)}`:key;
 return {getItem(key){const value=storage.getItem(keyFor(key));return value===null&&keyFor(key)!==key?storage.getItem(key):value;},setItem(key,value){storage.setItem(keyFor(key),value);},removeItem(key){storage.removeItem(keyFor(key));}};
}
export function chartStorage(){const instance=typeof location==='undefined'?'':new URLSearchParams(location.search).get('instance')||'';let profile='GUEST';try{profile=localStorage.getItem('terminal.user')||profile;}catch{}return instanceChartStorage(localStorage,instance,profile);}
