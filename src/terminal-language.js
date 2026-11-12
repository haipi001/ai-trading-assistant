// Interface labels only. Research material, tickers, user text and evidence stay verbatim.
const labels={
'首页':'Home','AI智搜':'AI search','市场概览':'Market overview','条件选币':'Coin screener','热门榜单':'Trending','排行':'Rankings','功能指南':'Guide','云图':'Heatmap','合约雷达':'Derivatives radar','图表':'Chart','深度':'Depth','资金流':'Money flow','合约数据':'Derivatives','自选':'Watchlist','快讯':'Flash news','精选':'Featured','直播':'Live coverage','巨鲸':'Whales','主力':'Large traders','推特':'Twitter','市场':'Markets','上新':'Listings','链上':'Onchain','宏观':'Macro','币股':'Crypto equities','要闻':'News','分析':'Analysis','直播回顾':'Recaps','产品教程':'Tutorials','科普':'Education','长推':'Threads','媒体报道':'Media','行业报告':'Industry reports','策略':'Strategies','自动赚币':'Earn','套利机会':'Arbitrage opportunities','专业套利':'Professional arbitrage','我的套利':'My arbitrage','聪明钱':'Smart money','资产':'Assets','总览':'Overview','币种分布':'Asset allocation','API账号分布':'API account allocation','盈亏日历':'P&L calendar','流水':'Transactions','风控':'Risk control','API授权':'API authorization','已授权账户':'Authorized accounts','添加授权':'Add authorization','安全说明':'Security','数据':'Data','加密货币储备':'Crypto reserves','更多':'More','钱包':'Wallet','自定义导航':'Customize navigation','帮助中心':'Help center','条件选股':'Stock screener','热门股票':'Trending stocks','涨幅榜':'Top gainers','财经日历':'Economic calendar','板块热力':'Sector heatmap','财报雷达':'Earnings radar','我的策略':'My strategies','智能套利':'Smart arbitrage','全币种 DCA':'Multi-asset DCA','AI网格':'AI grid','指标策略':'Indicator strategies','主力追踪':'Large trader tracking','游资追踪':'Momentum tracking','订单表与最新成交':'Orders and recent trades','最新资讯':'Latest news','资金流向':'Money flow','技术分析':'Technical analysis','特色数据':'Special data','ETF数据':'ETF data','下单面板':'Order ticket','关闭':'Close','发送':'Send','取消':'Cancel','保存':'Save','确认':'Confirm','刷新':'Refresh','设置':'Settings','AI服务设置':'AI settings','选择模型':'Choose model','研究材料':'Research material','全部':'All','搜索':'Search','买入':'Buy','卖出':'Sell','数量':'Quantity','价格':'Price','可用余额':'Available balance','只读':'Read only'
};
Object.assign(labels,{'AI 交易助手':'AI trading assistant','关闭工具面板':'Close tool panel','进入研究对话':'Open research chat','配置 AI 服务':'Configure AI service','侧栏布局':'Sidebar layout','经典侧栏':'Classic sidebar','专业侧栏':'Professional sidebar','系统设置':'System settings','通用':'General','后端会话':'Backend session','AI服务':'AI service','资讯服务':'News services','工作区同步':'Workspace sync','恢复默认':'Restore defaults','恢复默认设置':'Restore default settings','配置':'Configure','连接':'Connect','断开连接':'Disconnect','退出登录':'Sign out','登录':'Sign in','查看详情':'View details','暂无数据':'No data','创建我的策略':'Create my strategy','主题':'Theme','浅色':'Light','深色':'Dark','跟随系统':'System','软件缩放':'Interface scale','输入问题，Enter 发送…':'Ask a question, press Enter to send…'});
Object.assign(labels,{'查看报告全文与记录来源':'Read report and recorded sources','支持情景':'Supporting scenario','反对情景':'Opposing scenario','关键风险':'Key risks','报告建议':'Report suggestion','局限与未知项':'Limitations and unknowns','报告输入记录':'Recorded report inputs','来源与引用记录':'Recorded sources and citations','审阅报告与投资假设':'Review report against thesis','保存人工审阅，不创建订单':'Save human review','保存复盘笔记':'Save review notes','保存并确认完成复盘':'Save and mark review complete'});
Object.assign(labels,{'创建人工投资假设':'Create a human investment thesis','原始理由':'Original rationale','驱动因素（每行一项）':'Key drivers (one per line)','失效条件（每行一项）':'Invalidation conditions (one per line)','预期持有期限':'Expected holding horizon','目标或重新评估条件':'Target or reassessment condition','最大损失容忍度（%）':'Maximum loss tolerance (%)','主观判断强度（0至1）':'Subjective confidence (0 to 1)','保存人工假设，不创建订单':'Save human thesis'});
Object.assign(labels,{'读取此成交的AI复盘材料':'Read AI review material for this fill','核对冻结的复盘材料':'Inspect frozen review material','查看原始复盘记录':'Inspect original review record','模拟成交记录':'Paper fill record','原始订单理由':'Original order rationale','已保存的复盘记录':'Saved review record','交易日志':'Trade journal','历史门禁记录':'Historical decision gates'});
Object.assign(labels,{'准备AI复盘问题':'Prepare an AI review question','已准备的Paper复盘材料':'Prepared Paper review material','附带此成交的Paper复盘材料':'Include this Paper fill review material','本次Paper复盘来源':'Paper review sources for this reply','已保存的Paper AI复盘':'Saved Paper AI reviews','读取此成交的AI复盘历史':'Read AI review history for this fill'});
Object.assign(labels,{'取消此复盘准备，转为手动提问':'Clear Paper preparation and ask manually'});
let language='zh',observer,observedRoot;
const attributeOriginals=new WeakMap();
const originals=new WeakMap();
function render(){
 const root=document.getElementById('feature-root');if(!root)return;
 // Restrict translation to interface controls, never article bodies, prompts or evidence.
 for(const el of root.querySelectorAll('.pagebar,.channel-title,.floating-ai>header,.ace-agent-dock>nav,.drawer>header,.drawer>nav,.market-side-embedded>header,.market-side-embedded>nav,button,label,th,[data-terminal-label]')){
  const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let node;
  while(node=walker.nextNode()){
   if(node.parentElement.closest('pre,textarea,input,[contenteditable]'))continue;
   const current=node.textContent.trim();let original=originals.get(node);
   if(!original||![original,labels[original]].includes(current)){original=current;originals.set(node,original);}
   if(!labels[original])continue;
   const value=language==='en'?labels[original]:original;
   if(current!==value)node.textContent=node.textContent.replace(current,value);
  }
 }
 for(const element of root.querySelectorAll('[aria-label],[title],input[placeholder],textarea[placeholder]')){
  let saved=attributeOriginals.get(element);if(!saved){saved={};attributeOriginals.set(element,saved);}
  for(const name of ['aria-label','title','placeholder']){
   const current=element.getAttribute(name);if(!current)continue;
   let original=saved[name];if(!original||![original,labels[original]].includes(current))original=saved[name]=current;
   if(labels[original]){const value=language==='en'?labels[original]:original;if(current!==value)element.setAttribute(name,value);}
  }
 }
}
export function applyTerminalLanguage(value){
 language=value==='en'?'en':'zh';document.documentElement.lang=language==='en'?'en':'zh-CN';render();
 const root=document.getElementById('feature-root');
 if(root!==observedRoot){
  observer?.disconnect();observedRoot=root;
  if(root){observer??=new MutationObserver(render);observer.observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-label','title','placeholder']});}
 }
}
