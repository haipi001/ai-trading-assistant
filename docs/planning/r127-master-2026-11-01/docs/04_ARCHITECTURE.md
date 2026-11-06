# 04｜专业终端 + Agent + 真实交易：工程架构

## 1. 优先级：模块化单体 + 少量 Worker，不重建微服务/K8s

现有 React/Vite + FastAPI + Postgres + Redis 足以承载当前目标。增加独立执行 Worker/Agent Worker 和事件通道，保持模块边界，而不是一开始全面重构或接入几十个开源服务。

```text
现有 React r127（导航/图表/策略/快讯/要闻/资产/授权/设置）
    ├─ Shared WorkspaceContext（symbol/venue/account/mode/selection/snapshot）
    ├─ Ace Agent Dock（Chat / Team / Tasks / Actions）
    ├─ Order Ticket + Bottom Orders Panel
    └─ API Client + SSE/WebSocket Event Client + Auth Session
                     │ HTTPS / WSS (same-origin gateway preferred)
FastAPI Application（身份/角色/账户授权/业务 API / 查询）
    ├─ Market & News Data Service → Data Catalog/Trusted Snapshot
    ├─ Portfolio & Real Account Service
    ├─ Strategy/Backtest/Paper Service
    ├─ Thesis / Playbook / Decision / Behavior Risk
    ├─ Agent Orchestrator → Model Providers + Tool Registry
    ├─ Proposal/Approval Service（签名/TTL/撤销/审计）
    └─ Execution Coordinator（唯一真实交易入口）
                  │   │
       Postgres（订单/成交/账本/事件/任务/审计）
       Redis（排队/幂等辅助/通知/快照缓存；不能当成唯一财务真相）
                  │
      Workers / Adapters:
         Agent Worker      Event/Scheduler Worker     Execution Worker
         CCXT one CEX     IBKR future                Read-only Portfolio Sync
                  │
           CEX/Broker private APIs
```

## 2. 三种关键数据域，严禁混淆

- `MarketSnapshot`：外部行情/新闻事实、来源、交易所时区、timeframe、timestamp、陈旧状态、快照哈希。
- `PortfolioSnapshot`：真实/Paper/演示账户状态、账户时间、现金、冻结、持仓、风险预算和有效性。
- `TaskEvidence`：Agent 使用哪份市场/资产/研究资料、何时使用、由哪个模型输出什么提案。**模型内容不是新市场数据来源**。

### 来源权威性优先级

真实订单与真实成交：券商/交易所私有查询/私有事件为权威；本地执行日志证明曾发送过请求，但不能单独证明成交。余额与持仓：私有账户快照+交易记录对账为权威。行情：具名数据 Provider 的可验证原始数据，注明时间与覆盖。模拟：单独账户命名空间。

## 3. 前端状态管理

保留现有 React 行为，在不影响外观的条件下逐步建立：

- `WorkspaceContext`：用户主动选择的标的/周期/venue/资产类别/账户/模式/选区；统一版本号与采集时间。
- `ServerState`：账户、订单、回测、任务、策略、风控，从 API 取并按 event cursor 增量刷新。可用 TanStack Query，但引入时须确保现有功能不回归；本期不是强制新增库。
- `LocalPreferences`：工作区布局、快捷键、UI 主题、图表可视选项可保留 localStorage，但真实订单/持仓/授权不可仅放浏览器。
- `EventStream`：订单状态、Agent 任务、告警、持仓变更。需要重连、游标、顺序、去重、事件丢失后 snapshot 恢复。

## 4. Worker 与事件总线

- **Agent**：流式状态与工具调用、LLM 失败重试、调用预算和运行取消；长任务不阻塞 FastAPI HTTP handler。
- **Strategy/Scheduler**：条件扫描和告警，按需求与权限触发 Agent；避免在每一个 Web Server 实例上各启一份定时任务。分布式租约/唯一调度者是正式发布前置。
- **Execution**：独立权限边界，处理审批后的真实订单。与 Agent worker 完全隔离凭证；策略侧车不能直接访问交易所密钥。
- 关键订单事件使用事务内 Outbox 或同等持久保证；消费端幂等。Redis 失效时以数据库日志和交易所查询恢复。

## 5. 鉴权与密钥

- 公网 API 必须有真实可验证会话/角色/租户上下文，匿名行情与私有账户 API 严格分离。
- 最佳部署形态：前端同源 HTTPS 网关/BFF 转发交易 API，防止托管在 GitHub Pages 时发生跨站第三方 Cookie 限制或暴露管理端口；如果跨域则必须明确 CORS、SameSite、CSRF、Token 策略。
- 读取型交易所 Key 与交易型 Key 的授权与存储单独可见；最小权限、IP 白名单、禁用提现/划转/转账权限。密钥不得进 LLM、浏览器持久存储、日志和 AI prompt。
- 管理员/普通用户、Paper/Live、演示/真实、不同账户、测试/生产都要在后端隔离，不能靠前端按钮遮挡。

## 6. 开源依赖边界

- CCXT：只作为 BrokerAdapter 的一个实现，封装统一 `submit/cancel/fetch/order_events/balances/positions`; 交易所不支持的功能明确标不支持。
- LangGraph：Agent Worker 的状态工作流实现候选，不承担执行网关、财务账本或权限校验。
- Hummingbot API：后期自动策略引擎可选旁路执行方，但必须由你的 Execution Coordinator 给予策略授权与预算；不直接开放平台交易 Key。
- IBKR/富途：独立适配器，股票市场制度/时区/交易时间/订单精度必须单独处理。

## 7. 非功能目标（预算/门禁初值，须经性能测试修正）

- 关键交互优先；典型用户输入与导航响应目标 p95 < 200ms，图表主动切换加载目标 p95 < 2s（网络/数据服务相关，需区分）。
- 已连接交易所的私有订单变化目标在连接正常时 p95 几秒内更新到 UI；不能据此推断成交保证。
- 模型响应不是价格推送的前置；长任务流式增量呈现，断网恢复后能重新订阅任务。
- 对每个用户设置 Token、美元费用、并发、每日任务、新闻抓取限额；限流进入 UI 提示，不能默默吞任务。
- 重要异常必须可观察、可追责、可恢复，至少涵盖执行网关错误、未知订单、对账漂移、数据过期、任务堆积。
