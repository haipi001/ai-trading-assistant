import {createRequire} from 'node:module';
import {readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const root=new URL('../../',import.meta.url),require=createRequire(new URL('package.json',root));
const {parse}=require('@babel/parser');const controls=[],storage=[],shortcuts=[];
for(const file of readdirSync(new URL('src/',root)).filter(x=>/\.(jsx|js)$/.test(x))){
 const source=readFileSync(new URL('src/'+file,root),'utf8');const ast=parse(source,{sourceType:'module',plugins:['jsx']});
 function walk(node,owner='module'){
  if(!node||typeof node!=='object')return;
  if(node.type==='FunctionDeclaration'&&node.id)owner=node.id.name;
  if(node.type==='VariableDeclarator'&&node.id?.name&&/Function/.test(node.init?.type||''))owner=node.id.name;
  if(node.type==='JSXOpeningElement'){
   const name=node.name?.name||node.name?.property?.name;const attrs=node.attributes||[];const events=attrs.filter(x=>/^on[A-Z]/.test(x.name?.name||'')).map(x=>x.name.name);
   if(['button','input','textarea','select','a'].includes(name)||events.length)controls.push({file:'src/'+file,line:node.loc.start.line,owner,element:name,events,label:attrs.find(x=>x.name?.name==='aria-label')?.value?.value||null,status:'复用源码已纳入功能包；逐控件新终端验收待完成'});
  }
  if(node.type==='CallExpression'&&['useStoredState','getItem','setItem','removeItem'].includes(node.callee?.name||node.callee?.property?.name)){const key=node.arguments?.[0];if(key?.type==='StringLiteral')storage.push({file:'src/'+file,line:node.loc.start.line,key:key.value,owner,status:'需确认新旧同源持久化兼容与并发'});}
  if(node.type==='StringLiteral'&&['keydown','keyup','hashchange','popstate'].includes(node.value))shortcuts.push({file:'src/'+file,line:node.loc.start.line,event:node.value,owner,status:'需逐路径验收'});
  for(const [key,value] of Object.entries(node)){if(['loc','start','end','extra'].includes(key))continue;if(Array.isArray(value))value.forEach(x=>walk(x,owner));else if(value&&typeof value==='object')walk(value,owner);}
 }
 walk(ast);
}
const result={scope:'旧版src静态控件/存储/导航监听盘点；动态生成控件与运行时行为仍需人工验收',controls,storage,shortcuts};
writeFileSync(fileURLToPath(new URL('../integration/control-inventory.json',import.meta.url)),JSON.stringify(result,null,2));console.log(`${controls.length} JSX controls; ${storage.length} storage references; ${shortcuts.length} navigation/keyboard event references`);
