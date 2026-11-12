export function spotDcaConfiguration(value){
 const allowed=['kind','frequency','first_run_local','take_profit_percent'];
 if(!value||Object.keys(value).some(key=>!allowed.includes(key))||value.kind!=='spot_dca'||!['每天','每周','每月'].includes(value.frequency))throw Error('现货DCA配置无效');
 const result={kind:'spot_dca',frequency:value.frequency};
 if(value.first_run_local!=null){
  const time=value.first_run_local;
  if(typeof time!=='string'||time.startsWith('0000')||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(time)||!Number.isFinite(Date.parse(time+'Z'))||new Date(time+'Z').toISOString().slice(0,time.length)!==time)throw Error('首次计划时间无效');
  result.first_run_local=time;
 }
 if(value.take_profit_percent!=null){const take=value.take_profit_percent;if(typeof take!=='string'||!/^\d{1,16}(\.\d{1,12})?$/.test(take)||Number(take)<=0)throw Error('止盈意向无效');result.take_profit_percent=take;}
 return result;
}
