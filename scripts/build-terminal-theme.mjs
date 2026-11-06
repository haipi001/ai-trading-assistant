import fs from 'node:fs/promises';
import postcss from 'postcss';
import {terminalThemePlugin} from './terminal-theme.mjs';
import {appearanceColors} from '../src/terminal-appearance.js';
const base=new URL('../../terminal-ui/',import.meta.url);
let tokens='/* Generated from src/terminal-appearance.js. Run npm run theme:terminal. */\n';
for(const mode of ['dark','light'])for(const palette of ['AMBER','ICE','TOXIC']){
 const colors=appearanceColors(mode,palette);colors.bg=mode==='dark'?'#070c11':'#edf1f4';
 tokens+=`html[data-terminal-color-mode="${mode}"][data-terminal-palette="${palette}"]{color-scheme:${mode};`+Object.entries(colors).map(([key,value])=>`--ui-${key.replace(/[A-Z]/g,ch=>'-'+ch.toLowerCase())}:${value};`).join('')+'}\n';
}
await fs.writeFile(new URL('integration/appearance.tokens.css',base),tokens);
const paths=['styles.css','integration/desk.css'];let overrides='/* Generated semantic overrides for the terminal chrome. */\n';
for(const path of paths){const result=await postcss([terminalThemePlugin({darkSource:true})]).process(await fs.readFile(new URL(path,base),'utf8'),{from:path});
 const only=postcss.parse(result.css);only.walkRules(rule=>{if(!rule.selector.startsWith('html[data-terminal-color-mode]'))rule.remove();});overrides+=only.toString()+'\n';
}
await fs.writeFile(new URL('integration/appearance.generated.css',base),overrides);
console.log('Terminal theme tokens and chrome overrides generated.');
