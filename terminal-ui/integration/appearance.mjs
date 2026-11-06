export const APPEARANCE_KEY='terminal-appearance-v1';
export function appearanceMode(value){return value==='light'?'light':'dark';}
export function appearancePacket(mode,palette='AMBER'){
 return {colorMode:appearanceMode(mode),palette:['AMBER','ICE','TOXIC'].includes(palette)?palette:'AMBER'};
}
export function installAppearance(){
 const button=document.createElement('button');button.id='appearance-toggle';button.className='mbtn';button.type='button';
 document.getElementById('thbtn').before(button);
 let mode='dark';try{mode=appearanceMode(localStorage.getItem(APPEARANCE_KEY));}catch{}
 function apply(next){mode=appearanceMode(next);document.documentElement.dataset.terminalColorMode=mode;document.documentElement.dataset.terminalPalette=document.getElementById('thbtn')?.dataset.theme||'AMBER';document.documentElement.style.colorScheme=mode;
  button.textContent=mode==='dark'?'黑':'白';button.setAttribute('aria-label',mode==='dark'?'切换为白色主题':'切换为黑色主题');button.title=mode==='dark'?'黑色主题 · 点击切换为白色':'白色主题 · 点击切换为黑色';
  try{localStorage.setItem(APPEARANCE_KEY,mode);}catch{button.title+=' · 本机保存失败';}
  window.dispatchEvent(new CustomEvent('terminal:appearance',{detail:appearancePacket(mode,document.getElementById('thbtn')?.dataset.theme)}));
 }
 button.onclick=()=>apply(mode==='dark'?'light':'dark');
 new MutationObserver(()=>apply(mode)).observe(document.getElementById('thbtn'),{attributes:true,attributeFilter:['data-theme']});
 window.addEventListener('terminal:appearance-request',event=>{if(['dark','light'].includes(event.detail?.colorMode))apply(event.detail.colorMode);});
 apply(mode);
}
