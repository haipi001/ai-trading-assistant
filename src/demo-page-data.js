import {demoCandles} from './demo-strategy-model.js';
const row=(name,value,change,status)=>({name,value,change,status});
export const DEMO_PAGE_GROUPS=['home','market','flash','news','strategy','chain','assets','auth','data','more'];
export function demoPageData(target,context,scenario='trend'){
 if(!DEMO_PAGE_GROUPS.includes(target.page))throw Error('此页面没有业务演示模板');
 const candles=demoCandles(context.market,scenario),last=candles.at(-1),symbol=context.instrumentId||'未选择标的';
 const marketRows=[row(symbol,last.close.toFixed(4),'+2.4%','模拟行情'),row(context.market==='stocks'?'MSFT':'ETH',context.market==='stocks'?'420.50':'3200.00','−1.2%','观察'),row(context.market==='stocks'?'NVDA':'SOL',context.market==='stocks'?'135.80':'148.60','+3.1%','关注')];
 const data={home:{title:'市场观察',columns:['标的','示例价格','日变动','状态'],rows:marketRows,action:'加入演示自选'},market:{title:'行情快照',columns:['标的','示例价格','日变动','状态'],rows:marketRows,action:'添加价格提醒'},flash:{title:'模拟快讯流',columns:['事件','时点','类别','核验状态'],rows:[row(`${target.tab} · 资金流观察`,'09:30','市场','待核验'),row('示例机构更新研究观点','10:15','研究','模拟素材'),row('示例宏观指标即将公布','14:00','日历','模拟素材')],action:'收藏快讯'},news:{title:'示例研究资料',columns:['标题','阅读时间','类别','状态'],rows:[row(`${target.tab} · 市场结构观察`,'5 分钟','研究','未读'),row('波动与流动性情景分析','8 分钟','风险','未读'),row('多资产配置演示报告','6 分钟','配置','未读')],action:'加入阅读清单'},chain:{title:'链上观察样例',columns:['对象','示例规模','变化','状态'],rows:[row('演示地址 A','120,000 USD','+4.2%','只读观察'),row('演示资金池 B','850,000 USD','−2.1%','流动性观察'),row('演示事件 C','24 条','+3','待核验')],action:'跟踪演示对象'},assets:{title:'模拟组合',columns:['资产','示例市值','权重','状态'],rows:[row(symbol,'5,000 USD','50%','模拟持仓'),row('现金','3,000 USD','30%','模拟现金'),row('其他资产','2,000 USD','20%','模拟持仓')],action:'加入演示复盘'},auth:{title:'连接流程演示',columns:['连接','权限','模式','状态'],rows:[row('演示交易账户','只读','模拟','未连接'),row('演示证券账户','只读','模拟','未连接'),row('演示钱包','只读','模拟','未连接')],action:'演示连接检查'},data:{title:'数据目录样例',columns:['数据集','样本量','更新频率','状态'],rows:[row(`${target.tab} · 数据快照`,'72 条','日频','模拟可用'),row('资金费率样例','24 条','8 小时','模拟可用'),row('数据质量检查','3 项','手动','待检查')],action:'检查演示数据'},more:{title:'工具使用样例',columns:['工具','用途','范围','状态'],rows:[row(target.tab,'功能演示','本地','可体验'),row('研究清单','整理资料','本地','待完成'),row('策略工作台','规则回放','跨页面','可体验')],action:'完成演示步骤'}};
 const special={
 R010:{title:'模拟订单簿',columns:['档位','价格','数量','方向'],rows:[row('买一',last.close.toFixed(2),'1.50','买盘'),row('买二',(last.close*.999).toFixed(2),'2.80','买盘'),row('卖一',(last.close*1.001).toFixed(2),'1.20','卖盘')],action:'标记深度档位'},
 R011:{title:'模拟资金流',columns:['时段','流入','流出','净流入'],rows:[row('09:00','120 万','80 万','+40 万'),row('10:00','90 万','110 万','−20 万'),row('11:00','150 万','70 万','+80 万')],action:'加入资金观察'},
 R012:{title:'模拟合约指标',columns:['指标','当前值','前值','状态'],rows:[row('资金费率','0.01%','0.008%','模拟'),row('持仓量','12.4 亿','12.0 亿','模拟'),row('多空比','1.15','1.08','模拟')],action:'关注指标'},
 R048:{title:'模拟盈亏日历',columns:['日期','已实现盈亏','成交数','状态'],rows:[row('2026-03-11','+120 USD','3','已复盘'),row('2026-03-12','−65 USD','2','待复盘'),row('2026-03-13','+80 USD','1','待复盘')],action:'标记复盘完成'},
 R049:{title:'模拟资金流水',columns:['记录','金额','类别','状态'],rows:[row('模拟入金','+1,000 USD','资金划转','已记录'),row('模拟买入','−500 USD','交易支出','已记录'),row('模拟手续费','−0.50 USD','费用','已记录')],action:'标记流水'},
 R050:{title:'模拟风险检查',columns:['规则','当前值','上限','状态'],rows:[row('单一资产集中度','50%','40%','超限'),row('日内亏损','1%','3%','正常'),row('杠杆倍数','1x','2x','正常')],action:'确认演示风险'},
 R052:{title:'模拟授权流程',columns:['步骤','权限','提交方式','状态'],rows:[row('选择服务','只读','本地演示','待选择'),row('检查权限','禁止提现','模拟校验','待检查'),row('验证连接','不提交密钥','模拟校验','待验证')],action:'完成演示步骤'},
 R053:{title:'模拟安全检查清单',columns:['检查项','建议','范围','状态'],rows:[row('提现权限','保持关闭','演示账户','已关闭'),row('自动执行','保持关闭','演示策略','已关闭'),row('凭证保存','本地安全存储','连接流程','待接入')],action:'确认安全说明'},
 R054:{title:'模拟储备快照',columns:['平台','储备规模','覆盖率','状态'],rows:[row('演示平台 A','1.2 亿 USD','105%','模拟数据'),row('演示平台 B','8,000 万 USD','102%','模拟数据'),row('演示平台 C','6,000 万 USD','98%','需关注')],action:'加入储备观察'},
 };
 return {...(special[target.code]||data[target.page==='strategy'?'home':target.page]),symbol,market:context.market,candles,source:'demo',asOf:'2026-03-13',scenario};
}
