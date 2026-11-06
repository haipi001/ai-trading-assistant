export function getTerminalBackendBridge(){
 try{if(typeof window==='undefined'||typeof document==='undefined'||!document.documentElement.hasAttribute('data-terminal-feature')||window.parent===window||window.parent.location.origin!==window.location.origin)return null;const bridge=window.parent.TerminalBackend;return bridge&&typeof bridge.request==='function'&&typeof bridge.session==='function'?bridge:null;}catch{return null;}
}
