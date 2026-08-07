import React, { useMemo, useState } from "react";
import * as I from "@phosphor-icons/react";

export const UTILITY_TOOL_TITLES = [
  "地址簿", "钱包监控", "授权检测", "Gas 追踪", "网络节点", "资产快照",
  "经济日历", "全球指数", "利率与汇率", "美股行情", "黄金原油", "市场情绪",
  "新手教程", "快捷键", "联系客服", "意见反馈", "检查更新", "关于 AI交易助手",
];

const walletTools = new Set(UTILITY_TOOL_TITLES.slice(0, 6));
const macroTools = new Set(UTILITY_TOOL_TITLES.slice(6, 12));

function ToolHeader({ title, description }) {
  return <div className="utility-head"><span><I.Wrench /></span><div><h3>{title}</h3><p>{description}</p></div></div>;
}

function ToolTable({ heads, rows, action }) {
  return <div className={`utility-table columns-${heads.length}`}><header>{heads.map((x)=><b key={x}>{x}</b>)}</header>{rows.map((row,index)=><div key={`${row[0]}-${index}`}>{row.map((value)=><span key={value}>{value}</span>)}{action ? action(row,index) : null}</div>)}</div>;
}

export function UtilityToolPanel({ model, close, say, go }) {
  const title = model.title;
  const [query, setQuery] = useState("");
  const [secondary, setSecondary] = useState("");
  const [network, setNetwork] = useState("Ethereum");
  const [status, setStatus] = useState("idle");
  const [enabled, setEnabled] = useState(true);
  const [records, setRecords] = useState([]);
  const [selected, setSelected] = useState("全部");
  const finish = (message) => { say(message); close(); };
  const addRecord = (record) => {
    if (!query.trim()) return say("请填写有效内容");
    setRecords([...records, record]);
    setQuery("");
    setSecondary("");
  };
  const macroRows = useMemo(() => ({
    经济日历: [["20:30","美国初请失业金人数","高","预测 23.5万"],["22:00","美国成屋销售","中","预测 4.01M"],["明日 02:00","美联储褐皮书","高","待公布"]],
    全球指数: [["标普500","6,248.56","-0.41%"],["纳斯达克","20,630.67","-0.52%"],["恒生指数","24,825.66","+0.68%"],["美元指数","98.42","+0.16%"]],
    美股行情: [["MSTR","412.68","-2.14%"],["COIN","389.20","+1.82%"],["NVDA","172.41","-0.38%"],["TSLA","329.65","+0.74%"]],
    黄金原油: [["现货黄金","3,337.40","+0.32%"],["COMEX黄金","3,346.10","+0.29%"],["WTI原油","65.24","-0.81%"],["布伦特原油","68.58","-0.62%"]],
  })[title] || [], [title]);

  if (title === "地址簿") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="管理常用链上地址和本地备注，不上传到服务器。"/><div className="utility-form two"><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="钱包地址 0x…"/><input value={secondary} onChange={(e)=>setSecondary(e.target.value)} placeholder="备注，例如 冷钱包"/><button onClick={()=>addRecord([secondary || "未命名",query,"Ethereum"])}>添加地址</button></div>{records.length?<ToolTable heads={["备注","地址","网络",""]} rows={records} action={(_,i)=><button onClick={()=>setRecords(records.filter((__,index)=>index!==i))}>删除</button>}/>:<div className="utility-empty"><I.AddressBook/><b>暂无地址</b><small>添加后可用于转账校验和钱包监控</small></div>}</div>;

  if (title === "钱包监控") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="跟踪地址余额和大额转账，本演示使用本地事件。"/><div className="utility-form"><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="输入钱包地址"/><button onClick={()=>addRecord([query,"$2.84M","刚刚","正常"])}>开始监控</button></div>{records.length?<ToolTable heads={["地址","资产","更新","状态"]} rows={records}/>:<div className="utility-empty"><I.Eye/><b>尚未监控钱包</b></div>}<label className="utility-switch"><input type="checkbox" checked={enabled} onChange={(e)=>setEnabled(e.target.checked)}/>大额转账桌面提醒</label></div>;

  if (title === "授权检测") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="检查钱包授权范围并识别高风险无限额度授权。"/><div className="utility-form"><input value={query} onChange={(e)=>{setQuery(e.target.value);setStatus("idle")}} placeholder="输入 EVM 钱包地址"/><button onClick={()=>{if(!query.trim())return say("请输入钱包地址");setStatus("done")}}>开始检测</button></div>{["done","revoked"].includes(status)?<><div className="utility-score"><I.ShieldCheck/><span><b>安全评分 {status==="revoked"?"98":"86"}</b><small>{status==="revoked"?"风险授权已处理":"发现 1 项需要关注"}</small></span></div><ToolTable heads={["协议","权限","风险"]} rows={status==="revoked"?[["Uniswap","USDT 限额","低"]]:[["Uniswap","USDT 限额","低"],["Unknown dApp","USDC 无限额度","高"]]}/><button className="overlay-primary" disabled={status==="revoked"} onClick={()=>setStatus("revoked")}>{status==="revoked"?"风险授权已撤销":"模拟撤销风险授权"}</button></>:<div className="utility-empty"><I.ShieldCheck/><b>输入地址开始安全检测</b></div>}</div>;

  if (title === "Gas 追踪") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="查看主流网络 Gas 并设置低价提醒。"/><div className="feature-tabs">{["Ethereum","Arbitrum","Base"].map((x)=><button className={network===x?"on":""} key={x} onClick={()=>setNetwork(x)}>{x}</button>)}</div><div className="gas-cards"><article><small>慢速</small><b>3.2 Gwei</b><em>≈ $0.18</em></article><article><small>标准</small><b>4.1 Gwei</b><em>≈ $0.24</em></article><article><small>快速</small><b>5.8 Gwei</b><em>≈ $0.34</em></article></div><label>低于多少时提醒<input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="例如 3 Gwei"/></label><button className="overlay-primary" onClick={()=>query?finish(`${network} Gas 提醒已保存`):say("请输入提醒阈值")}>保存提醒</button></div>;

  if (title === "网络节点") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="选择行情和链上数据节点，比较实时延迟。"/><select value={network} onChange={(e)=>setNetwork(e.target.value)}><option>Ethereum</option><option>Bitcoin</option><option>Solana</option></select><ToolTable heads={["节点","区域","延迟","状态"]} rows={[[`${network} Main RPC`,"新加坡","42ms","正常"],[`${network} Backup RPC`,"东京","68ms","正常"],[`${network} Archive`,"美国","186ms","较慢"]]}/><button className="overlay-primary" onClick={()=>{setStatus("refreshed");say("节点延迟已刷新")}}>{status==="refreshed"?"已刷新":"重新测速"}</button></div>;

  if (title === "资产快照") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="生成当前账户资产的本地只读快照。"/><div className="snapshot-summary"><span><small>快照时间</small><b>{new Date().toLocaleString("zh-CN")}</b></span><span><small>账户数</small><b>3</b></span><span><small>估值</small><b>12,846.32 USDT</b></span></div><ToolTable heads={["资产","数量","折合"]} rows={[["USDT","8,420.18","$8,420.18"],["BTC","0.0521","$3,426.14"],["ETH","0.314","$999.98"]]}/><button className="overlay-primary" onClick={()=>finish("资产快照已保存到本地记录")}>保存快照</button></div>;

  if (["经济日历","全球指数","美股行情","黄金原油"].includes(title)) return <div className="feature-panel utility-panel"><ToolHeader title={title} description="聚合宏观与传统市场数据，作为加密市场研判参考。"/><div className="utility-filter"><div>{["全部","重要","已关注"].map((x)=><button className={selected===x?"on":""} key={x} onClick={()=>setSelected(x)}>{x}</button>)}</div><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="搜索"/></div><ToolTable heads={title==="经济日历"?["时间","事件","重要性","数据"]:["标的","最新","涨跌"]} rows={macroRows.filter((row)=>row.join(" ").toLowerCase().includes(query.toLowerCase()))}/><footer className="feature-actions"><button onClick={()=>{close();go(title==="经济日历"?"data":"market")}}>打开关联页面</button><button className="overlay-primary" onClick={()=>finish(`${title}关注条件已保存`)}>保存关注</button></footer></div>;

  if (title === "利率与汇率") { const converted=(Number(query)||0)*7.18; return <div className="feature-panel utility-panel"><ToolHeader title={title} description="查看主要利率并进行本地汇率换算。"/><div className="rate-strip"><span><small>美联储目标利率</small><b>4.25%–4.50%</b></span><span><small>美国10Y</small><b>4.42%</b></span><span><small>美元指数</small><b>98.42</b></span></div><div className="convert-box"><label>USD<input type="number" value={query} onChange={(e)=>setQuery(e.target.value)}/></label><I.ArrowRight/><label>CNY<input value={converted?converted.toFixed(2):""} readOnly/></label></div></div>; }

  if (title === "市场情绪") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="综合恐惧贪婪、波动率、资金流和社交热度。"/><div className="sentiment-gauge"><i/><strong>40</strong><b>中性</b></div><div className="sentiment-bars">{[["恐惧贪婪",40],["资金流",62],["波动率",71],["社交热度",56]].map(([x,v])=><p key={x}><span>{x}</span><i><em style={{width:`${v}%`}}/></i><b>{v}</b></p>)}</div><button className="overlay-primary" onClick={()=>finish("市场情绪已加入首页关注")}>加入首页</button></div>;

  if (title === "新手教程") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="从行情阅读到策略模拟的桌面端入门路径。"/><div className="tutorial-steps">{["认识工作区","添加自选","阅读K线","运行模拟策略"].map((x,i)=><button className={selected===x?"on":""} key={x} onClick={()=>setSelected(x)}><i>{i+1}</i><span><b>{x}</b><small>{selected===x?"当前学习步骤":"点击查看"}</small></span><I.CaretRight/></button>)}</div>{selected!=="全部"&&<div className="tutorial-detail"><b>{selected}</b><p>按照页面中的高亮入口完成操作；所有交易步骤默认只生成本地模拟结果。</p><button onClick={()=>{close();go(selected==="添加自选"||selected==="阅读K线"?"market":"strategy")}}>开始练习</button></div>}</div>;

  if (title === "快捷键") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="桌面工作区快捷操作一览。"/><ToolTable heads={["快捷键","功能"]} rows={[["/","聚焦全局搜索"],["Esc","关闭弹层或清空搜索"],["⌘ K","打开命令搜索"],["⌘ S","保存当前布局"],["Space","复盘播放/暂停"]]}/><label className="utility-switch"><input type="checkbox" checked={enabled} onChange={(e)=>setEnabled(e.target.checked)}/>启用单键图表快捷键</label></div>;

  if (title === "联系客服" || title === "意见反馈") return <div className="feature-panel utility-panel"><ToolHeader title={title} description={title==="联系客服"?"提交本地客服工单，保留问题和界面上下文。":"告诉我们当前界面中仍需改进的地方。"}/><label>问题类型<select value={selected} onChange={(e)=>setSelected(e.target.value)}><option>功能问题</option><option>数据问题</option><option>界面建议</option></select></label><label>问题描述<textarea value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="请描述遇到的问题"/></label><label>联系方式（可选）<input value={secondary} onChange={(e)=>setSecondary(e.target.value)} placeholder="仅保存在本地演示"/></label><button className="overlay-primary" onClick={()=>query.trim().length>=5?finish(`${title}内容已保存到本地工单`):say("请至少输入 5 个字")}>提交</button></div>;

  if (title === "检查更新") return <div className="feature-panel utility-panel"><ToolHeader title={title} description="检查服务版本和资源更新状态。"/><div className="update-card"><I.CheckCircle/><span><b>{status==="done"?"当前已是最新版本":"AI交易助手 2.16.10"}</b><small>{status==="done"?"检查于刚刚":"上次检查：今天 18:30"}</small></span></div><button className="overlay-primary" onClick={()=>setStatus("done")}>{status==="done"?"已是最新版":"立即检查"}</button></div>;

  return <div className="feature-panel utility-panel"><ToolHeader title="关于 AI交易助手" description="行情、数据、策略和资产一体化交易工作台。"/><div className="about-brand"><b>AI</b><span><h2>AI交易助手</h2><p>Version 2.16.10 · Professional</p></span></div><ToolTable heads={["项目","信息"]} rows={[["运行模式","在线服务"],["交易能力","默认模拟，不自动提交真实订单"],["数据来源","交易系统后端 / 演示回退"],["产品范围","核心行情与交易工具"]]}/><button onClick={close}>关闭</button></div>;
}
