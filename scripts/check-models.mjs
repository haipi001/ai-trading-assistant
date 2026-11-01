import {readdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const directory=new URL('.',import.meta.url);
const scripts=readdirSync(directory).filter(name=>/^check-.*\.mjs$/.test(name)&&name!=='check-models.mjs').sort();
let failed=0;
for(const name of scripts){
 const result=spawnSync(process.execPath,[fileURLToPath(new URL(name,directory))],{cwd:fileURLToPath(new URL('..',directory)),encoding:'utf8',timeout:40000});
 const ok=result.status===0&&!result.error;
 console.log(`${ok?'PASS':'FAIL'} ${name}`);
 if(!ok){failed++;process.stderr.write(result.stdout||'');process.stderr.write(result.stderr||'');if(result.error)console.error(result.error.message);}
}
console.log(`${scripts.length} model scripts; ${failed} failed`);
process.exitCode=failed?1:0;
