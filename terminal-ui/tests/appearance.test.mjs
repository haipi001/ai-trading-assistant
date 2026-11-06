import {test} from 'node:test';
import assert from 'node:assert/strict';
import postcss from '../../node_modules/postcss/lib/postcss.mjs';
import {appearanceMode,appearancePacket} from '../integration/appearance.mjs';
import {appearanceColors,validAppearance,chartAppearance,applyEmbeddedAppearance} from '../../src/terminal-appearance.js';
import {terminalThemePlugin} from '../../scripts/terminal-theme.mjs';
function luminance(hex){const linear=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return linear[0]*.2126+linear[1]*.7152+linear[2]*.0722;}
function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
test('appearance is a separate whitelisted preference and primary text retains contrast in all six palettes',()=>{
 assert.equal(appearanceMode('LIVE'),'dark');assert.deepEqual(appearancePacket('light','unknown'),{colorMode:'light',palette:'AMBER'});
 assert.equal(validAppearance({colorMode:'dark',palette:'ICE'}),true);assert.equal(validAppearance({colorMode:'custom',palette:'ICE'}),false);
 for(const mode of ['dark','light'])for(const palette of ['AMBER','ICE','TOXIC']){const c=appearanceColors(mode,palette);for(const text of ['text','muted'])for(const bg of ['surface','subtle'])assert.ok(contrast(c[text],c[bg])>=4.5,`${mode}/${palette}/${text}/${bg}`);for(const bg of ['accentSolid','upSolid','downSolid','warningSolid','strong'])assert.ok(contrast(c.onStrong,c[bg])>=4.5,`${mode}/${palette}/${bg}`);}
});
test('embedded theme changes only appearance attributes and CSS variables, with no execution context mutation',()=>{
 const attributes={},styles={},events=[];globalThis.document={documentElement:{dataset:attributes,style:{setProperty:(k,v)=>styles[k]=v}}};globalThis.window={dispatchEvent:e=>events.push(e)};const original=globalThis.CustomEvent;globalThis.CustomEvent=class{constructor(type,options){this.type=type;this.detail=options.detail;}};
 try{assert.equal(applyEmbeddedAppearance({colorMode:'bad',palette:'AMBER'}),false);assert.deepEqual(attributes,{});assert.equal(applyEmbeddedAppearance({colorMode:'light',palette:'ICE'}),true);assert.equal(attributes.terminalColorMode,'light');assert.equal(styles['--ui-surface'],'#ffffff');assert.equal(attributes.executionMode,undefined);assert.equal(events[0].type,'terminal:appearance');}finally{delete globalThis.document;delete globalThis.window;globalThis.CustomEvent=original;}
});
test('default chart background follows appearance while custom backgrounds and standalone appearance remain intact',()=>{
 const dark=appearanceColors('dark');assert.equal(chartAppearance('#ffffff',dark).background,dark.surface);assert.equal(chartAppearance('#123456',dark).background,'#123456');assert.equal(chartAppearance('#ffffff',null).background,'#ffffff');
});
test('embedded CSS overrides retain original standalone rules, responsive context, semantic gains/losses and drawings',async()=>{
 const source='.box{background:#fff;color:#20252c;border:1px solid #ddd}.buy{color:#00a877}.sell{color:#eb5260}@media(max-width:700px){.box{background:#f4f5f6}}.drawing{stroke:#2979ff;fill:#fff}@keyframes blink{to{background:#fff}}';
 const result=await postcss([terminalThemePlugin()]).process(source,{from:undefined});
 assert.ok(result.css.includes('.box{background:#fff;color:#20252c;border:1px solid #ddd}'));
 assert.ok(result.css.includes('html[data-terminal-color-mode] .box{background:var(--ui-surface);color:var(--ui-text);border:1px solid var(--ui-line)}'));
 assert.ok(result.css.includes('.buy{color:var(--ui-up)}'));assert.ok(result.css.includes('.sell{color:var(--ui-down)}'));
 assert.ok(result.css.includes('@media(max-width:700px){.box{background:#f4f5f6}html[data-terminal-color-mode] .box{background:var(--ui-subtle)}}'));
 assert.ok(result.css.includes('.drawing{stroke:#2979ff;fill:#fff}'));assert.ok(result.css.includes('@keyframes blink{to{background:#fff}}'));
});
