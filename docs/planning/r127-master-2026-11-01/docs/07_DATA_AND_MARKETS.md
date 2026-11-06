# 07｜行情、资讯、数据目录与专业数据可信性

## 1. 保留已实现的数据接入

前端公开行情已包含 Binance / OKX / Bitget 现货的 K线、ticker、盘口、最近成交、多周期聚合和直播处理；不要改回用一个随机数模拟行情。同时保留用于教学和 Demo 的 `demoMarketBars`，但从视觉上把其与 LIVE/PAPER 交易的实际行情分离。

### 标的唯一身份

`asset_class / venue / instrument_id / base / quote / settlement / product_type / currency / exchange_timezone / trading_calendar / tick_size / lot_size / min_notional / instrument_status`。

跨交易所 BTC/USDT 可能存在交易制度和流动性差异；股票/ETF 同名 ticker 也可能跨交易所重复，必须有可靠 instrument ID 和账户级 symbol mapping。

## 2. 交易用数据快照

一个可用于风控和 Agent 的行情快照至少有：`provider`, `instrument`, `as_of`, `received_at`, `timeframe`, `last_closed_candle_at`, `is_last_candle_closed`, `market_session`, `latency_ms`, `data_quality`, `source_url_or_provider_ref`, `content_hash`。

- 标记采集时间与交易所生成时间，不混淆。
- 每种用途设置不同 `freshness_policy`：展示图表、信号判断、订单预览、真实下单不可使用一套统一的宽松 TTL。
- 过期、断流、缺柱、数值异常、未来数据、跨 symbol 数据禁止进入正式决策条件；UI 可继续展示标记的历史数据供研究。
- 不能把静态概览的 `MARKET_QUOTES` 当成实时价格。没真实来源时状态是 `DEMO`, `OFFLINE`, `STALE`, `UNAVAILABLE`，不是显示虚假成功价。
- 历史回测禁未来函数/存活偏差；明确交易费率、滑点、交易时间与数据覆盖范围。

## 3. 资讯与新闻

- 复用目前已有的来源级缓存、部分失败、新闻筛选、独立摘要与快讯等代码；截图离线是恢复体验的需求，不等同于代码未实现。
- 官方 RSS/授权 API 与自建抓取策略分离；尊重订阅版权、转载条款、robots/请求限制和供应商数据许可。
- `source_status` 必须含 last_success, last_attempt, error_code, stale_reason, count；一源失败不清空其他源。
- AI 仅可引用有效的 `news_item_id`，文章正文不可信，提示词注入不得改变交易权限。
- 从快讯/要闻到 Agent 研究：保存原文链接、发布时间、获取时间、事件 ID、相关标的（含 `link_method`、可信度），用户可打开来源验证。

## 4. 股票与加密市场分歧

- 股票/ETF：市场日历、盘前盘后、企业行动、股息拆合、币种/汇率、行情交易所授权与数据许可。
- 现货 CEX：24/7、资金费率不适用现货；深度与逐笔来源按市场。USDT 基础币和法币估值分离。
- 永续/合约：杠杆、保证金、强平、资金费率与仓位模式是独立交易模块，不应因为首页有“合约数据”就默认可以真实交易合约。
- 链上/Web3：区块时间、交易所外行情、gas、授权风险、链重组和签名操作；初期只读。

## 5. 研究/订单资料可追溯

研究任务 `ResearchRun` → 输入 `data_snapshot_ids` → 模型与工具日志 → 输出 `evidence_ids` → `ActionCard` → `OrderProposal` → `OrderDraft` → `Order` → `Fill` → `Review`。所有关键实体必须可点击回溯。同一份数据可以用于研究，但交易风控需要下单时刷新账户与行情状态，不能直接使用昨天的研究快照。
