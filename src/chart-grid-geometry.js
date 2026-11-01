export function defaultGridColumns(count){return count<=1?1:count<=4?2:count<=9?3:count<=16?4:6;}
export function validateGridGeometry(value){
 if(value===null||value===undefined)return null;
 if(!Number.isInteger(value.columns)||value.columns<1||value.columns>6||!Array.isArray(value.weights)||value.weights.length!==value.columns||value.weights.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<.25||x>4))throw new Error('自定义图窗列宽无效');
 if(value.rowWeights!==undefined&&(!Array.isArray(value.rowWeights)||value.rowWeights.length<1||value.rowWeights.length>18||value.rowWeights.some(x=>typeof x!=="number"||!Number.isFinite(x)||x<.25||x>4)))throw new Error("图窗行高无效");
 return {columns:value.columns,weights:[...value.weights],...(value.rowWeights?{rowWeights:[...value.rowWeights]}:{})};
}
export function gridTemplate(count,geometry){
 const value=validateGridGeometry(geometry),columns=value?Math.min(count,value.columns):defaultGridColumns(count);
 return Array.from({length:columns},(_,index)=>`minmax(0,${value?.weights[index]??1}fr)`).join(' ');
}
export function resizeGridBoundary(geometry,index,delta){
 const next=validateGridGeometry(geometry);
 if(!next||!Number.isInteger(index)||index<0||index>=next.columns-1||!Number.isFinite(delta))throw new Error('图窗分隔线参数无效');
 const sum=next.weights[index]+next.weights[index+1];
 const left=Math.max(Math.max(.25,sum-4),Math.min(Math.min(4,sum-.25),next.weights[index]+delta));
 next.weights[index]=left;next.weights[index+1]=sum-left;
 return next;
}

export function gridRows(count,geometry){
 const value=validateGridGeometry(geometry),columns=Math.min(count,value?.columns??defaultGridColumns(count));
 return Array.from({length:Math.ceil(count/columns)},(_,i)=>`minmax(0,${value?.rowWeights?.[i]??1}fr)`).join(' ');
}
export function resizeGridRowBoundary(geometry,count,index,delta){
 const next=validateGridGeometry(geometry),rows=Math.ceil(count/Math.min(count,next.columns));
 if(!Number.isInteger(index)||index<0||index>=rows-1||!Number.isFinite(delta))throw new Error('图窗行分隔线无效');
 const weights=Array.from({length:rows},(_,i)=>next.rowWeights?.[i]??1),sum=weights[index]+weights[index+1];
 const left=Math.max(Math.max(.25,sum-4),Math.min(Math.min(4,sum-.25),weights[index]+delta));
 weights[index]=left;weights[index+1]=sum-left;return {...next,rowWeights:weights};
}
