export const UI_PALETTES=Object.freeze({
 dark:{surface:'#0d1319',subtle:'#151e26',hover:'#21303c',text:'#dce5ed',muted:'#96a5b3',dim:'#7e909f',line:'#2b3a47',strong:'#26333f',onStrong:'#ffffff',up:'#39c695',down:'#f57884',warning:'#e6b969'},
 light:{surface:'#ffffff',subtle:'#f3f5f7',hover:'#e7ecf0',text:'#202b35',muted:'#556777',dim:'#687987',line:'#ccd5dd',strong:'#26333f',onStrong:'#ffffff',up:'#087f5b',down:'#c43d50',warning:'#91611b'},
});
export function validAppearance(value){return value&&['dark','light'].includes(value.colorMode)&&['AMBER','ICE','TOXIC'].includes(value.palette);}
export function appearanceColors(mode='dark',palette='AMBER'){
 const value=UI_PALETTES[mode];if(!value)throw Error('invalid_appearance');
 const accent={dark:{AMBER:'#edaa54',ICE:'#56c9e8',TOXIC:'#78ce97'},light:{AMBER:'#955610',ICE:'#116e8c',TOXIC:'#217843'}}[mode][palette];
 if(!accent)throw Error('invalid_palette');return {...value,accent,accentSolid:mode==='dark'?'#875017':accent,upSolid:'#087f5b',downSolid:'#a93647',warningSolid:'#77521f'};
}
export function applyEmbeddedAppearance(value){
 if(!validAppearance(value))return false;
 const root=document.documentElement;root.dataset.terminalColorMode=value.colorMode;root.dataset.terminalPalette=value.palette;root.style.colorScheme=value.colorMode;
 for(const [key,color] of Object.entries(appearanceColors(value.colorMode,value.palette)))root.style.setProperty('--ui-'+key.replace(/[A-Z]/g,letter=>'-'+letter.toLowerCase()),color);
 window.dispatchEvent(new CustomEvent('terminal:appearance',{detail:value}));return true;
}
export function readEmbeddedAppearance(){
 if(typeof document==='undefined'||!document.documentElement.hasAttribute('data-terminal-feature'))return null;
 return appearanceColors(document.documentElement.dataset.terminalColorMode||'dark',document.documentElement.dataset.terminalPalette||'AMBER');
}
export function chartAppearance(background,theme){return theme?{background:/^#fff(?:fff)?$/i.test(background)?theme.surface:background,text:theme.muted,line:theme.line,grid:theme.subtle}:{background,text:'#7a8490',line:'#dfe4e7',grid:'#eef1f3'};}
export function requestEmbeddedAppearance(colorMode){if(!['dark','light'].includes(colorMode))throw Error('invalid_appearance');if(typeof document==='undefined'||!document.documentElement.hasAttribute('data-terminal-feature'))return;window.parent.postMessage({type:'terminal:feature-appearance-request',colorMode},window.location.origin);}
