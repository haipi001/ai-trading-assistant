import {cp,mkdir,readFile,writeFile,rm,mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
const api=process.env.VITE_API_BASE_URL||'https://ai-trading-assistant-api.onrender.com';
const url=new URL(api);
if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash)throw Error('Public backend must be a credential-free HTTPS URL');
const temporary=await mkdtemp(join(tmpdir(),'terminal-public-'));
try{
 execFileSync('npm',['run','build'],{stdio:'inherit'});
 await cp('dist',join(temporary,'legacy'),{recursive:true});
 execFileSync('npm',['run','build:terminal'],{stdio:'inherit',env:{...process.env,VITE_API_BASE_URL:api,TERMINAL_FEATURE_OUTDIR:'terminal-ui/features'}});
 await rm('dist',{recursive:true,force:true});
 await cp('terminal-ui','dist',{recursive:true,filter:path=>!['tests','scripts','evidence'].includes(path.split('/').at(-1))&&!/\.(md|py|command)$/.test(path)});
 await cp(join(temporary,'legacy'),'dist/legacy',{recursive:true});
 // Existing standalone bundles retain their public-base asset paths.
 await cp(join(temporary,'legacy/assets'),'dist/assets',{recursive:true});
 const file='dist/index.html';let html=await readFile(file,'utf8');
 html=html.replace(/(<meta name="terminal-api-base" content=")[^"]*(">)/,(_,a,b)=>a+url.href.replace(/\/$/,'')+b);
 await writeFile(file,html);
 const controls='dist/integration/workspace-controls.mjs';let source=await readFile(controls,'utf8');
 source=source.replace('http://localhost:3002/local-data-migration.html','legacy/local-data-migration.html');await writeFile(controls,source);
 await writeFile('dist/.nojekyll','');
 console.log('Public terminal built; standalone retained at legacy/. Live remains closed.');
}finally{await rm(temporary,{recursive:true,force:true});}
