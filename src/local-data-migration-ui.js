import {exportLocalData,decodeLocalData,previewLocalData,applyLocalData,restoreLocalData,MIGRATION_LIMIT} from './local-data-migration.js';
import './local-data-migration.css';
const $=id=>document.getElementById(id);let plan=null;
$('origin').textContent='当前浏览器存储地址：'+location.origin;
const report=text=>$('status').textContent=text;
function preview(raw){plan=null;$('preview').replaceChildren();$('apply').disabled=true;const packet=decodeLocalData(raw);plan=previewLocalData(packet,localStorage);$('source').textContent=`来源：${packet.origin||'未标记'} · ${plan.length} 个条目`;
 for(const row of plan){const label=document.createElement('label');label.className='data-row';const check=document.createElement('input');check.type='checkbox';check.value=row.key;check.checked=row.status==='new';check.disabled=row.status==='same';const name=document.createElement('span');name.textContent=row.key.replace('ai-trading-assistant-','');const state=document.createElement('b');state.textContent={new:'新增',same:'相同',conflict:'本机已有 · 选中将替换'}[row.status];label.append(check,name,state);$('preview').append(label);}
 $('apply').disabled=!plan.some(row=>row.status!=='same');report('预览完成，请检查需要迁移的条目。');}
$('export').onclick=()=>{try{const raw=exportLocalData(localStorage,{origin:location.origin});const url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='r127-local-data.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);report('数据包已导出，原数据保持。');}catch(error){report('导出失败：'+error.message);}};
$('file').onchange=async event=>{try{const file=event.target.files?.[0];if(!file)return;if(file.size>MIGRATION_LIMIT)throw Error('数据包最大8MB');preview(await file.text());}catch(error){plan=null;$('preview').replaceChildren();$('apply').disabled=true;report('预览失败：'+error.message);}finally{event.target.value='';}};
$('preview-paste').onclick=()=>{try{preview($('paste').value);}catch(error){report('预览失败：'+error.message);}};
$('apply').onclick=()=>{try{if(!plan)throw Error('请先预览');const selected=[...$('preview').querySelectorAll('input:checked:not(:disabled)')].map(input=>input.value);const result=applyLocalData(plan,selected,localStorage);report(`已迁移 ${result.applied} 项（替换 ${result.overwritten} 项），迁移前备份已保存。请刷新新终端。`);plan=null;$('apply').disabled=true;}catch(error){report('迁移未完成：'+error.message);}};
$('restore').onclick=()=>{try{const count=restoreLocalData(localStorage);report(`已恢复 ${count} 项迁移前数据，请刷新新终端。`);plan=null;$('apply').disabled=true;}catch(error){report('恢复失败：'+error.message);}};
