import { CHART_TYPES, validatePaneAppearance } from "./chart-pane-appearance.js";
import { validateGridGeometry } from "./chart-grid-geometry.js";
import { validateChartAxis } from "./chart-axis.js";
import { validateAnchoredDrawing } from "./chart-drawings.js";
import { validateViewport } from "./chart-viewport.js";
import { periodDefinition } from './market-chart-model.js';
const counts=new Set([1,2,3,4,5,6,7,8,9,10,12,15,16,18]);
const syncOptions=new Set(['十字光标','交易对','指标','周期','日期范围','对比K线','缩放比例','坐标轴','其他']);
export function validateChartLayout(value) {
  if(!value || value.schema!==1) throw new Error('不支持的图表布局版本');
  const text=(value,max=100)=>typeof value==='string' && value.length>0 && value.length<=max;
  const names=value=>Array.isArray(value)&&value.length<=100&&value.every(item=>text(item))&&new Set(value).size===value.length;
  if(!['web3','stocks'].includes(value.marketMode)||!text(value.symbol)||!text(value.venue)||!counts.has(value.paneCount)||!CHART_TYPES.includes(value.chartType)||!names(value.studies)||!names(value.paneSync)||value.paneSync.some(item=>!syncOptions.has(item))) throw new Error('图表布局字段无效');
  periodDefinition(value.period);
  if(!Array.isArray(value.paneSymbols)||value.paneSymbols.length!==18||!value.paneSymbols.every(item=>text(item))||!Array.isArray(value.panePeriods)||value.panePeriods.length!==18||!Array.isArray(value.paneStudies)||value.paneStudies.length!==18||!value.paneStudies.every(names)) throw new Error('图窗设置不完整');
  value.panePeriods.forEach(periodDefinition);
  const next=structuredClone(value);
  if(next.paneAppearance!==undefined){if(!Array.isArray(next.paneAppearance)||next.paneAppearance.length!==18)throw new Error("图窗样式目录无效");next.paneAppearance=next.paneAppearance.map(validatePaneAppearance);}
  if(next.paneGeometry!==undefined)next.paneGeometry=validateGridGeometry(next.paneGeometry);
  if(next.paneAxes!==undefined){if(!Array.isArray(next.paneAxes)||next.paneAxes.length!==18)throw new Error("坐标轴目录无效");next.paneAxes=next.paneAxes.map(validateChartAxis);}
  if(next.viewports!==undefined) {
    if(!next.viewports||Array.isArray(next.viewports)||typeof next.viewports!=="object"||Object.keys(next.viewports).some(key=>!/^([0-9]|1[0-7])$/.test(key)))throw new Error('图窗视口目录无效');
    for(const key of Object.keys(next.viewports)) next.viewports[key]=validateViewport(next.viewports[key]);
  }
  if(next.drawings!==undefined){if(!Array.isArray(next.drawings)||next.drawings.length>1000)throw new Error("绘图目录无效");for(const drawing of next.drawings){if(!drawing||typeof drawing.id!=="string")throw new Error("绘图对象无效");if(drawing.schema===2)validateAnchoredDrawing(drawing);else if(drawing.schema!==undefined||!["趋势线","水平线","平行线","矩形","测量","斐波那契","文本","画笔"].includes(drawing.type)||![drawing.x,drawing.y].every(value=>typeof value==="number"&&Number.isFinite(value)&&value>=0&&value<=100))throw new Error("旧版绘图对象无效");}if(new Set(next.drawings.map(drawing=>drawing.id)).size!==next.drawings.length)throw new Error("绘图对象ID重复");}
  return next;
}
export function captureChartLayout(state) {
  return validateChartLayout({schema:1,...(state.paneAppearance?{paneAppearance:state.paneAppearance}:{}),...(state.paneGeometry?{paneGeometry:state.paneGeometry}:{}),...(state.paneAxes?{paneAxes:state.paneAxes}:{}),...(state.drawings?{drawings:state.drawings}:{}),...(state.viewports?{viewports:state.viewports}:{}),marketMode:state.marketMode,symbol:state.symbol,venue:state.venue,period:state.period,chartType:state.chartType,paneCount:state.paneCount,paneSync:[...state.paneSync],studies:[...state.studies],paneSymbols:Array.from({length:18},(_,i)=>state.paneSymbols[i]||state.symbol),panePeriods:Array.from({length:18},(_,i)=>state.panePeriods[i]||state.period),paneStudies:Array.from({length:18},(_,i)=>[...(state.paneStudies[i]||state.studies)])});
}
