// Credentials remain in memory, separate from local DEMO profiles.
export function createBackendClient({baseUrl='http://127.0.0.1:8001',fetcher=fetch}={}) {
 const url=new URL(baseUrl);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('invalid_backend_url');
 const base=url.href.replace(/\/$/,'');let session=null,attempt=0,revision=0;const listeners=new Set();
 const notify=()=>listeners.forEach(listener=>listener());
 function clear(){session=null;revision++;notify();}
 function metadata(){if(session&&Date.parse(session.expires_at)<=Date.now())clear();return session?{user_id:session.user.user_id,role:session.user.role,expires_at:session.expires_at}:null;}
 async function request(path,{method='GET',body,headers={},signal,timeout=10000,authenticated=true}={}){
  if(!path.startsWith('/')||path.startsWith('//'))throw Error('invalid_api_path');
  metadata();
  const authorization=authenticated&&session?`Bearer ${session.session_token}`:null;
  const requestBody=authorization&&body?.user_id==='default-user'?{...body,user_id:session.user.user_id}:body;
  const controller=new AbortController();const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();const timer=setTimeout(abort,timeout);
  try{const response=await fetcher(base+path,{method,credentials:'include',headers:{'Content-Type':'application/json',...headers,...(authorization?{Authorization:authorization}:{})},body:requestBody===undefined?undefined:JSON.stringify(requestBody),signal:controller.signal});if(!response.ok){if(response.status===401&&authorization===`Bearer ${session?.session_token}`)clear();const error=Error(`API ${response.status}`);error.status=response.status;try{const value=await response.json();const code=value?.detail?.code;if(typeof code==='string'&&/^[a-z_]{1,80}$/.test(code))error.code=code;}catch{}throw error;}return response.status===204?null:await response.json();}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
 }
 return {request,async login(accessToken){const id=++attempt;const value=await request('/production/auth/login',{method:'POST',body:{access_token:accessToken},authenticated:false});if(id!==attempt)throw Error('session_attempt_superseded');if(typeof value?.session_token!=='string'||!value.session_token||!value.user?.user_id||!(Date.parse(value.expires_at)>Date.now()))throw Error('invalid_session_response');session=value;revision++;notify();return metadata();},async logout(){attempt++;const token=session?.session_token;try{if(token)await request('/production/auth/logout',{method:'POST',body:{session_token:token}});}finally{if(session?.session_token===token)clear();}},session:metadata,identity(){return metadata()?`terminal-session-${revision}`:null;},clearSession(){attempt++;clear();},subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);}};
}
