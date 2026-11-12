export function checkCopyParameters({amount,stopLoss,mode}){
 for(const value of [amount,stopLoss])if(typeof value!=='string'||!/^\d{1,16}(\.\d{1,12})?$/.test(value)||!Number.isFinite(Number(value))||Number(value)<=0)throw Error('请输入有效的正数投入和止损意向');
 if(!['定额跟单','定比跟单'].includes(mode))throw Error('请选择有效跟单模式');
 return {amount,stopLoss,mode,executionAvailable:false,maximumLossVerified:false};
}
