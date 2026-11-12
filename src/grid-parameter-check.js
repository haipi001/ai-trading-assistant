function positive(value){
 if(typeof value!=='string'||!/^\d{1,16}(\.\d{1,12})?$/.test(value)||!Number.isFinite(Number(value))||Number(value)<=0)throw Error('请填写有效的正数价格和预算');
 return Number(value);
}
export function checkGridParameters({lower,upper,gridCount,amount}){
 const low=positive(lower),high=positive(upper),budget=positive(amount);
 if(high<=low||budget<20||typeof gridCount!=='string'||!/^\d{1,3}$/.test(gridCount)||Number(gridCount)<2||Number(gridCount)>500)throw Error('上界须高于下界，网格数为2–500整数，投入不少于20');
 const count=Number(gridCount);
 return {lower:low,upper:high,intervals:count,priceSpacing:(high-low)/count,budgetPerInterval:budget/count,feesIncluded:false,executionAvailable:false};
}

export function gridConfiguration(value){
 if(!value||Object.keys(value).sort().join(',')!=='intervals,kind,lower,upper'||value.kind!=='arithmetic_grid'||!Number.isInteger(value.intervals))throw Error('网格配置无效');
 checkGridParameters({lower:value.lower,upper:value.upper,gridCount:String(value.intervals),amount:'20'});
 return {kind:'arithmetic_grid',lower:value.lower,upper:value.upper,intervals:value.intervals};
}
