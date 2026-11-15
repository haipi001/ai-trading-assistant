import {fileURLToPath} from 'node:url';
import {readFile,readdir} from 'node:fs/promises';import {resolve,join} from 'node:path';
const project=fileURLToPath(new URL('..',import.meta.url)),source=join(project,'terminal-ui'),runtime=resolve(process.argv[2]||join(project,'../terminal-ui'));
try{await readdir(runtime);}catch(error){if(error.code==='ENOENT'&&!process.argv[2]){console.log('SKIP optional external runtime mirror is absent');process.exit(0);}throw error;}
async function walk(dir,prefix=''){const result=[];for(const entry of await readdir(dir,{withFileTypes:true})){const relative=join(prefix,entry.name);if(entry.isDirectory())result.push(...await walk(join(dir,entry.name),relative));else if(/\.(mjs|js|css|html|json)$/.test(entry.name))result.push(relative);}return result;}
const paths=['app.js','workspace.js','index.html','styles.css',...(await walk(join(source,'integration'))).map(path=>'integration/'+path)];
const errors=[];for(const path of paths){try{const [a,b]=await Promise.all([readFile(join(source,path)),readFile(join(runtime,path))]);if(!a.equals(b))errors.push(path+': differs');}catch{errors.push(path+': missing');}}
if(errors.length){console.error(errors.join('\n'));process.exitCode=1;}else console.log(`PASS terminal source/runtime mirror: ${paths.length} files`);
