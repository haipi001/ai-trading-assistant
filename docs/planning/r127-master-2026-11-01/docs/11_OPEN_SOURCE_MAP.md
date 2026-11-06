# 11｜开源代码复用地图（精简依赖而非复制整个交易平台）

以下是适用性判断，不代表已把代码接入现有仓库。采用前逐一核对最新版本、许可证、供应商政策和维护状态；不复制来源不明或可能受商业条款限制的前端资产。

| 项目 | 官方代码 | 角色 | 接入阶段/形态 | 决策与边界 |
|---|---|---|---|---|
| CCXT | https://github.com/ccxt/ccxt | CEX 市场+真实订单+撤单+账户连接 | T2，Python 依赖/封装 | **优先引入**；先单交易所现货；能力按 venue 探测，独立订单账本 |
| ib_async | https://github.com/ib-api-reloaded/ib_async | IBKR 股票/ETF 账户、订单、回报 | T5 独立 BrokerAdapter | 需 TWS/IB Gateway、真实账户/数据许可，不和 CCXT 混进统一原生 schema |
| Futu OpenAPI | https://github.com/FutunnOpen/py-futu-api | 富途行情与交易 | T5 备选 | 账户资格、OpenD、交易/市场规则、区域合规先核实 |
| LangGraph | https://github.com/langchain-ai/langgraph | 多 Agent 状态/检查点、人机审批 | T3 仅 Agent Worker | 可以延后直到真实任务/事件需求明确；不得让它负责真实订单/风险权限 |
| TradingAgents | https://github.com/TauricResearch/TradingAgents | 多角色投研/牛熊辩论 | T3 参考/有限复用 | 重点学习证据、多角色与回测时间边界；不直接替换本项目研究模型 |
| Vibe-Trading | https://github.com/HKUDS/Vibe-Trading | AI 交易研究/工具调用思路 | T3/T4 架构参考 | 选取合适模式，不直接拷贝全部前端和策略结果 |
| Hummingbot API | https://github.com/hummingbot/hummingbot-api | 机器人策略与真实执行服务 | T6 可选 sidecar | 不能绕过本平台订单权限、审计、风险授权；先决定是否真需要 |
| Hummingbot Condor | https://github.com/hummingbot/condor | Agent + 策略执行边界 | T3/T6 研究参考 | 重点学习“LLM 推理/确定性交易分离”，无需直接变成产品主 UI |
| Freqtrade | https://github.com/freqtrade/freqtrade | 策略回测/自动机器人 | T4/T6 备选 | 若现有回测/执行缺口严重再采用，不同时叠加多套引擎 |
| NautilusTrader | https://github.com/nautechsystems/nautilus_trader | 事件驱动与实盘/回测一致性 | T4 架构参考 | 不初期引入 Rust 大型引擎，学习事件/订单生命周期即可 |
| LEAN | https://github.com/QuantConnect/Lean | 多资产量化回测与实盘 | T4/T5 参考 | 主引擎和语言栈差异较大，不宜替换现有 Python FastAPI |
| Lightweight Charts | https://github.com/tradingview/lightweight-charts | 图表 | 现有，持续维护 | **已使用，坚决保留**；扩展 Agent 批注，不推倒现有绘图系统 |
| OpenBB | https://github.com/OpenBB-finance/OpenBB | 基本面、宏观、数据提供层 | T3/T5 数据插件 | 合同和数据许可比 UI 拷贝更重要；可按数据需求接入 |
| Fincept Terminal | https://github.com/Fincept-Corporation/FinceptTerminal | 专业信息架构和工作区参考 | UI 研究 | 不直接复制 UI/源码；查清具体 AGPL/商业许可证版本与义务 |
| Ghostfolio | https://github.com/ghostfolio/ghostfolio | 投资组合/绩效界面参考 | T4 产品研究 | 留意 AGPL 与资料许可，默认不移植代码 |
| rotki | https://github.com/rotki/rotki | Web3 组合与成本归因参考 | T5/T7 研究 | 根据钱包/资产需求参考，不引入整个产品 |

### 引入新依赖前的评估表

必须填写：许可证及仓库链接；主要维护语言/升级频率；引入的具体功能；与现有 `backend/app/services/` 的重叠；可以作为可选适配器吗；失败/断线如何处理；是否需要保存资金 API Key；资源/CPU/内存/Token 预算；独立进程安全边界；运行证据；回退路径。

**明确不建议**：一期同时加入 CCXT、Hummingbot、Freqtrade、LEAN、NautilusTrader 作为五套执行真相源。先确保一套订单/账本/风控中心，外部代码只作为其实现或沙盒侧车。
