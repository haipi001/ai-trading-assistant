// Only the embedded build receives these overrides; standalone r127 CSS is unchanged.
export function themedColor(hex,property,{darkSource=false}={}){
 let raw=hex.toLowerCase().replace('#','');if(raw.length===3||raw.length===4)raw=[...raw].map(ch=>ch+ch).join('');
 if(!/^[0-9a-f]{6}([0-9a-f]{2})?$/.test(raw))return hex;
 const [r,g,b]=[0,2,4].map(index=>parseInt(raw.slice(index,index+2),16)/255),alpha=raw.length===8?parseInt(raw.slice(6),16)/255:1;
 const hi=Math.max(r,g,b),lo=Math.min(r,g,b),luma=.2126*r+.7152*g+.0722*b,sat=hi-lo;
 const background=/background/.test(property),border=/border|outline|decoration/.test(property),shadow=/shadow/.test(property);
 let token;
 if(shadow)return `rgba(0,0,0,${Math.min(alpha,.2).toFixed(3)})`;
 if(sat>.16){
  const family=r>g&&g>b*1.35?'warning':r>g*1.22&&r>b*1.12?'down':g>r*1.15&&g>b*.95?'up':'accent';
  token=border?'line':background?(luma>.72||alpha<.3?'subtle':family+'-solid'):family;
 }else if(border)token='line';
 else if(background)token=darkSource?(luma<.07?'bg':luma<.15?'surface':luma<.35?'subtle':'hover'):(luma<.3?'strong':luma<.8?'hover':luma<.985?'subtle':'surface');
 else token=darkSource?(luma>.65?'text':luma>.35?'muted':'dim'):(luma>.96?'on-strong':luma>.63?'dim':luma>.23?'muted':'text');
 const color=`var(--ui-${token})`;return alpha===1?color:`color-mix(in srgb, ${color} ${(alpha*100).toFixed(2)}%, transparent)`;
}
export function themedValue(value,property,options){
 if(!/^(color|background(?:-color|-image)?|border(?:-(?:top|right|bottom|left))?(?:-color)?|outline(?:-color)?|(?:box|text)-shadow|text-decoration-color|caret-color|accent-color)$/.test(property))return value;
 return value.replace(/#[\da-f]{3,8}\b|rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/gi,(match,r,g,b,a)=>{
  if(match.startsWith('#'))return themedColor(match,property,options);
  const channels=[r,g,b].map(v=>Math.round(Math.max(0,Math.min(255,Number(v)))).toString(16).padStart(2,'0')).join('');
  return themedColor('#'+channels+(a===undefined?'':Math.round(Number(a)*255).toString(16).padStart(2,'0')),property,options);
 });
}
export function terminalThemePlugin(options={}){
 return {postcssPlugin:'terminal-semantic-theme',Once(root){
  root.walkRules(rule=>{
   if(rule.raws.terminalThemed)return;let parent=rule.parent;while(parent){if(parent.type==='atrule'&&/keyframes/.test(parent.name))return;parent=parent.parent;}
   const declarations=[];rule.walkDecls(decl=>{const value=themedValue(decl.value,decl.prop,options);if(value!==decl.value)declarations.push(decl.clone({value}));});
   if(!declarations.length)return;
   const scope='html[data-terminal-color-mode]';const selectors=rule.selectors.map(selector=>selector.includes(':root')?selector.replace(/:root/g,scope):/^html\b/.test(selector)?selector.replace(/^html\b/,scope):scope+' '+selector);
   const themed=rule.clone({selector:selectors.join(',')});themed.removeAll();themed.append(declarations);themed.raws.terminalThemed=true;rule.after(themed);
  });
 }};
}
