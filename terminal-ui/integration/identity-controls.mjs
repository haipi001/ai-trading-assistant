import {identities} from './identity-service.mjs';
import {identitiesFor,identityPatch,verifiedIdentity} from './identity-catalog.mjs';
export function installIdentityControls({bar,getState,update}){
 const host=document.createElement('span');host.className='integration-identities';
 host.innerHTML='<label data-identity-account>账户 <select id="desk-account" aria-label="工作区账户"></select></label><label data-identity-wallet hidden>钱包 <select id="desk-wallet" aria-label="工作区钱包"></select></label><button type="button" id="desk-identities-refresh">刷新账户</button><span role="status" id="desk-identities-status"></span>';
 bar.querySelector('#desk-execution').closest('label').before(host);
 const account=host.querySelector('#desk-account'),wallet=host.querySelector('#desk-wallet'),retry=host.querySelector('button'),status=host.querySelector('[role="status"]');let syncing=false;
 function options(select,rows,selected,empty,loading){select.replaceChildren(new Option(empty,''));for(const row of rows)select.add(new Option(row.label,row.id));if(selected&&!rows.some(row=>row.id===selected)){const pending=new Option('待校验 '+(select===account?'账户':'钱包'),selected);pending.disabled=true;select.add(pending);}select.value=selected;select.disabled=loading;}
 function sync(){if(syncing)return;syncing=true;try{
  const catalog=identities.snapshot(),patch=identityPatch(getState().current,catalog);if(Object.keys(patch).length)update(patch);
  const context=getState().current,rows=identitiesFor(context,catalog),state=identities.status(),verified=verifiedIdentity(context,catalog);
  host.querySelector('[data-identity-account]').hidden=context.market==='onchain';host.querySelector('[data-identity-wallet]').hidden=context.market!=='onchain';
  options(account,rows.accounts.map(a=>({...a,label:a.label+' · '+a.mode})),context.accountId,'未选择账户',state.loading);
  options(wallet,rows.wallets,context.walletId,'未选择钱包',state.loading);
  bar.querySelector('#desk-execution [value="PAPER"]').disabled=context.market==='onchain'||!verified.paperEligible;
  retry.disabled=state.loading;status.textContent=state.loading?'正在校验账户与钱包':state.error||(!catalog?'尚未校验账户与钱包':context.market==='onchain'?`${rows.wallets.length}个同链只读钱包`:`${rows.accounts.length}个兼容账户`);
 }finally{syncing=false;}}
 account.onchange=()=>{const rows=identitiesFor(getState().current,identities.snapshot()).accounts;if(account.value&&!rows.some(a=>a.id===account.value))return sync();update({accountId:account.value});};
 wallet.onchange=()=>{const rows=identitiesFor(getState().current,identities.snapshot()).wallets;if(wallet.value&&!rows.some(w=>w.id===wallet.value))return sync();update({walletId:wallet.value});};
 retry.onclick=()=>identities.refresh();window.addEventListener('terminal:context',sync);window.addEventListener('terminal:identity-options',sync);window.addEventListener('terminal:session-changed',()=>identities.refresh());
 sync();identities.refresh();
}
