# r127 整体实施规划 · 2026-11-01

状态：规划已整理，T0/T1 等增量开发中；113 项完整退出条件尚未满足。唯一主仓库为 `ai-trading-assistant`。首次导入时 HEAD 为 `9e774c232992bda309fdd22099114b5303a74f10`、初始工作树干净；后续实现与验收以执行追踪表及 `docs/acceptance/` 的日期证据为准，当前开发改动尚未提交。

## 1. 产品目标与范围

在当前浅色专业交易终端上，形成“研究证据 → 提案 → 风控 → 人工审批 → 订单 → 成交/持仓 → 复盘”的可追溯闭环。保留 React/Vite r127、localhost:3002、全部十个主导航、二级频道、九类策略、图表工具、脚本、画线、多窗、回放、笔记和本地数据。Ace Agent 在现有右栏增加 Chat/Team/Tasks/Actions，支持关闭，手动交易不依赖 AI。

全范围沿用[原工程包](r127-master-2026-11-01/README.md)：113 项任务、95 项 UI 覆盖、5 份契约 Schema、五张用户截图。95 项是原包覆盖项，不代表全部按钮已盘点。T0 继续补充细粒度控件、弹窗、快捷键和持久化路径。

本文件确定实施顺序，不将任务表中的 TODO 当作已完成实现。原包完整保存，来源摘要见 `r127-master-2026-11-01/SOURCE_SHA256.json`。

## 2. 规划导入时的代码核对与事实边界

下表是首次导入的基线。后续增量以 [T0开发证据](../acceptance/R127_T0_PROGRESS_2026_11_01.md) 与 [认证及会话证据](../acceptance/R127_T0_AUTH_2026_11_01.md) 为准；例如Render认证默认值现已改true，但尚未部署验收。

| 项目 | 本轮静态核对 | 对规划的影响 |
|---|---|---|
| 唯一 UI | CANONICAL_UI.md 指向当前目录/3002；main.jsx 十个 NAV、九类策略仍存在 | 原位增强；旧 Next.js 偏好不用于替换 UI |
| CI | ci.yml 仍安装 backend[dev]，未包含 mcp extra | T0-04 修复依赖后跑全套；本轮未查询远程最新 CI，不断言其当前状态 |
| 托管认证 | backend/render.yaml 的 MANAGED_AUTH_REQUIRED 仍 false | 先完成身份全链验证；仅改配置不足以关闭问题 |
| 实盘 | live_execution.py 仍包含 real_live_execution_not_implemented | 真实交易尚待适配器与门禁，不删除保护冒充实现 |
| 现有能力 | 市场、新闻、BYOK、Paper/Risk/Approval 等已有代码定位 | 按模块审计并复用；源码存在不等于端到端通过 |
| 运行证明 | 本轮未启动浏览器、pytest、真实模型或券商 | 不沿用历史通过数作为当前验收；无真实订单或费用 |

历史 v4 的领域模型与安全约束继续保留；新开发按本计划 T0–T7 排期。手动订单可使用明确用户理由，策略自动化仍需 Constitution/Playbook 等上游约束；不得把“降低操作步骤”实现为绕过服务器闸门。

## 3. 总体架构和状态归属

采用模块化单体：现有 React → 同源 HTTPS API → FastAPI → Postgres/Redis，按需求增加研究 Worker、调度 Worker、执行 Worker。优先复用 backend/app/services，不引入多套订单真相源。

| 状态 | 权威与存储 | 前端职责 |
|---|---|---|
| 工作区 | WorkspaceContext，含 instrument/venue/timeframe/account/mode/context_version | 页面间传递；切对象后不误发旧附件 |
| 行情/资讯 | Provider 原始数据与服务端快照，来源/时间/hash/质量可追溯 | 显示来源、陈旧、部分失败与重试 |
| 任务/证据 | DB 持久化任务、角色、工具调用、费用和证据 | SSE 游标恢复；不计时伪造进度 |
| 订单/成交/账本 | DB 订单日志与交易所私有回报/查询对账 | 展示状态；本地点击不能代表成交 |
| 授权/风控 | 服务端用户/账户归属、政策、可信账户快照 | 可编辑草稿；不能覆盖权威风险字段 |
| 布局/偏好 | 兼容 localStorage，逐步可选服务端保存 | 无损导入导出与回滚 |

研究 Worker 不持资金 Key。模型只生成经校验的 ResearchReport/ActionCard/Proposal。Execution Coordinator 是唯一执行入口；DB 唯一约束、事务 Outbox、幂等消费者及对账共同处理重复事件与重启。Redis 不是财务真相源。

## 4. 阶段、依赖与交付门禁

| 阶段 | 任务数 | 交付能力 | 前置与完成证据 |
|---|---:|---|---|
| T0 / R0 | 16 | UI 清点、完整 CI、认证/租户、可信风控、恢复基线 | 五屏及路径证据；完整回归；权限拒绝及绕过测试；迁移恢复 |
| T1 / R1 | 17 | 跨页 Context、Ace 原位增强、来源状态、Paper 票据 | T0；图表/新闻/策略/资产联动；刷新恢复；无旧功能丢失 |
| T2 / R2 | 20 | 单一 CEX 现货人工交易、查询/撤单/成交/对账 | T0+票据；fixture 故障注入→真实 Sandbox→独立获权的小额 Live |
| T3 / R3 | 18 | 真实多角色研究、后台任务、证据、Actions、预算 | T0+T1；各角色真实调用与费用/失败记录；注入/取消/恢复评测 |
| T4 / R4 | 12 | 笔记/策略版本→回测→Paper→受限 Live→复盘 | T2+T3；无损迁移、样本外、费用滑点、归因一致性 |
| T5 / R5 | 10 | IBKR 股票/ETF、独立日历/币种/企业行动 | T2 稳定；IBKR Paper 后单独获权 Live；Futu 为可行性核查 |
| T6 / R6 | 10 | A5 策略限额授权、到期撤销、暂停、恢复 | T2+T4；跨账户/标的/额度越界拒绝；多实例防重复与停机演练 |
| T7 | 10 | 专业工作区、键盘、多屏、性能、国际化、插件研究 | 相关稳定能力先完成；原浅色和功能回归；实测性能与操作效率 |

T2 与 T3 可在模块层交错推进，T2 不等待所有研究角色完成；所有实盘门禁仍必须通过。T7 的合约、链上签名是独立研究项目，现有合约数据展示不赋予交易权限。

原包阶段估算为 T0 2–3、T1 3–5、T2 4–7、T3 4–6、T4 4–6、T5 4–7、T6 5–8 周。它们是粗略工作量窗口，串行合计 26–42 周且不含 T7；依赖交错不能直接相加成为交付承诺。第三方账户、数据权利与稳定性观察会影响日期。

## 5. 首四个迭代及可审查切片

按约五个工作日组织，实际以退出条件而非日期晋级。

| 顺序 | 任务范围 | 具体交付 | 退出条件 |
|---|---|---|---|
| PR01 | T0-01/02/03 | 10 导航/子频道/九策略/工具栏/弹窗清点；固定五屏；记录 Demo 混用 | 每项有路径、数据模式、既有行为、回归用例；浏览器证据 |
| PR02 | T0-04/05/06 | dev,mcp 依赖、完整后端回归、迁移、前端审计/模型/构建 | 完整命令、退出码、耗时；失败逐项修复，不删除测试 |
| PR03 | T0-08/09/10 | 会话、资源归属、CSRF/CORS/角色/Token；staging 强制认证 | 匿名/错角色/跨用户/跨账户拒绝；前端登录链可用 |
| PR04 | T0-11/12/13 | 持仓/挂单/冻结资金/政策服务端重算；模式与来源标签 | 伪造零敞口/低阈值无效；过期快照拒绝执行 |
| PR05 | T0-07/14/15/16 | 五屏 E2E、依赖/凭据审计、主分支门禁、备份恢复 | T0 证据完整；只读和模拟保持可用 |
| PR06 | T1 核心 | Context 兼容层、Ace Chat/Team/Tasks/Actions、资讯失败恢复 | BTC→ETH/venue/周期/账户/模式切换不污染 |
| PR07 | T1 票据与 T2 基础 | Paper 预览/审批/提交/订单/账本/复盘，复用既有服务 | 真实行情驱动的 Paper 限价单 UI 闭环；断线/双击可恢复 |
| PR08 | T2 适配器 | 单 venue spot 协议、能力检测、状态机、幂等与对账 | fixture 拒单/部分成交/撤单竞态/提交超时通过；有授权再测 Sandbox |

迭代 1 优先 PR01–05，超出容量时顺延而不缩减 T0。迭代 2 PR06，迭代 3 PR07，迭代 4 PR08。没有外部授权时仍可完成隔离实现与 UI 验收，外部证明保持待验证。

## 6. 契约与数据迁移策略

原 API 保留兼容，新能力按需添加 /api/v2；原包 API 表是设计候选，须与代码/OpenAPI核对后实现。以 Pydantic/OpenAPI 为主源生成消费端契约，五份 JSON Schema 是草案，不直接充当 ORM 迁移。

先落 WorkspaceContext 与 ConnectionState，再落 AgentTask/ActionCard；交易实体按 Intent→Draft(version)→RiskEvaluation(TTL)→Approval→ExecutionRequest→BrokerOrder→Fill→Ledger→Reconciliation。事件包含 event_id/cursor/tenant/resource/version/timestamp，重连游标失效时拉快照。

所有持久化变更带 Alembic 迁移、旧数据归属核对、脱敏备份、空库升级及已有库升级/恢复演练。笔记先备份再迁移，保留本地导出与冲突处理。至少一个发布窗口保持 API 兼容；前端回滚不回退成交事实或删除账本。

## 7. 验收与发布

第一条标志性路径：BTC/USDT 1H 图表→可选 Ace 研究→草稿→服务器风控→人工审批→Paper 成交→持仓/费用/交易日志→复盘。必须在原 r127 页面完成。

原包 J01–J10 与 95 项覆盖逐项验证。每项记录 commit、环境、命令/退出码、截图、API/DB证据、来源、外部调用及费用、限制和回滚。证据级别分开记录：STATIC、FIXTURE_E2E、EXTERNAL_SANDBOX、EXTERNAL_LIVE，不能互相替代。

Live 发布前要求：全量 CI；认证与租户隔离；服务端可信风控；审批版本/TTL；密钥最小权限；幂等/UNKNOWN 对账；部分成交撤单竞态；Kill-switch；备份恢复；实际账户和单笔授权。未知提交结果先查询，不自动重发。停机默认拦截新单，已有挂单单独查询处理。

GitHub Pages 继续只是静态前端。交易后端采用受控 HTTPS/staging→production 分离部署；本轮未改生产、未启用 Live、未提交或推送。

## 8. 追踪规则与后续入口

[execution_tracker.csv](r127-master-2026-11-01/tasks/execution_tracker.csv) 保留全部 113 个原任务及依赖，追加 VerifiedStatus/EvidencePath/ReviewNotes。初始均 NOT_AUDITED；审计后进入 READY/IN_PROGRESS/IMPLEMENTED/VERIFIED，缺外部条件可记 BLOCKED_EXTERNAL；只有证据满足原任务验收才 VERIFIED。

原表阶段依赖（如 T0）意味着该阶段必需门禁通过，不是其中任意任务完成。执行时补充到具体任务 ID。模块已有代码先核查，防止重复建设。候选依赖 CCXT/ib_async/LangGraph 等在真正引入时重新核验版本、许可和维护状态，本轮不把原包开源表视为最新技术验证。

下一最小任务：PR01，补齐实际 UI 控件/行为矩阵和五屏运行截图，再实施 PR02 的 CI 修复。规划完成与系统完成分别汇报。
