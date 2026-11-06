# 06｜真实交易实施规范：账户、执行、状态机、风控与对账

## 1. 目标 / 分期

**核心目标：在现有交易工作台上完成可被审计的真实交易，而不是手动调用代码 API。** 先一个 CEX 现货交易场所，逐步扩展股票/ETF，最后扩展受限策略自动交易、Web3 路径。绝不将一次成功的 API 请求视作订单生命周期完成。

- L0：只读连接，验证账户/余额/权限、交易能力探测，无真实动作。
- L1：Paper 模拟（真实市场数据，可注入撮合与费用规则）；与真实账户隔离。
- L2：交易所测试网络/Sandbox（如支持，明确与真实规则差异）；全部订单状态机与失败演练通过。
- L3：人工小额 Live：白名单账户+交易标的+手续费与最大订单额+限价优先+用户每单确认+对账。
- L4：多订单类型、IBKR 股票/ETF、长期运行策略与分级自动化。

## 2. RealBrokerAdapter 契约（初期单交易所 CCXT）

```python
class TradingVenueAdapter(Protocol):
    async def capabilities(self, account_id): ...
    async def instruments(self, symbol): ...
    async def get_account(self, account_id): ...
    async def get_balances(self, account_id): ...
    async def get_open_orders(self, account_id, symbol=None): ...
    async def get_order(self, account_id, exchange_order_id=None, client_order_id=None): ...
    async def get_fills(self, account_id, since=None): ...
    async def submit_order(self, account_id, instruction, client_order_id): ...
    async def cancel_order(self, account_id, exchange_order_id=None, client_order_id=None): ...
    async def subscribe_private_events(self, account_id): ...
```

首个适配器应尽量减少连接复用：现有只读链接可用于验证，但真实交易授权必须明确升级，保存新凭证引用，并严格限制提现/转账权限、IP、API Key 范围。CCXT 的支持差异和交易所本身字段都需要写入 `capabilities`，不得假定所有交易所原生支持改单、止盈止损或单一统一订单类型。

## 3. 订单主实体与状态机（必须以服务器数据库持久化）

实体：`OrderIntent`（用户或 Agent 提案）、`OrderDraft`（可编辑票据）、`RiskEvaluation`（服务端规则计算）、`ApprovalRecord`（用户/策略授权与 TTL）、`ExecutionRequest`（幂等提交）、`BrokerOrder`（交易所回报）、`Fill`（实际成交事件）、`PositionSnapshot`、`LedgerEntry`、`ReconciliationRun`、`ExecutionAuditEvent`。

必须区分：

- 本地：`DRAFT → VALIDATED → APPROVAL_PENDING → APPROVED → SUBMIT_REQUESTED`
- 交易所确认：`ACKNOWLEDGED / OPEN / PARTIALLY_FILLED / FILLED / CANCEL_PENDING / CANCELLED / REJECTED / EXPIRED`
- 不确定性：`UNKNOWN_PENDING_RECONCILIATION`，任何超时、断线、重复回调都可能发生；**不能自动重试已发送且状态未知的同一订单请求**，先按 `clientOrderId` 查询对账。
- `PARTIALLY_FILLED` 可以进一步成交、取消或到期；`CANCEL_PENDING` 同时仍可能成交；`FILLED` 不能因为本地撤单按钮而倒退状态。

所有状态变更必须携带 sequence/idempotency/event_id 与事件时间，客户端不是订单状态权威。

## 4. 真实提交时必须同步重算的风控

`validate(auth actor, account, venue rules, wallet available balance, order proposal version, instrument minNotional/stepSize/tickSize, quote freshness, portfolio exposure, working orders, trading mode, user risk constitution, session approval TTL, strategy policy, global kill-switch)`。

关键原则：**风险阈值由服务端已保存的风险政策读取，当前持仓/余额/挂单/已有敞口由可信账户快照计算；前端 JSON 里的 total_equity/current_position_pct 等只能用于说明或编辑草稿，不能作为风控权威。**

首期策略：默认禁止杠杆与合约、禁止市价超额、不支持时段/订单参数时拒绝。默认交易权限关闭。后续增加股票的市场时间、盘前盘后、做空/保证金、公司行为和精度规则；不要把加密现货规则硬套到股票。

## 5. 下单、撤单、断线的实盘闭环

1. 用户在 S2 的行情图表或订单面板填写数量、方向、方式、交易所、账户，点击“预览”。
2. 服务端依账户最新状态计算：名义本金、最大损失估计、费用、可用余额、单标的及组合敞口、风险限制；返回 `risk_evaluation_id` 和版本、短 TTL。
3. 前端展示不可误认的 LIVE 确认票据；用户确认后，服务端再次比较风险快照/订单版本/价格有效性和授权；过期须重新预览。
4. Execution Coordinator 在数据库里持久化提交意图及 `clientOrderId`，经唯一执行权限向交易所提交。响应为 ACK/拒绝/未知，不以 HTTP 200 直接等于成交。
5. 私有事件流或轮询实际订单/成交 ID 更新状态与账本。掉线时暂停新的策略自动下单并提示“账户实时状态待确认”；已有订单仍需继续查询对账。
6. 撤单：前端发出请求 → 执行网关 → 确认交易所状态 → 确认无未完成持仓状态；失败重试安全，不得声明用户点“撤单”后已经撤完。
7. 任何执行与相关证据都写入审计事件和交易日志，供 Agent/用户复盘。

## 6. 幂等与一致性

- 全链路 `intent_id`、`draft_version`、`approval_id`、`idempotency_key`、`client_order_id`、`exchange_order_id`、`execution_event_id`。
- 数据库执行请求唯一约束；队列至少一次投递容忍，消费者幂等；重复浏览器请求只查同一订单状态。
- 必须处理交易所支持与不支持自定义 `clientOrderId` 的差异；无可靠查询/去重保障的交易所不进入首期 Live。
- Outbox/Event Journal 保证事务与异步通知一致；对账优先外部权威，保留本地未知状态事件而不是覆盖成成功。
- 对账粒度：订单、成交、费用、账户余额、分币种净变动和持仓。异常不自动修正资金记录，记录差异、人工确认或受控恢复。

## 7. 交易功能发布顺序

1. Single venue CEX spot test mode, `LIMIT` BUY/SELL + `CANCEL` + lookup + order status + fills。
2. 同交易所最小真实订单，小额可控+每单人工确认；测试需覆盖限价挂单、部分成交、撤单与复查。
3. 市价、订单编辑（可先 cancel+replace 但须双重风控与处理竞态）、止盈止损（按能力矩阵分类）与多 symbol。
4. 第二交易所或 IBKR Paper，再逐步股票 Live。此阶段不搞统一多券商智能路由。
5. A5 受控自动化：策略实例、资产/名义额度/日限/风险限/交易账户白名单/有效期/暂停操作，保护外部 Agent Sidecar 不可越权。

## 8. 必须通过的异常测试（无一省略）

- 错误 API Key、没有交易权限、提现权限启用、交易所维护、速率限制/429、IP 限制、账户冻结。
- 最小名义金额/精度不符、资金不足、仓位限额、报价过期、品种不可交易。
- 断线时提交订单，HTTP 超时但交易所实际接受；禁止双单。
- 两个浏览器窗口同时点提交；数据库只创建一次执行意图。
- 部分成交后撤单，成交和撤单竞态，费用更新、剩余数量一致。
- 接入密钥在运行中被撤销、会话过期、角色越权、跨用户订单 ID 访问。
- 接到过期/重复/乱序私有事件；对账恢复正确，账本不重复计费。
- Kill-switch 生效后拒绝新增真实单；已挂单的撤单策略另行明确，并显示可证实的处理结果。
- 数据源/Redis/DB/Agent 断开：执行模块不能静默继续不受控下单；后台策略进入安全态。

## 9. 安全运营限制

- 生产交易 API 必须运行在受控 HTTPS 服务，不直接暴露 API Key 给静态 GitHub Pages 浏览器。
- 默认 LIVE=false / 自动授权 A0；上线时只能对通过门禁的具体账户显式授权，审核日志保留。
- 交易账号使用独立交易 Key，关闭提现、划转权限、IP allowlist。策略引擎与 LLM 无任何交易 Key。
- 强制日限额、单笔限额、单标的/集中度限额、最大未完成订单数、订单提交速率、重复方向/价格保护和最大损失风控；阈值用户配置后仍由服务端执行，不能在请求体里降低已锁定风控。
- 生产/测试数据库物理或严格权限隔离，不允许前端通过切模式共享真实持仓与 Paper 账本。
