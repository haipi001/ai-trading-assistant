# 01｜GitHub 源码基线与实际开发状态

## 经核对的基线

- 当前公共主仓库：<https://github.com/haipi001/ai-trading-assistant>
- main commit：`9e774c232992bda309fdd22099114b5303a74f10`（2026-11-01）
- 当前架构：React 19 + Vite 6；FastAPI、SQLAlchemy、Postgres/Redis、Alembic；前后端合仓后根目录 `src/`、`backend/app/`；测试在 `scripts/`、`backend/tests/`。
- UI 唯一基线：`CANONICAL_UI.md` 的 r127 / 本机 3002；真实源码不以旧备份和外部复刻版为准。
- 2026-11-01 CI：GitHub Pages 成功；Front/backend CI 失败。pytest collect `backend/tests/test_mcp_readonly.py` 报缺少 `mcp` extra。CI 文件在 `.github/workflows/ci.yml`。

## 可复用的实际模块

| 领域 | 现有位置 | 现状/后续策略 |
|---|---|---|
| 导航与整体工作台 | `src/main.jsx`, `src/professional-sidebar.css`, `src/channels.css` | 主结构、色彩与路由保留；逐步模块化，不影响行为 |
| 图表与多窗口 | `src/trading-chart.jsx`, `src/chart-*`, `src/indicator-library*` | 保留既有指标、画线、分屏、布局、回放；修差异而非换引擎 |
| 市场数据 | `src/market-api.js`, `src/live-market-*`, `src/*-public-market.js` | 公共 Binance/OKX/Bitget 多数据流；需要更严谨状态协议 |
| 快讯/要闻 | `src/news-feed-*`, `src/news-notices*`, `backend/app/services/news_feed.py` | 实现过真实 RSS 聚合和状态/缓存；截图离线时应显示恢复策略 |
| AI 设置与聊天 | `src/ai-integration-settings.jsx`, `src/research-ai-chat.jsx`, `src/research-ai.js` | 有 BYOK OpenAI/DeepSeek、研究附件和验证；下一步提升成跨工作区 Agent Cockpit |
| 只读连接 | `src/exchange-probe-panel.jsx`, `src/saved-exchange-connections.jsx`, `backend/app/api/exchange_connections.py` | 多 CEX 只读连接/余额校验；不等于具备实际交易权限 |
| 我的策略 | `src/strategy-intelligence.jsx`, `src/script-workspace.jsx`, `src/strategy-filters.css` | 保留 9 个类别、笔记与脚本；把生成草稿改为结构化可审查成果 |
| Agent 角色 | `backend/app/agents/research.py`, `backend/app/services/research_committee.py` | 模拟 Agent + 顺序研究；不冒称真实并行 AI 服务 |
| AI Providers | `backend/app/ai/providers.py`, `backend/app/services/research_evals.py` | OpenAI/DeepSeek 及真实 Provider Eval 基础可重用 |
| 模拟与回测 | `backend/app/services/paper_execution.py`, `backend/app/services/backtests.py` | 成交/滑点/手续费/账本与回测基础有实现；前端闭环和真实一致性待验证 |
| 风控与决策 | `backend/app/services/risk.py`, `decision_gates.py`, `automation_policy.py` | 已有基础；生产前必须审计风险输入是否来自可信服务端快照 |
| 实盘骨架 | `backend/app/services/live_execution.py`, `backend/app/api/live_execution.py` | `execute` 明确追加 `real_live_execution_not_implemented`，未真实下单 |
| 服务部署 | `backend/render.yaml`, `.github/workflows/ci.yml` | 基础存在；实际生产账号授权与 CI 为阻塞 |

## P0 问题（事实/待验证）

1. **CI 失败**：`mcp` 为 `[project.optional-dependencies].mcp`，CI 当前仅装 `backend[dev]`。修好依赖后必须运行全部后端和前端测试；不可据此推断测试都通过。
2. **认证边界**：当前 Render Blueprint 设置 `MANAGED_AUTH_REQUIRED=false`。`auth_middleware.py` 在托管身份关闭时直接放行非登录请求（须结合端点依赖全面审计）。任何可公网访问的交易/密钥服务都不得以此配置上线。
3. **真实交易**：目前无真实下单实现。必须在交易执行服务里新增合格适配器及状态机并完成功能、安全验收；不准简单删除 blocking reason。
4. **风险可信数据**：`DecisionGateEvaluateRequest`、风险计算多个字段可以来自客户端请求。需要研究 API 是否允许前端输入覆盖持仓敞口或真实风控阈值；后端以可信账户快照与存储策略重算。
5. **Demo 混合风险**：前端仍有 `demoMarketBars` 和静态 `MARKET_QUOTES`。已有真实行情可用时要严格区分，未连接不使用示例伪装成实时。
6. **多 Agent**：研究委员会当前依次运行模拟研究角色；BYOK 真模型入口不等于研究委员会已经启用真实并发代理。
7. **单用户历史路径**：部分 API 仍有 `default-user` 等历史兼容用法。必须检查在真实生产会话下的一致性、跨租户隔离和迁移历史数据的权限归属。

## 明确未完成的外部证明

- 未在此次规划工作中运行本地或 staging 全量 E2E；未以真实密钥进行交易所成交；未证明真实股票交易账户可用；未证明目前 r127 每个按钮均可真实执行业务动作。
- 研发任务文档是计划，不是运行报告。每个 PR 需记录代码 commit、测试命令、截图/脱敏视频、外部 API 调用有无发生、是否发生真实资产变动。
