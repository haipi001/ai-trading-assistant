# 08｜API 契约与流式事件（现有路由和拟新增 v2 严格区分）

## 1. 现有代码中有代表性的 API（需先检查权限与响应 schema）

| 路由 | 当前用途 | 接入后目标 |
|---|---|---|
| `GET /health/status` | 后端健康连接 | 顶栏准确展示后端健康/交易能力/行情各自状态 |
| `GET /assets`, `GET /candles` | 标的/历史行情 | 统一标的身份、来源与快照 |
| `GET /news-feed/latest` | 新闻缓存 | 快讯/要闻源状态与引用 Agent |
| `POST /production/human-control/llm/chat` | AI 研究聊天 | Ace Chat 与 Agent Task 链接，资料授权/成本明示 |
| `GET /production/human-control/llm/chat/status` | AI 模型配置状态 | 顶栏/右栏显示能否研究 |
| `GET /exchange-connections` | 已保存只读交易所连接 | 继续区分只读与交易权限，不改变原连接含义 |
| `POST /exchange-connections/{id}/check` | 只读重新验证/余额 | 连接管理/资产页统一反馈 |
| `POST /agents/run-research` | 模拟研究委员会入口 | 迁移到持久化 Agent Task API 并保留旧 API 兼容 |
| `POST /decision-gates/evaluate` | 规则闸门 | 核查客户端风险输入可信边界，真实执行必须使用服务端重算 |
| `/backtest-runs`, `/paper-executions/*` | 回测与模拟成交 | 策略页面/订单页面共用可信输出 |
| `/live-execution/*` | 当前实盘安全骨架 | 原接口兼容但真正实盘必须经新执行网关、权限和审批 |

以上是路径/代码定位示例，**不表示这些路由在当前部署环境中一定可访问**。实现前需依据 OpenAPI 和代码再核对每个具体入参/权限。

## 2. 拟新增 v2 API：只代表目标契约，首期不强制全部实现

| 资源 | 方法/路由 | 授权 | 产物 | UI |
|---|---|---|---|---|
| Workspace | `GET/PUT /api/v2/workspaces/{id}` | 当前用户 | 工作区布局/选中上下文 | 顶栏、图表、多窗 |
| Instruments | `GET /api/v2/instruments/search` | 登录或公共行情权限 | 实名 instrument ID | 搜索、订单票据 |
| Agent Task | `POST /api/v2/agent/tasks` | research:run | `task_id`, status | Ace Chat/Team |
| Agent Task | `GET /api/v2/agent/tasks/{id}` | task owner | task progress/evidence | Ace Tasks |
| Agent Task | `POST /api/v2/agent/tasks/{id}/cancel` | owner | cancel ack | Ace Tasks |
| Action Cards | `GET /api/v2/agent/actions` | owner | action list with provenance | Ace Actions |
| Strategy Draft | `POST /api/v2/strategies/drafts` | strategy:write | versioned draft | 我的策略 |
| Exchange Account | `GET /api/v2/trading/accounts` | account:read | capability+permission | 授权、资产、票据 |
| Account Verify | `POST /api/v2/trading/accounts/{id}/verify` | account:manage | current permission snapshot | 授权 |
| Order Proposal | `POST /api/v2/trading/proposals` | proposal:create | proposal id/version | Ace / 交易 |
| Risk Preview | `POST /api/v2/trading/orders/preview` | trade:preview | risk evaluation id/ttl | 下单票据 |
| Order Approve | `POST /api/v2/trading/orders/{id}/approve` | trade:approve + freshness | approval id | 确认票据 |
| Order Submit | `POST /api/v2/trading/orders/{id}/submit` | trade:submit + active approval | execution request & status | 真实交易 |
| Order Read | `GET /api/v2/trading/orders` | account:read | authoritative order lifecycle | 底部订单 |
| Order Cancel | `POST /api/v2/trading/orders/{id}/cancel` | trade:cancel | accepted/pending/failed | 订单详情 |
| Fills | `GET /api/v2/trading/fills` | account:read | actual fills | 成交、日志 |
| Positions | `GET /api/v2/trading/positions` | account:read | broker-reconciled positions | 资产、风险 |
| Reconcile | `POST /api/v2/trading/accounts/{id}/reconcile` | account:manage | reconciliation job id | 资产、订单 |
| Alerts | `GET /api/v2/alerts` | user | alert list | Ace Actions/顶部通知 |
| Events | `GET /api/v2/events/stream` | event:subscribe | SSE event stream with cursor | 多工作区 |

## 3. 通用响应 Envelope（示例草案）

```json
{
  "request_id": "req-uuid",
  "resource_id": "business-resource-id",
  "status": "accepted|pending|completed|blocked|failed|unknown",
  "as_of": "2026-11-01T00:00:00Z",
  "source": "broker|provider|calculated|demo|paper",
  "mode": "DEMO|PAPER|LIVE",
  "version": 1,
  "stale": false,
  "data": {},
  "error": null
}
```

> 只作为新接口的约定示例；旧 API 不强制一次性切换，否则会造成 r127 功能大面积回归。

## 4. 事件通道（SSE 初期优先，双向需求再上 WebSocket）

结构：`event_id, stream_cursor, tenant_id(server), workspace_id(opt), resource_type, resource_id, type, occurred_at, emitted_at, payload_version, payload`。客户端指定上次游标重连，服务端校验租户并按序回放；序号过期则返回应重新拉资源快照的错误类型。

| 事件 | 界面位置 | 约束 |
|---|---|---|
| `market.source.status_changed` | 行情/快讯/顶部状态 | 来源级状态，不能把新闻源失败误显示为交易断线 |
| `agent.task.status_changed` | Ace Tasks | 展示真实任务状态与工具阶段 |
| `agent.action.proposed` | Ace Actions | 可审查，不触发实盘 |
| `risk.order.blocked` | 票据/通知/审计 | 具体规则与服务端输入版本 |
| `approval.requested/expired` | 票据/Action Inbox | 过期须重新评估 |
| `order.state_changed` | 订单表/票据 | 依据服务端/交易所状态机，含来源 |
| `execution.fill.confirmed` | 成交/持仓/日志 | 必须有真实 Fill ID，禁止模型生成 |
| `portfolio.snapshot.updated` | 资产/风险/Agent Context | 账户、币种、时间与对账状态明确 |
| `reconciliation.discrepancy` | 资产/订单/通知 | 无法对账则升级告警，不能静默平账 |

## 5. UI 动作的 API 验收

点击 → 调用合法 Endpoint → 错误状态可见 → 服务端数据持久化 → 事件通知 → 刷新/重登/切换标签后状态可一致恢复。`idempotency_key` 只针对需要防重复的 mutation；对所有 POST 必须校验用户会话、权限和资源归属。

## 6. JSON Schema

参考 `schemas/agent_task.schema.json`, `agent_action_card.schema.json`, `trade_proposal.schema.json`, `order_event.schema.json`, `workspace_context.schema.json`。这些是客户端/服务端协作草案，不是直接可部署的 ORM migration。实施时由 Pydantic 模型生成 OpenAPI，再在 TypeScript/Zod 或 JSON Schema 消费端校验，避免两套独立事实来源。
