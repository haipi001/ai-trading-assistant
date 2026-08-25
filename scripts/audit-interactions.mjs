import fs from "node:fs";
import process from "node:process";
import { parse } from "@babel/parser";

const sourceFiles = [
  "../src/main.jsx",
  "../src/market-workbench.jsx",
  "../src/feature-overlays.jsx",
  "../src/utility-tools.jsx",
  "../src/trading-chart.jsx",
  "../src/strategy-intelligence.jsx",
  "../src/chart-command-centers.jsx",
];
const sources = sourceFiles.map((file) =>
  fs.readFileSync(new URL(file, import.meta.url), "utf8"),
);
const source = sources.join("\n");
const failures = [];
let buttons = 0;
let handlers = 0;
let mappedElements = 0;
let formControls = 0;
let formHandlers = 0;
const metaTabs = {};
const featureOverlayTypes = [];
const utilityToolTitles = [];

function returnedJsx(node) {
  if (!node) return null;
  if (node.type === "JSXElement") return node;
  if (node.type === "ParenthesizedExpression")
    return returnedJsx(node.expression);
  return null;
}

function walk(node) {
  if (!node || typeof node !== "object") return;
  if (
    node.type === "VariableDeclarator" &&
    node.id?.name === "META" &&
    node.init?.type === "ObjectExpression"
  ) {
    for (const pageProperty of node.init.properties) {
      const pageName = pageProperty.key?.name || pageProperty.key?.value;
      const tabsProperty = pageProperty.value?.properties?.find(
        (property) => (property.key?.name || property.key?.value) === "tabs",
      );
      if (tabsProperty?.value?.type === "ArrayExpression") {
        metaTabs[pageName] = tabsProperty.value.elements.map(
          (element) => element?.value,
        );
      }
    }
  }
  if (
    node.type === "VariableDeclarator" &&
    node.id?.name === "FEATURE_OVERLAY_TYPES" &&
    node.init?.type === "ArrayExpression"
  ) {
    featureOverlayTypes.push(...node.init.elements.map((element) => element?.value));
  }
  if (
    node.type === "VariableDeclarator" &&
    node.id?.name === "UTILITY_TOOL_TITLES" &&
    node.init?.type === "ArrayExpression"
  ) {
    utilityToolTitles.push(...node.init.elements.map((element) => element?.value));
  }
  if (node.type === "JSXOpeningElement" && node.name?.name === "button") {
    buttons += 1;
    const handler = node.attributes.find(
      (attr) => attr.type === "JSXAttribute" && attr.name?.name === "onClick",
    );
    if (!handler) {
      failures.push(`Button without onClick at line ${node.loc.start.line}`);
    } else {
      handlers += 1;
      const expression = handler.value?.expression;
      if (
        expression?.type === "ArrowFunctionExpression" &&
        expression.body?.type === "BlockStatement" &&
        expression.body.body.length === 0
      ) {
        failures.push(
          `Button with empty onClick at line ${node.loc.start.line}`,
        );
      }
    }
  }
  if (
    node.type === "JSXOpeningElement" &&
    ["input", "textarea", "select"].includes(node.name?.name)
  ) {
    formControls += 1;
    const readOnly = node.attributes.some(
      (attr) => attr.type === "JSXAttribute" && attr.name?.name === "readOnly",
    );
    const controlled = node.attributes.some(
      (attr) => attr.type === "JSXAttribute" && attr.name?.name === "value",
    );
    const handler = node.attributes.find(
      (attr) => attr.type === "JSXAttribute" && attr.name?.name === "onChange",
    );
    if (readOnly || !controlled) {
      formHandlers += 1;
    } else if (!handler) {
      failures.push(
        `${node.name.name} without onChange at line ${node.loc.start.line}`,
      );
    } else {
      formHandlers += 1;
      const expression = handler.value?.expression;
      if (
        expression?.type === "ArrowFunctionExpression" &&
        expression.body?.type === "BlockStatement" &&
        expression.body.body.length === 0
      ) {
        failures.push(
          `${node.name.name} with empty onChange at line ${node.loc.start.line}`,
        );
      }
    }
  }
  if (
    node.type === "CallExpression" &&
    node.callee?.type === "MemberExpression" &&
    node.callee.property?.name === "map"
  ) {
    const callback = node.arguments[0];
    if (
      callback?.type === "ArrowFunctionExpression" ||
      callback?.type === "FunctionExpression"
    ) {
      let body = callback.body;
      if (body.type === "BlockStatement") {
        body = body.body.find(
          (item) => item.type === "ReturnStatement",
        )?.argument;
      }
      const jsx = returnedJsx(body);
      if (jsx) {
        mappedElements += 1;
        const hasKey = jsx.openingElement.attributes.some(
          (attr) => attr.type === "JSXAttribute" && attr.name?.name === "key",
        );
        if (!hasKey)
          failures.push(`Mapped JSX without key at line ${jsx.loc.start.line}`);
      }
    }
  }
  if (
    node.type === "CallExpression" &&
    node.callee?.type === "MemberExpression" &&
    node.callee.object?.name === "Array" &&
    node.callee.property?.name === "from"
  ) {
    const callback = node.arguments[1];
    if (callback?.type === "ArrowFunctionExpression") {
      const jsx = returnedJsx(callback.body);
      if (jsx) {
        mappedElements += 1;
        const hasKey = jsx.openingElement.attributes.some(
          (attr) => attr.type === "JSXAttribute" && attr.name?.name === "key",
        );
        if (!hasKey)
          failures.push(
            `Array.from JSX without key at line ${jsx.loc.start.line}`,
          );
      }
    }
  }
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === "object" && value.type) walk(value);
  }
}

for (const currentSource of sources) {
  walk(parse(currentSource, { sourceType: "module", plugins: ["jsx"] }));
}

const requiredPages = [
  "首页",
  "行情",
  "快讯",
  "要闻",
  "策略",
  "链上",
  "资产",
  "授权",
  "数据",
  "更多",
];
for (const page of requiredPages) {
  if (!source.includes(`"${page}"`)) failures.push(`Missing page: ${page}`);
}

const expectedChannelCounts = {
  home: 8,
  market: 5,
  flash: 12,
  news: 12,
  strategy: 5,
  chain: 3,
  assets: 6,
  auth: 3,
  data: 2,
  more: 4,
};
for (const [page, expected] of Object.entries(expectedChannelCounts)) {
  const actual = metaTabs[page]?.length || 0;
  if (actual !== expected)
    failures.push(
      `Page ${page} has ${actual} top channels; expected ${expected}`,
    );
}
const totalChannels = Object.values(metaTabs).reduce(
  (sum, tabs) => sum + tabs.length,
  0,
);
if (totalChannels !== 60)
  failures.push(`META contains ${totalChannels} channels; expected 60`);

for (const component of [
  "Home",
  "Market",
  "FlashPage",
  "News",
  "Strategy",
  "ChainPage",
  "Assets",
  "Auth",
  "DataPage",
  "MorePage",
]) {
  if (!source.includes(`<${component} {...ctx} />`))
    failures.push(`Missing primary content route: ${component}`);
}

const requiredTopTabs = [
  "Ace智搜",
  "市场概览",
  "条件选币",
  "热门榜单",
  "排行",
  "功能指南",
  "云图",
  "合约雷达",
  "图表",
  "深度",
  "资金流",
  "合约数据",
  "自选",
  "直播",
  "巨鲸",
  "主力",
  "推特",
  "特朗普",
  "上新",
  "ETF",
  "活动FUN放",
  "分析",
  "直播回顾",
  "产品教程",
  "科普",
  "长推",
  "媒体报道",
  "Web3.0",
  "行业报告",
  "AI号",
  "自动赚币",
  "套利机会",
  "专业套利",
  "我的套利",
  "聪明钱",
  "Hyperliquid",
  "Polymarket",
  "总览",
  "币种分布",
  "API账号分布",
  "盈亏日历",
  "流水",
  "风控",
  "已授权账户",
  "添加授权",
  "安全说明",
  "加密货币储备",
  "钱包",
  "宏观",
  "自定义导航",
  "帮助中心",
];
for (const tab of requiredTopTabs) {
  if (!source.includes(`"${tab}"`)) failures.push(`Missing top tab: ${tab}`);
}

for (const flow of ["strategyCreate", "addGroup", "apiAuth", "automationCreate"]) {
  if (!source.includes(`model.type === "${flow}"`) && !featureOverlayTypes.includes(flow))
    failures.push(`Missing complete flow: ${flow}`);
}

const openedOverlayTypes = new Set(
  [...source.matchAll(/(?:openOverlay|open)\("([^"]+)"/g)].map((match) => match[1]),
);
const directlyHandledOverlayTypes = new Set(
  [...source.matchAll(/model\.type === "([^"]+)"/g)].map((match) => match[1]),
);
for (const type of featureOverlayTypes) directlyHandledOverlayTypes.add(type);
for (const type of openedOverlayTypes) {
  if (!directlyHandledOverlayTypes.has(type))
    failures.push(`Overlay ${type} falls through to the generic result panel`);
}

for (const workflowContract of [
  "生成策略草稿",
  "添加到对话",
  "K线范围已切换为",
  "组合订单模拟校验通过",
  "保存跟单方案",
  "生成预览",
  "提交审核",
  "完成分享",
  "打开关联页面",
]) {
  if (!source.includes(workflowContract))
    failures.push(`Missing workflow outcome: ${workflowContract}`);
}

const requiredUtilityTools = [
  "地址簿", "钱包监控", "授权检测", "Gas 追踪", "网络节点", "资产快照",
  "经济日历", "全球指数", "利率与汇率", "美股行情", "黄金原油", "市场情绪",
  "新手教程", "快捷键", "联系客服", "意见反馈", "检查更新", "关于 AI交易助手",
];
for (const title of requiredUtilityTools) {
  if (!utilityToolTitles.includes(title))
    failures.push(`Utility tool lacks a dedicated panel: ${title}`);
}
if (new Set(utilityToolTitles).size !== requiredUtilityTools.length)
  failures.push(`Utility tool manifest has ${new Set(utilityToolTitles).size} entries; expected ${requiredUtilityTools.length}`);

for (const marketWorkbench of [
  "委单区",
  "自定义指标/回测/实盘",
  "AI网格",
  "现货DCA",
  "合约DCA",
  "组合下单",
  "跟单面板",
  "AI分析",
  "交易历史",
]) {
  if (!source.includes(`"${marketWorkbench}"`))
    failures.push(`Missing market workbench: ${marketWorkbench}`);
}

for (const marketSubpage of [
  "现货仓位(0)",
  "当前委托(0)",
  "策略(0)",
  "历史委托",
  "买卖记录",
  "账户资产",
  "预估清算图",
  "深度图",
  "技术分析",
  "主力",
  "指标编辑",
  "指标选币",
  "策略回测",
  "实盘运行 (0/30)",
  "实盘历史",
  "创建网格",
  "运行中",
  "历史策略",
  "创建DCA",
  "成交记录",
  "策略执行",
  "资金费用",
  "策略广场",
  "我的跟单",
  "跟单历史",
]) {
  if (!source.includes(`"${marketSubpage}"`))
    failures.push(`Missing market subpage: ${marketSubpage}`);
}

for (const marketWorkflow of [
  "dynamic-group-form",
  'setBacktestStatus("running")',
  "backtest-history-table",
  "请先完成收益测算",
  "图表布局已切换为",
  "K线已切换到",
  "首次保证金需不少于20 USDT",
  "请先完成风险测算",
  "已生成本地导出记录",
  'useLocalState("ai-trading-assistant-grid-strategies"',
  'useLocalState("ai-trading-assistant-spot-dca-strategies"',
  'useLocalState("ai-trading-assistant-futures-dca-strategies"',
  'useLocalState("ai-trading-assistant-indicator-live-strategies"',
  'venue === "DEX" ? "ai-trading-assistant-dex-copy-subscriptions" : "ai-trading-assistant-copy-subscriptions"',
  'export function StrategyProductWorkbench',
  'venue="CEX"',
  'venue="DEX"',
  'status: "已终止"',
  'status: item.status === "运行中" ? "已暂停" : "运行中"',
  '网格本地模拟策略已创建',
  '现货DCA本地模拟策略已创建',
  '合约DCA本地模拟策略已创建',
  '指标本地模拟实盘已创建',
  '本地模拟跟单已启动',
  '已终止并归档',
  '重新创建为本地模拟策略',
]) {
  if (!source.includes(marketWorkflow))
    failures.push(`Missing market workflow state: ${marketWorkflow}`);
}

for (const replayContract of [
  "KlineReplayPanel",
  "K线复盘训练",
  "选择起始时间",
  "重新选择起点",
  "简洁模式",
  "持仓模式",
  "模拟买入",
  "模拟卖出",
  "复盘训练结果",
  "不会启用实盘交易",
]) {
  if (!source.includes(replayContract))
    failures.push(`Missing K-line replay contract: ${replayContract}`);
}

for (const completionContract of [
  "AI指标助手",
  "AI生成代码已写入指标编辑器",
  "AI 解读分享卡片已生成",
  "关键支撑与阻力已添加到本地图表",
  "风险受控模拟订单草稿",
  "strategy-batchbar",
  "批量暂停",
  "批量恢复",
  "批量终止",
  "订单详情",
  "收益概览",
  "当前委托",
  "成交记录",
  "策略参数",
  "模拟运行异常",
  "检查并恢复",
]) {
  if (!source.includes(completionContract))
    failures.push(`Missing recommended completion contract: ${completionContract}`);
}

for (const tradingChartContract of [
  "TradingChartGrid",
  "createChart",
  "CandlestickSeries",
  "HistogramSeries",
  "LineSeries",
  "CrosshairMode.Normal",
  "mouseWheel: true",
  "pressedMouseMove: true",
  'layout === "双窗"',
  'layout === "四窗"',
  "TradingView K线绘图区",
  "美股合约",
  "Hyperliquid",
]) {
  if (!source.includes(tradingChartContract))
    failures.push(`Missing TradingView market contract: ${tradingChartContract}`);
}

for (const completeMarketControlContract of [
  '"六窗"',
  '"九窗"',
  'studies.includes("网格线")',
  'studies.includes("价格线")',
  'studies.includes("买卖信号")',
  'studies.includes("委托线")',
  'studies.includes("持仓成本线")',
  'studies.includes("筹码分布")',
  'studies.includes("大额成交")',
  'studies.includes("主力大单")',
  'studies.includes("主力挂单统计")',
  'studies.includes("指标胜率")',
  'replayMode ? all.slice',
  'model.onApplyDate?.(date)',
  'venue={marketPlatform}',
  'quoteOverride={quote}',
  'layout === "六窗"',
  'layout === "九窗"',
  'aria-label="图表类型"',
  '"空心蜡烛"',
  '"折线图"',
  '"面积图"',
  '个K线窗口周期',
  'onPanePeriodChange?.(index,value)',
  'ai-trading-assistant-prefill-order',
  '在此价格添加预警',
  '限价买入',
  '限价卖出',
  '从此开始K线复盘',
  '重置图表视图',
  '清除全部绘图',
  'showDepthBars',
  'redUp: settings.redUp',
  'function indicatorSnapshot',
  'function emaValues',
]) {
  if (!source.includes(completeMarketControlContract))
    failures.push(`Missing complete market control contract: ${completeMarketControlContract}`);
}

for (const chartLayoutContract of [
  'useStoredState("ai-trading-assistant-chart-tabs"',
  'aria-label="新增图表标签页"',
  '至少保留一个图表标签页',
  '当前图表标签页已保存',
  'className="chart-layout-bar"',
]) {
  if (!source.includes(chartLayoutContract))
    failures.push(`Missing chart layout tab workflow: ${chartLayoutContract}`);
}

for (const drawingContract of [
  'useStoredState("ai-trading-assistant-chart-drawings"',
  'aria-label="K线绘图区"',
  'className="chart-drawing-layer"',
  'drawing.type === "趋势线"',
  'drawing.type === "水平线"',
  'drawing.type === "平行线"',
  'drawing.type === "测量"',
  'drawing.type === "矩形"',
  'drawing.type === "文本"',
  'drawing.type === "斐波那契"',
  'drawing.type === "画笔"',
  'setDrawingRedo([drawings, ...drawingRedo])',
  'setDrawingHistory([...drawingHistory, drawings])',
  '磁吸模式已',
  '图表画线已',
  '已删除 ${drawings.length} 个图表对象',
]) {
  if (!source.includes(drawingContract))
    failures.push(`Missing real chart drawing contract: ${drawingContract}`);
}

for (const quickTradeContract of [
  'useStoredState("ai-trading-assistant-quick-orders"',
  'useState("限价")',
  '["限价", "市价"]',
  'aria-label="快捷交易价格"',
  'aria-label="快捷交易数量"',
  'status: tradeOrderType === "市价" ? "模拟成交" : "等待成交"',
  '本地模拟委托已清空',
  '模拟委托已撤销',
]) {
  if (!source.includes(quickTradeContract))
    failures.push(`Missing quick trade lifecycle contract: ${quickTradeContract}`);
}

for (const arbitrageContract of [
  'useStoredState("ai-trading-assistant-arb-favorites"',
  'aria-label="套利平台筛选"',
  'aria-label="套利合约筛选"',
  'setCategory(1)',
  'tab === "自动赚币"',
  'tab === "专业套利"',
  'tab === "我的套利"',
  'useStoredState("ai-trading-assistant-arb-combinations"',
  'useStoredState("ai-trading-assistant-professional-arb-orders"',
  'aria-label="自动赚币平台筛选"',
  'aria-label="专业套利下单金额"',
  '模拟双腿下单',
  'arbType === "收藏"',
  'arbType === "反向套利"',
  'arbType === "跨所永续"',
  'arbType === "永续-期货"',
  'arbType === "价差-期现"',
  '暂无收藏的套利机会',
  '套利已收藏',
  '套利已取消收藏',
]) {
  if (!source.includes(arbitrageContract))
    failures.push(`Missing arbitrage navigation/filter contract: ${arbitrageContract}`);
}

for (const marketChannelContract of [
  'useState("累计深度")',
  '["累计深度", "增量深度"]',
  '["0.01%", "0.1%", "0.5%", "1%"]',
  'tab === "资金流" ? ["净流入", "大单", "主力"]',
  'tab === "合约数据" && platform !== "全部平台"',
  'coins.filter((x)=>watch.includes(x[0]))',
  'openOverlay("addWatch","管理自选")',
  'AI 深度解读',
  'AI 资金流解读',
]) {
  if (!source.includes(marketChannelContract))
    failures.push(`Missing market channel contract: ${marketChannelContract}`);
}

for (const rightRailContract of [
  '["depth", "订单表与最新成交", I.ListNumbers]',
  '["news", "最新资讯", I.Newspaper]',
  '["funds", "资金流向", I.Money]',
  'type === "analysis"',
  '["feature", "特色数据", I.ChartBar]',
  '["etf", "ETF数据", I.Bank]',
  '["ai", "Ace Agent", I.Robot]',
  'type === "depth"',
  'type === "feature"',
  'type === "news"',
  'aria-label="下单面板"',
  'aria-label="侧栏布局"',
  'aria-label="联系客服"',
  'aria-label="AI智能分析"',
  '"classic"',
  '"professional"',
  '"下单", "抢新开盘", "特色"',
  '"多账户下单", "多号同步"',
  '"三键下单", "短线提速"',
  '"智能拆单", "降低滑点"',
  '综合技术评分',
  '最新成交',
  '交易所净流入',
  '自选相关',
]) {
  if (!source.includes(rightRailContract))
    failures.push(`Missing original market right-rail contract: ${rightRailContract}`);
}

for (const chainChartContract of [
  '"ai-trading-assistant-followed-traders"',
  '"ai-trading-assistant-chart-traders"',
  'className="chart-trader-strip"',
  'className={`trader-marker ${trader.side === "卖出" ? "sell" : "buy"}`}',
  'trackedTraders={chartTraders.filter((trader) => trader.symbol === symbol)}',
  '查看已上K线 ({chartTraders.length})',
  '已显示到 ${x[5]} K线',
  '已清空K线交易员轨迹',
  '从K线移除${trader.name}',
]) {
  if (!source.includes(chainChartContract))
    failures.push(`Missing chain-to-chart persistence contract: ${chainChartContract}`);
}

for (const topMarketToolbarContract of [
  '"ai-trading-assistant-chart-snapshots"',
  'onMarketAction={(type) => setMarketCommand({ type, id: Date.now() })}',
  'marketCommand.type === "snapshot"',
  'marketCommand.type === "saveLayout"',
  'source = "图表工具栏"',
  'drawingCount: drawings.length',
  'studies: [...studies]',
  'openOverlay("chartSnapshots", "行情快照记录"',
  'onRestoreSnapshot: (snapshot)',
  'onDeleteSnapshot: (id)',
  'onClearSnapshots: () => setChartSnapshots([])',
  'model.type === "chartSnapshots"',
  '应用到图表',
  '行情快照记录已清空',
]) {
  if (!source.includes(topMarketToolbarContract))
    failures.push(`Missing real top market toolbar contract: ${topMarketToolbarContract}`);
}

for (const marketSymbolContract of [
  'useStoredState("ai-trading-assistant-market-symbol", "BTC")',
  'useStoredState("ai-trading-assistant-market-mode", "web3")',
  'aria-label="市场类型切换"',
  'const quote = quoteFor(symbol)',
  '<MarketChannel tab={tab} openOverlay={openOverlay} watch={watch} setWatch={setWatch} symbol={symbol}',
  '<OrderBook openOverlay={openOverlay} watch={watch} setWatch={setWatch} symbol={symbol}',
  'symbol: marketSymbol',
  'placeholder={`数量 ${marketSymbol}`}',
  'symbol={marketSymbol}',
  '<Ticker symbol={marketSymbol}',
]) {
  if (!source.includes(marketSymbolContract))
    failures.push(`Missing global market symbol contract: ${marketSymbolContract}`);
}

for (const localOrderLedgerContract of [
  'useLocalState("ai-trading-assistant-quick-orders", [])',
  'window.addEventListener("ai-trading-assistant-local-state", sync)',
  'window.dispatchEvent(new CustomEvent("ai-trading-assistant-local-state"',
  'const pendingOrders = scopedOrders.filter((order) => order.status === "等待成交")',
  'const historicalOrders = scopedOrders.filter((order) => order.status !== "等待成交")',
  'const filledOrders = scopedOrders.filter((order) => order.status === "模拟成交")',
  'status: "已撤销"',
  '本地模拟仓位已平仓',
  '现货仓位(${positions.length})',
  '当前委托(${pendingOrders.length})',
]) {
  if (!source.includes(localOrderLedgerContract))
    failures.push(`Missing shared local order-ledger contract: ${localOrderLedgerContract}`);
}

for (const channelSpecificContract of [
  "香港 Web3 嘉年华报名开启",
  "2026 Q2 数字资产市场报告",
  "美国现货 BTC ETF 单日净流入 4.2 亿美元",
  "链上永续交易员，仓位与成交实时追踪",
  "预测市场高手，观点与仓位一起验证",
]) {
  if (!source.includes(channelSpecificContract))
    failures.push(`Missing channel-specific content: ${channelSpecificContract}`);
}

for (const globalWorkflowContract of [
  'openOverlay("searchResults"',
  'document.documentElement.classList.toggle("news-reading-mode"',
  'window.speechSynthesis.speak(utterance)',
  'model.title.includes("图表布局")',
  'done(`图表布局“${layoutName.trim()}”已保存`)',
  '币安主账户',
  'sectionFilter === "亏损日"',
  '账户持仓排行',
  '资金费率排行',
  '最近24小时',
  '"K线设置", "下单设置", "预警", "快讯弹窗", "策略通知", "市场异动", "消息中心", "Webhook"',
  'useStoredState("ai-trading-assistant-system-settings"',
  'useStoredState("ai-trading-assistant-notifications"',
  '查看关联内容',
  '"消息通知": [',
  '"账户活动": [',
  '请输入 https:// 开头的 Webhook 地址',
  'model.type === "alertCenter"',
  'useStoredState("ai-trading-assistant-alerts"',
  'useStoredState("ai-trading-assistant-alert-history"',
  '["价格预警", "指标预警", "价差预警", "资金费率", "链上预警"]',
  '["我的预警", "历史预警"]',
  '请至少选择一种预警方式',
  '预警已移入历史记录',
  'openOverlay("alertCenter", "预警中心"',
  'openOverlay("alertCenter","信号预警"',
]) {
  if (!source.includes(globalWorkflowContract))
    failures.push(`Missing global workflow contract: ${globalWorkflowContract}`);
}
if (source.includes('finish(`图表布局“${layoutName.trim()}”已保存`)'))
  failures.push("Chart layout workflow calls an undefined completion helper");

for (const excludedFeature of ["群聊", "DCA社区", ">VIP<", '"VIP"']) {
  if (source.includes(excludedFeature))
    failures.push(`Excluded feature returned: ${excludedFeature}`);
}

for (const contract of [
  'localStorage.getItem("ai-trading-assistant-workspace")',
  'localStorage.setItem("ai-trading-assistant-workspace"',
  'useState("自定义指标/回测/实盘")',
  'watchOpen ? "watch-open" : "watch-collapsed"',
  'event.key === "/"',
]) {
  if (!source.includes(contract))
    failures.push(`Missing desktop UX contract: ${contract}`);
}

console.log(
  `Interaction audit: ${buttons} buttons, ${handlers} handlers, ${formControls} form controls, ${formHandlers} form handlers, ${mappedElements} keyed mapped elements.`,
);
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(
  `All buttons and form controls have non-empty handlers; ${requiredPages.length} primary pages route to dedicated components, all ${totalChannels} top-channel entries are present, ${openedOverlayTypes.size} overlay entry types and ${utilityToolTitles.length} utility tools have dedicated outcomes, market workflow states and product exclusions are enforced, 4 multi-step flows are present, and desktop workspace UX contracts are intact.`,
);
