function positive(value){if(typeof value!=='string'||!/^\d{1,16}(\.\d{1,12})?$/.test(value)||!Number.isFinite(Number(value))||Number(value)<=0)throw Error('请填写有效的正数保证金和比例');return Number(value);}
export function checkFuturesDcaParameters({amount,leverage,addRatio,takeProfit,direction,frequency}){
 const margin=positive(amount);positive(addRatio);positive(takeProfit);
 if(margin<20||!['1x','2x','3x','5x','10x'].includes(leverage)||!['做多','做空'].includes(direction)||!['每1小时','每4小时','每天','每周'].includes(frequency))throw Error('保证金需不少于20，且需选择有效杠杆、方向与频率');
 const initialNotional=margin*Number(leverage.slice(0,-1));
 return {initialMargin:margin,initialNotional,absolutePnlForOnePercent:initialNotional*.01,maximumAdditionalMargin:null,maximumLoss:null,feesIncluded:false,executionAvailable:false};
}
