import {newsSnapshot} from './news-feed-model.js';

// Settings changes replace an in-flight read; normal refresh clicks coalesce.
export function createNewsFeedReader({request,onStart,onData,onError,onIdle}){
 let stopped=false,pending=false,generation=0,controller=null;
 return {
  async load({refresh=false,automatic=false,replace=false}={}){
   if(stopped||(pending&&!replace))return false;
   const version=++generation;
   if(replace)controller?.abort();
   const current=new AbortController();controller=current;pending=true;onStart();
   try{
    const value=newsSnapshot(await request(refresh?`/news-feed/refresh${automatic?'?automatic=true':''}`:'/news-feed/latest',{method:refresh?'POST':'GET',signal:current.signal,timeout:refresh?70000:8000}));
    if(!stopped&&version===generation)onData(value);
   }catch{
    if(!stopped&&version===generation&&!current.signal.aborted)onError();
   }finally{
    if(!stopped&&version===generation){pending=false;onIdle();}
   }
   return true;
  },
  stop(){stopped=true;++generation;pending=false;controller?.abort();}
 };
}
