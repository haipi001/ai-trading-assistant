# 13｜首四个迭代 Sprint（可立即执行）

> Sprint 按约 5 个工作日的独立迭代组织，只为排期方便；不可据此保证上线时间。具体开发的任务 ID 见 `tasks/development_tasks.csv`。

## Sprint 01｜冻结 r127，恢复完整 CI，拦住真实风险

**功能切片 A：UI 测试基线**
- 记录 r127 的 5 个用户锚点与所有 NAV/META/九类策略/右侧快捷导航/底部交易区。
- 添加 Playwright 或等价浏览器自动化最小冒烟：入口/频道/图表指标/笔记/新闻离线/设置；截图差异仅做提示而不直接压过功能测试。
- 检查 `src/main.jsx` 里 Demo 实时报价混用位置，生成定位清单；本轮不改原样式。

**功能切片 B：CI 健康**
- 修复 `[dev,mcp]` 安装，运行完整 pytest；若出现后续测试失败，逐一修复而非 skip。
- 将前端 model tests/build/security/migration guard/secret scan 作为必需检查；GitHub Pages 部署必须能明确体现 CI 审核门禁。
- 保留完整命令与耗时，记录 Postgres 独立迁移/空 DB 测试结果。

**功能切片 C：认证与风控可信性**
- 对 Render Blueprint 的 `MANAGED_AUTH_REQUIRED=false` 做安全差异分析；在 staging 强制 session、API 资源归属、CSRF/CORS 与限流。
- Risk/DecisionGate 的持仓/资金/授权来自服务端，不接受客户端“我没有仓位”类参数作为最终交易许可。
- 若涉及生产数据库/密钥，先做好脱敏备份/回滚说明。

**Sprint Exit**：回归 CI 绿、截图/功能基线固定、生产公开风险可证明修正；仍未实盘。

## Sprint 02｜Ace Agent 原位增强 + 全站可信状态

- 新增兼容层 `WorkspaceContext`，从 S1 首页、S2 行情、S3/S4 资讯、S5 策略、资产发送当前上下文；不用重写所有页面。
- 现有 Ace Agent 提供 Chat/Team/Tasks/Actions 结构，初期没有能力的面板显示真实“尚未启用/计划中”，不是模拟任务百分比。
- 统一行情、新闻、AI Key、只读账户各自 ConnectionState；资讯失败时保留来源缓存/时间/错误/重试。
- 自动化测试上下文切换 BTC→ETH、不同 venue、不同 timeframe、Demo/Paper/Live；旧附件不误发。

**Sprint Exit**：同一图表选区可传入已有真实模型研究对话，能看到正确快照；关闭 Ace Agent 不破坏图表。

## Sprint 03｜订单票据（仅 Paper）、服务端订单与审批

- 复用后端已有 `PaperExecution`，为前端增加可编辑专业票据、风险预览、服务端订单 ID、审批状态、模拟成交与底部订单面板。
- 真实账户选择与 Paper/Live UI 分层显示；本轮不调用真实下单 API。
- 订单数据从服务端反查，页面刷新仍可看完整进度；资产/日志联动；双击、重复点击、断线测试。
- 导出 `OrderIntent/Draft/Fill` 的结构化字段，用于未来 LiveAdapter 实现。

**Sprint Exit**：通过 UI 完成第一笔完整 Paper 限价单（包括费用、持仓、复盘）；实盘仍阻止。

## Sprint 04｜第一真实 CEX 适配器框架（仍以 Sandbox 为主）

- 选择实际可用的一家 CEX 现货（不同时接多家），先实现能力检测、只读账号/交易权限区分、市场规则、余额与订单查询。
- 加入 `OrderStateMachine`、幂等 ID、事件持久化/查询、未知订单对账、执行网关授权；在 Sandbox/假服务做超时/拒单/部分成交/撤单。
- 现有 UI 的 OrderTicket / OrdersBottomPanel 接收真实来源的状态，不再根据前端点击立即生成成交。
- 如果尚无外部 Sandbox 授权，使用明示 fixture 执行此 Sprint，但 **不标记真实交易验收完成**。

**Sprint Exit**：完整模拟 Broker 断线、取消/重试、对账情况；安全门禁满足后才计划人工小额真实交易测试。

## 最小端到端标志性验收

`行情 BTC/USDT → 选取 1H 图表 → Ace Agent 研究（可选）→ 创建草稿 → 风控预览 → Paper 成交 → 资产与交易日志刷新`，所有步骤能在当前 r127 外观中完成，无需跳到另一个独立演示 UI。
