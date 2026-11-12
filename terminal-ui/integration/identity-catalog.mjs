const text=(value,max=128)=>{if(typeof value!=='string'||!value.trim()||value.length>max)throw Error('invalid_identity_options');return value;};
export function identityCatalog(value){
 if(value?.execution_authorized!==false||value.source!=='owned_workspace_identities'||!Array.isArray(value.accounts)||!Array.isArray(value.wallets)||value.accounts.length>500||value.wallets.length>500)throw Error('invalid_identity_options');
 const userId=text(value.user_id),ids=new Set();
 const accounts=value.accounts.map(row=>{const id=text(row.id);if(ids.has(id)||!Array.isArray(row.markets)||row.markets.some(m=>!['stocks','cex'].includes(m))||typeof row.paper_eligible!=='boolean')throw Error('invalid_identity_options');ids.add(id);const mode=text(row.mode,32);if(row.paper_eligible&&(mode!=='paper'||!row.markets.length))throw Error('invalid_identity_options');return {id,label:text(row.label,255),markets:[...new Set(row.markets)],mode,baseCurrency:typeof row.base_currency==='string'&&/^[A-Z0-9]{2,12}$/.test(row.base_currency)?row.base_currency:null,paper_eligible:row.paper_eligible};});
 ids.clear();const wallets=value.wallets.map(row=>{const id=text(row.id);if(ids.has(id)||!(row.chain_id===null||typeof row.chain_id==='string'&&/^[1-9][0-9]{0,19}$/.test(row.chain_id)))throw Error('invalid_identity_options');ids.add(id);return {id,label:text(row.label),chain_id:row.chain_id};});
 return {userId,accounts,wallets};
}
export function identitiesFor(context,catalog){return {accounts:(catalog?.accounts||[]).filter(a=>a.markets.includes(context.market)),wallets:context.market==='onchain'?(catalog?.wallets||[]).filter(w=>w.chain_id===context.chainId):[]};}
export function verifiedIdentity(context,catalog){const {accounts,wallets}=identitiesFor(context,catalog);const account=accounts.find(a=>a.id===context.accountId);return {accountVerified:Boolean(account),paperEligible:Boolean(account?.paper_eligible),walletVerified:Boolean(wallets.find(w=>w.id===context.walletId))};}
export function identityPatch(context,catalog){
 if(!catalog)return context.executionMode==='PAPER'?{executionMode:'READ_ONLY'}:{};
 const status=verifiedIdentity(context,catalog),patch={};
 if(context.accountId&&!status.accountVerified)patch.accountId='';
 if(context.walletId&&!status.walletVerified)patch.walletId='';
 if(context.executionMode==='PAPER'&&!status.paperEligible)patch.executionMode='READ_ONLY';
 return patch;
}
export function createIdentityCatalog({request,identity=()=>null,notify=()=>{}}){
 let snapshot=null,revision=0,loading=false,error=null;
 function invalidate(){revision++;snapshot=null;loading=false;error=null;notify();}
 return {snapshot:()=>snapshot?structuredClone(snapshot):null,status:()=>({loading,error}),invalidate,
  async refresh(){const version=++revision,session=identity();snapshot=null;loading=true;error=null;notify();try{let offset=0,value=null;
   do {
    const packet=await request('/api/v2/workspaces/session/options'+(offset?'?offset='+offset:''),{timeout:5000});
    if(version!==revision||session!==identity())return;
    const page=identityCatalog(packet);
    if(value&&value.userId!==page.userId)throw Error('identity_changed');
    if(!value)value={userId:page.userId,accounts:[],wallets:[]};
    for(const key of ['accounts','wallets']){const ids=new Set(value[key].map(row=>row.id));for(const row of page[key]){if(ids.has(row.id))throw Error('identity_page_changed');ids.add(row.id);value[key].push(row);}}
    const next=packet.next_offset??null;
    if(next!==null&&(!Number.isSafeInteger(next)||next!==offset+500))throw Error('invalid_identity_pagination');
    offset=next;
   }while(offset!==null);
   snapshot=value;}catch(e){if(version!==revision)return;error=e.status===401?'请先登录后端会话':'账户与钱包列表不可用，请检查后端后重试';}finally{if(version===revision){loading=false;notify();}}}
 };
}

export function filterIdentityChoices(rows,query,selected){
 const needle=String(query||'').trim().toLocaleLowerCase();
 return rows.filter(row=>row.id===selected||!needle||[row.label,row.id,row.mode||''].some(value=>String(value).toLocaleLowerCase().includes(needle)));
}
