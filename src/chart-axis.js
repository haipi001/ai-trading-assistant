export const DEFAULT_CHART_AXIS = Object.freeze({mode:'linear',inverted:false,autoScale:true});
export function validateChartAxis(value){
  if(!value||!['linear','logarithmic','percentage'].includes(value.mode)||typeof value.inverted!=='boolean'||typeof value.autoScale!=='boolean'||value.mode==='percentage'&&!value.autoScale)throw new Error('价格坐标轴设置无效');
  return {...value};
}
export function chartAxisOptions(value){const axis=validateChartAxis(value);return {mode:{linear:0,logarithmic:1,percentage:2}[axis.mode],invertScale:axis.inverted,autoScale:axis.autoScale};}
export function updatePaneAxis(axes,index,next,synchronized){validateChartAxis(next);if(!Number.isInteger(index)||index<0||index>=18)throw new Error('图窗序号无效');return Array.from({length:18},(_,i)=>({...((synchronized||i===index)?next:axes[i]||DEFAULT_CHART_AXIS)}));}
export function validatePriceRange(range){
  if(!range||![range.from,range.to].every(value=>typeof value==='number'&&Number.isFinite(value)&&value>0)||range.to<=range.from)throw new Error('价格上限必须大于下限，且均为正数');return {from:range.from,to:range.to};
}
export function parsePriceRange(from,to){if(String(from).trim()===''||String(to).trim()==='')throw new Error('请输入价格上下限');return validatePriceRange({from:Number(from),to:Number(to)});}
export function storedPriceRange(view,key,axis){if(!view||view.key!==key||axis.autoScale||axis.mode==='percentage'||view.priceMode!==axis.mode||!view.priceRange)return null;return validatePriceRange(view.priceRange);}
// LW5.2 setVisibleRange stores raw numbers, but the log getter interprets them
// as transformed values. Calibrate its integer log offset through public API
// reads; newer versions with a corrected setter take the direct path instead.
export function applyExactPriceRange(scale,range){
  validatePriceRange(range);const mode=scale.options().mode;
  if(mode!==0&&mode!==1)throw new Error('百分比坐标不接受绝对价格范围');
  scale.setVisibleRange(range);
  if(mode===0)return;
  const matches=actual=>actual&&["from","to"].every(key=>Number.isFinite(actual[key])&&Math.abs(actual[key]-range[key])<=Math.max(.00000001,Math.abs(range[key])*1e-6));
  if(matches(scale.getVisibleRange()))return;
  try {
    scale.setVisibleRange({from:100,to:101});
    const probe=scale.getVisibleRange()?.from;
    if(!Number.isFinite(probe)||probe<=0)throw new Error('无法校准对数价格轴');
    const offset=Math.round(100-Math.log10(probe));
    if(!Number.isInteger(offset)||offset<4||offset>100)throw new Error('无法校准对数价格轴');
    const transform=price=>Math.log10(price+10**-offset)+offset;
    scale.setVisibleRange({from:transform(range.from),to:transform(range.to)});
    if(!matches(scale.getVisibleRange()))throw new Error('价格精度不足，无法应用该范围');
  } catch(error){scale.applyOptions({autoScale:true});throw error;}
}
