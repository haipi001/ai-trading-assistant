/** Demo content is shared across markets within one local profile. Legacy unscoped
 * records are left untouched because their owner cannot be established. */
export function createDemoProfileStorage(storage) {
  let profile='GUEST';
  try { profile=storage.getItem('terminal.user')||profile; } catch {}
  const suffix=':profile:'+encodeURIComponent(profile);
  const keyFor=key=>{
    if(!['terminal-demo-strategies-v1','terminal-demo-audit-v1'].includes(key)&&!key.startsWith('terminal.demo.notes.v1:'))throw Error('Unsupported demo storage key');
    return key+suffix;
  };
  return {keyFor,getItem:key=>storage.getItem(keyFor(key)),setItem:(key,value)=>storage.setItem(keyFor(key),value)};
}
