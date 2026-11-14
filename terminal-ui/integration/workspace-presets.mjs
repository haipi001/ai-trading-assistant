import {normalizePreferences} from './workspace-preferences.mjs';
const common=new Set(['R001','R009','R013','R014','R026','R045','R051','STR0','WEI','W','GP','PORT','ORD','SET','HELP']);
const direct=new Set(['ai','research','notes','calculator','news']);
export function applyWorkspacePreset(value,preset,codes,tools){if(!['standard','professional'].includes(preset))throw Error('invalid_preset');const next=normalizePreferences(value,codes,tools);next.navigation.hidden=preset==='standard'?codes.filter(code=>!common.has(code)):[];next.tools.hidden=[];next.tools.overflow=preset==='standard'?tools.filter(tool=>!direct.has(tool)):[];return next;}
export function importDisplayPreferences(text,codes,tools){if(typeof text!=='string'||text.length>65536)throw Error('配置文件超过64KB');const parsed=JSON.parse(text);if(parsed?.version!==1||!parsed.navigation||!parsed.tools)throw Error('不支持的展示配置格式');return normalizePreferences({navigation:parsed.navigation,tools:parsed.tools},codes,tools);}
export function exportDisplayPreferences(value,codes,tools){const clean=normalizePreferences(value,codes,tools);return JSON.stringify({version:1,navigation:clean.navigation,tools:clean.tools},null,2);}
