import {validateChartLayout} from './chart-layout-state.js';
export const CHART_LAYOUT_FILE_LIMIT=2*1024*1024;
export function encodeChartLayout(name,state){return JSON.stringify({format:'ai-trading-chart-layout',version:1,name:String(name||'图表布局').slice(0,80),state:validateChartLayout(state)},null,2);}
export function decodeChartLayout(text){
 if(typeof text!=='string'||new TextEncoder().encode(text).length>CHART_LAYOUT_FILE_LIMIT)throw new Error('布局文件最大2MB');
 let value;try{value=JSON.parse(text);}catch{throw new Error('布局JSON格式无效');}
 if(value?.format!=='ai-trading-chart-layout'||value.version!==1||typeof value.name!=='string'||!value.name.trim()||value.name.length>80)throw new Error('不支持的布局文件格式或版本');
 return {name:value.name.trim(),state:validateChartLayout(value.state)};
}
