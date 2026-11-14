import {panelVisibility} from './panel-visibility.js';
/** No timer is kept while hidden. Returning to a visible panel refreshes once. */
export function observeVisibleInterval(callback,interval,environment={}) {
 const page=environment.page||panelVisibility(document),schedule=environment.schedule||setTimeout,cancel=environment.cancel||clearTimeout;
 let timer=null,stopped=false;const immediate=environment.immediate!==false;
 const clear=()=>{if(timer!==null)cancel(timer);timer=null;};
 const arm=()=>{if(!stopped&&!page.hidden)timer=schedule(tick,interval);};
 const tick=()=>{clear();if(stopped||page.hidden)return;callback();arm();};
 const changed=()=>{clear();if(!stopped&&!page.hidden){if(immediate)tick();else arm();}};
 page.addEventListener('visibilitychange',changed);changed();
 return()=>{stopped=true;clear();page.removeEventListener('visibilitychange',changed);};
}

/** Count visible time only, so a background notice is not dismissed unread. */
export function observeVisibleTimeout(callback,delay,environment={}) {
 const page=environment.page||panelVisibility(document),schedule=environment.schedule||setTimeout,cancel=environment.cancel||clearTimeout,now=environment.now||Date.now;
 let timer=null,started=null,remaining=delay,done=false;
 const pause=()=>{if(timer!==null)cancel(timer);timer=null;if(started!==null)remaining=Math.max(0,remaining-Math.max(0,now()-started));started=null;};
 const dispose=()=>{done=true;pause();page.removeEventListener('visibilitychange',changed);};
 const fire=()=>{if(done)return;if(page.hidden){pause();return;}dispose();callback();};
 const changed=()=>{pause();if(!done&&!page.hidden){started=now();timer=schedule(fire,remaining);}};
 page.addEventListener('visibilitychange',changed);changed();return dispose;
}
