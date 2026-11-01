export const LAYOUT_STORAGE_KEY='ai-trading-assistant-chart-tabs';
export function commitLayoutList(storage,expected,next){
 if(storage.getItem(LAYOUT_STORAGE_KEY)!==expected)throw new Error('其他页面已修改布局列表，请先重新读取列表；当前图表设置仍保留，可先导出备份');
 const raw=JSON.stringify(next);storage.setItem(LAYOUT_STORAGE_KEY,raw);return raw;
}
export async function commitLayoutListLocked(storage,locks,expected,next){
 if(!locks?.request)throw new Error('当前浏览器不支持安全的多页面布局保存，请先导出布局备份');
 return locks.request(LAYOUT_STORAGE_KEY,{mode:'exclusive'},()=>commitLayoutList(storage,expected,next));
}
