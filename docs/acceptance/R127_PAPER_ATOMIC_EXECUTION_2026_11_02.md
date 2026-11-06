# r127 Paper 事务、幂等与未知结果恢复（2026-11-02）

整体开发继续。本页证明受控 Paper 执行的改进，不表示实盘、所有账户写入或所有数据库并发场景已验证。

## 实现与契约

`PaperExecutionService.execute_draft` 开始前要求调用方没有待提交的模型变更，清除旧读取快照并重新读取订单。SQLite 使用 BEGIN IMMEDIATE 获取数据库写锁；Postgres 代码路径按账户、草稿顺序获取行锁。风控、研究/其余门禁复核改为可加入外层事务，执行时不再中途提交释放锁。

同次模拟成交的 Execution、现金/持仓、税批次、Journal、Review、草稿状态和成功审计在同一事务中提交。提交前异常会回滚这些变更；保留阻止门禁的审计，另记失败尝试。失败尝试不声称一定没有成交：如果提交已完成但响应/读取失败，客户端须查询原请求号。

- 0025 迁移新增 fill_sequence、idempotency_key、request_fingerprint；历史记录按草稿及 created_at/id 顺序回填序号，保留原财务字段。
- 唯一索引约束 `(order_draft_id, fill_sequence)` 和 `(order_draft_id, idempotency_key)`；CHECK 要求 Paper 事件序号非空且为正。重复/缺失身份不能悄悄写成第二条同次事件。
- `PaperExecutionRequest.idempotency_key` 可选，1–128 个字母/数字/点/下划线/冒号/连字符。非有限浮点请求拒绝。原无键客户端保持兼容，但无键的不同部分成交调用按新尝试处理，不提供同请求重放保证。
- 同一草稿、相同请求号、相同执行参数：读取已提交的同一 Execution/Journal/Review，响应 `replayed=true`，不新增成交、不扣第二次款。即使审批已过期，也只读取历史回执，不续期、不执行新成交。
- 相同请求号更换数量、价格、费用、滑点、操作者/理由等执行参数会拒绝。明确的新请求号可继续合法部分成交，仍在锁内重读剩余数量及账户状态。
- 重放响应中的 Execution 是原事件；草稿、税批次等关联状态可能已被后续合法成交更新，不能将它们当作不可变的历史账户快照。
- API 重放沿用 201，并用 replayed 标识返回既有回执；201 本身不表示新发生一笔成交，更不表示实盘。
- 数据库冲突返回 409 / `detail.code=paper_execution_outcome_unknown`，要求查询或用原键重试；不会伪装成已确定的风控拒绝。

原 Paper 票据为同一草稿/价格保存同一随机请求号，参数改变时拒绝静默重试。网络、5xx 或明确的数据库未知状态后禁用普通执行，提供“重试同次模拟执行（使用原请求号）”。不自动重试；读取到 filled 回执后清除未知状态并禁用再次执行。请求号只在当前组件内存保留；刷新后仍可通过服务端草稿/成交读取恢复。

## 文件

- `backend/app/services/paper_execution.py`：事务、锁、序号、幂等重放、异常与失败审计。
- `backend/app/services/risk.py`、`decision_gates.py`：外层事务可控制复核提交，独立 API 仍保留原提交行为。
- `backend/app/models/core.py`、`schemas/core.py`、`api/paper_execution.py`：字段、约束与响应/错误契约。
- `backend/alembic/versions/20261102_0025_paper_execution_identity.py`：兼容历史数据的增量迁移。
- `src/paper-order-workflow.js`、`paper-order-ticket.jsx`、`scripts/check-paper-order-workflow.mjs`：稳定请求号、显式重试、未知结果分类。
- `backend/tests/test_paper_execution_atomic.py`：真实文件数据库及独立请求 Session 的竞争写入和故障注入。

## 验证

原相关 95 项回归通过。新增第一版并发专项 10 passed / 1 warning（4.80 秒），随后新增提交后丢失响应及数据库未知结果测试。

完整后端首轮 894 passed / 1 warning（76.50 秒）；最终完整后端 **895 passed / 1 warning（120.35 秒），退出 0**，新增 12 项；54 组前端模型全部通过，616 按钮/253 控件审计通过，构建 6.86 秒（仅大 chunk 提示），密钥扫描/diff 检查通过。结果与源码 SHA256 见同目录 RESULTS JSON。新用例覆盖同键/不同键/无键全量竞争、部分成交重放及并发完成、同账户不同草稿不丢现金/仓位更新、参数冲突、审批过期后的历史读取、财务/税批次/Journal 写入后故障整体回滚、提交后响应丢失，以及数据库约束和未知结果分类。

SQLite 迁移守卫通过：单 head、空库升级、模型 parity、降级一级再升级。另复制上轮隔离的 0024 数据库到新测试路径，含两笔真实运行产生的模拟成交；升级 0025 后 executions/positions/tax lots/realizations/journals/reviews 全部原列和行逐项相等，新增序号正确、integrity_check=ok。没有迁移真实用户库或重写历史金额。

### 浏览器丢失响应与两进程恢复

新建隔离 SQLite/0025，两份独立后端进程分别运行 8003/8004，共享同一测试库；测试代理在 8001 转发请求。仅测试夹具会丢响应，生产代码没有该开关。初始 seed 仅合成行情/模拟资金，实盘与外部 LLM 均关闭。

1. 原 UI 3002 选择 AAPL/NASDAQ/USD，数量 1，价格 225.12；手动理由明确故障验收、无研究报告，五门通过后单独审批。
2. 第一后端提交草稿 `8b577536-cc7e-47ea-aa27-453b758988af` 成交，代理收到成功体后故意关闭连接。浏览器显示“结果未确认”，普通执行禁用、原请求号重试入口可见。
3. 查询 DB 已有一笔成交；解除夹具丢响应后，实际点击重试，经第二个独立后端进程返回 `replayed=true`。
4. 两次请求号完全相同，执行 ID 均为 `c0fb6d06-55cb-4297-afa7-8281fbe60320`；重试前后都只有一笔成交、序号 1、一份 Journal/Review，金额 225.12、费用 0.022512、现金效果 -225.142512。filled 审计一次、replayed 审计一次，integrity_check=ok。
5. UI 显示原成交回执并禁用执行。恢复 SOL/币安/1h 后关闭临时标签；两个后端日志均有 Application shutdown complete，代理及后端均 SIGTERM 退出143，三个临时端口无监听。保留测试库，不触碰真实账户/凭据。

证据截图：`output/r127-paper-atomic-20261102/recovered-single-fill.png`。最终新增的 409/5xx 分类由 API/模型用例验证；未再做这两种 HTTP 状态的浏览器注入。浏览器实际验证的是提交后断开连接及原号显式重试。

## 剩余限制

- Postgres 锁代码尚未在真实 Postgres 上运行；不将 SQLite 证明外推。SQLite 写锁会串行整个库的写入，不能据此宣称高吞吐/p95 达标。
- 当前序列化范围是这些 Paper 执行入口。审批/政策修改、企业行动、导入及其他账户写入尚未统一遵守同一锁协议；不能宣称所有相邻状态变化或财务操作已经没有时间差。
- 原键重放保护已提交回执；不包含外部交易所订单、Outbox、券商查询/撤单/对账或系统故障后的完整财务恢复。
- 历史 migration 回填不识别或删除旧的错误重复成交，历史审计仍需另做。数据库管理员直接篡改不在此 hash/请求号的抵抗范围。
- 真正的 kill -9/掉电、提交边界磁盘故障、网络分区、大规模压力、Postgres 多实例、自动策略调度恢复等仍未由本页证明。
- 跨刷新后原请求号的 UI 交接、细粒度错误/过期说明、完整订单状态机与原规划所有任务继续推进。无实盘、发布、远程 CI 或真实库迁移。
