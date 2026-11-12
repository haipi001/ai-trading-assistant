// Local UI records carry no evidence of a running server strategy.
export function localStrategyLabel(record){
 if(record?.status==='待启动')return '本地配置 · 未启动';
 if(record?.status==='已终止')return '本地配置 · 已归档';
 if(record?.status==='草稿')return '本地草稿';
 return record?.status==='已暂停'?'本地模拟 · 已暂停':'本地模拟 · 未验证运行';
}
export function toggleLocalStrategy(record){
 if(!record||record.status==='草稿')return record;
 return {...record,status:record.status==='已暂停'?'待启动':'已暂停'};
}
