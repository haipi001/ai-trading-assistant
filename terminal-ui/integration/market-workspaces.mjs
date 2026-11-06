import {switchMarket,marketContext} from './context.mjs';
import {normalizeView,normalizeMarketViews} from './workspace-state.mjs?v=2';
export function createMarketWorkspaces({getState,applyState,getLayout,applyLayout,getLocks,applyLocks,codes}){
 let saved={};
 const capture=()=>normalizeView({layout:getLayout(),locks:getLocks()},codes());
 const defaultView=market=>({layout:{layout:'1',func:market==='onchain'?'R042':'R009',sym:'',focus:0,split:{c:.5,r:.5},panels:Array.from({length:4},()=>({func:'HELP',sym:''}))},locks:[]});
 return {
  snapshot(){return normalizeMarketViews({...saved,[getState().current.market]:capture()},codes());},
  replace(value){saved=normalizeMarketViews(value,codes());},
  clearIdentities(){for(const view of Object.values(saved))for(const lock of view.locks)lock.context=marketContext(lock.context.market,{...lock.context,accountId:'',walletId:''});},
  switchTo(market){
   const beforeState=structuredClone(getState()),before=capture();if(market===beforeState.current.market)return;
   const nextState=switchMarket(beforeState,market),next=normalizeView(saved[market]||defaultView(market),codes());
   try{applyLocks(next.locks);applyState(nextState);applyLayout(next.layout);saved={...saved,[beforeState.current.market]:before};}
   catch(error){beforeState.current={...beforeState.current,executionMode:'READ_ONLY',contextVersion:nextState.current.contextVersion+1};applyLocks(before.locks);applyState(beforeState);applyLayout(before.layout);throw error;}
  }
 };
}
