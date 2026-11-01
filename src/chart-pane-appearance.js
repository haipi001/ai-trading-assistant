export const CHART_TYPES=['蜡烛图','空心蜡烛','折线图','面积图','平均K线','美国线','K线图(HLC)'];
export function validatePaneAppearance(value){
 if(!value||!CHART_TYPES.includes(value.chartType)||!/^#[\da-f]{6}$/i.test(value.background))throw new Error('图窗样式或背景无效');
 return {chartType:value.chartType,background:value.background};
}
export function updatePaneAppearance(values,index,next,sync){
 const appearance=validatePaneAppearance(next);
 if(!Number.isInteger(index)||index<0||index>17)throw new Error('图窗编号无效');
 return Array.from({length:18},(_,i)=>sync||i===index?{...appearance}:{...(values[i]||appearance)});
}
