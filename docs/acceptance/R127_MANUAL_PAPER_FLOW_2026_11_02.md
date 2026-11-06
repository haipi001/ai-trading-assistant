# r127 无 AI 报告的手动 Paper 路径（2026-11-02）

整体规划继续进行。本增量完成原 Paper 票据的手动理由路径，适用于明确标记为 manual 的 Paper 限价订单；不意味着 Live/CEX 手动交易或全部 113 项已完成。

## 产品行为与 API

原票据新增“证据方式”：默认“手动理由 + 服务端行情（无需 AI 报告）”，仍可选择原有已保存报告。必须选择 Paper 账户和明确市场的资产，填写方向、正数量/限价和明确交易理由。报告/可选 Thesis 读取失败不再阻塞手动表单；账户或资产读取失败仍不能操作。

- `POST /orders/intents/{order_intent_id}/manual-evidence`（trade:preview）生成凭据。只接受已保存订单 ID，不接受客户端提供的报价、质量分数或执行资格。
- `GET /orders/intents/{order_intent_id}/manual-evidence`（read）读取持久化报价来源、价格、时间及有效期供恢复；损坏内容不作为有效回执返回。
- 服务端校验订单为 manual、Paper 账户、限价、正数量/价格及非空 user_rationale；拒绝信号来源、其他 source_type、Live、同时指定报告等不适用情况。
- 必须存在同 asset_id 的服务端报价，价格有限且为正、时间非未来且小于 900 秒。凭据有效至该报价时间 +900 秒，不能通过重新读取延长。
- 新表 `manual_trade_evidence` 绑定订单、租户、快照、报价、内容 hash 与到期时间。快照保存精确订单条款、理由及资产身份/报价原文。质量报告仅表示报价身份与时效符合本 Paper 用途，不表示研究结论已评估。
- 研究门只有校验该专用服务端凭据通过时才允许无研究报告；普通调用者的 research_report_required=false / quality_report_required=false 不再构成豁免。质量阈值至少 0.75，非手动凭据报告置信度阈值至少 0.5，仍可收紧。
- 仍经过五项门禁与服务器账户风控，预览后独立明确审批，再单独执行模拟限价单。原研究内容指纹、审批条款/TTL、当前门禁和报价重验继续生效。
- 改条款/理由/原报价、篡改快照、凭据到期、跨订单或跨租户复用均不能凭旧资格执行。新凭据不自动批准或成交。
- 原票据显示手动行情来源与有效期；刷新后可恢复原凭据/成交，切换标的或身份会使旧请求链失效，错误标的无法恢复草稿。

## 文件与迁移

- `backend/app/models/core.py` / `models/__init__.py`：租户隔离的 ManualTradeEvidence。
- `backend/alembic/versions/20261102_0024_manual_trade_evidence.py`：新表与索引，前序 0023。
- `backend/app/services/manual_trade_evidence.py`：凭据生成、校验、历史读取与审计。
- `backend/app/services/decision_gates.py`：专用凭据与服务端派生报告要求；保留普通报告路径。
- `backend/app/api/paper_execution.py`、`backend/app/schemas/core.py`：两条有权限的 API 与类型化响应。
- `src/paper-order-workflow.js`、`src/paper-order-ticket.jsx`：原位表单、显式请求链、来源显示和恢复；无新替代页面。
- `backend/tests/test_manual_trade_evidence.py`、`backend/tests/test_trade_permissions.py`、`scripts/check-paper-order-workflow.mjs`：正向与绕过/权限/租户测试。

## 验证

- 初版新后端专项 20 passed / 1 warning（2.44 秒），后补其他租户、viewer 权限与损坏回执读取用例。
- 首次完整后端 882 passed / 1 warning（71.01 秒）；补损坏凭据读取检查后最终 **883 passed / 1 warning（79.45 秒），退出 0**，新增后端共 23 项。密钥扫描与 diff 检查通过，结果见对应 RESULTS JSON。
- 前端 54 个模型脚本全部通过；615 按钮/253 表单控件及处理器通过静态审计，10 导航/59 频道及原控件保留守卫通过。
- 构建成功（4.03 秒），仅既有大 chunk 提示。
- SQLite 迁移守卫通过：单 head、空库升级、模型 parity、降一级、再次升级。未测试 Postgres 或真实用户数据库迁移。

### 实际浏览器与数据库证明

在新建的独立 SQLite 数据库、临时后端 8001、当前原 UI 3002 上使用 demo_seed 合成行情和模拟资金。AAPL/NASDAQ/USD，数量 1、限价 225.12，明确“不选研究报告、不调用模型、仅模拟资金”的理由：

1. 默认手动方式，研究报告选择框禁用；生成服务端行情凭据，五门 PASSED，草稿 pending 且执行按钮禁用。
2. 单独点击批准，显示 approved；再点击执行，显示 paper_filled、执行禁用和费用回执。
3. 刷新后在 SOL 工作区恢复 AAPL 草稿被拒绝，返回 AAPL 可恢复手动方式、原凭据和回执。
4. 独立查询 SQLite：草稿 `cceebf95-caf7-4119-9c0a-925eb4b8b703` 仅一笔成交；quantity=1，price/notional=225.12，fee=0.022512，cash_effect=-225.142512；RESEARCH_GATE 的 research_report_id 为空、manual_evidence=true。两份研究报告均为初始 seed，不是本流程新生成。integrity_check=ok。
5. 临时服务 SIGTERM 后记录 Application shutdown complete / Finished server process；端口 8001 无监听。执行会话退出码 143（由 SIGTERM 结束），不将它记为退出 0。保留临时测试库，未改真实账户/凭据或删除用户数据。
6. 原 SOL/币安/1小时选择已归还，临时浏览器标签关闭。

截图：`output/r127-manual-paper-20261102/restored-manual-paper.png` 和 `restored-manual-paper-receipt.png`。截图主图属于原终端显示；订单凭据使用独立后端的 mock 数据，不能把主图价格当作订单报价或真实成交证据。

## 仍未完成

- 手动凭据当前仅 Paper 限价；Live、真实券商/交易所、人类身份的不可伪造证明、真实生产验收仍未完成。带 source_type=manual 的授权 API 调用仍需显式审批，不能据此宣称可辨别自动客户端与真实人类。
- 本轮实际浏览器使用合成报价；未验证真实行情、真实 OIDC、Postgres、并发/幂等、断网结果恢复或跨标签同时操作。
- 手动理由路径仍需要章程/预算等既有门禁配置和有效报价；不是取消风控或允许不明数据下单。
- 900 秒凭据和审批 TTL 独立，任一个过期都会拒绝；UI 仍需改善具体阻止原因、过期提示和重新预览交接。服务器不自动重试成交。
- 历史凭据内容 hash 不抵抗数据库管理员同步篡改表与快照；财务事务/来源认证/完整策略版本授权问题沿原规划保留。
- 无完整 UI 全页面验收、远程 CI、Git 推送、部署或实盘启用。本次新交互已验证，但不以静态通过数宣称 113 项完成。


## 后续事务增量

本页 Paper 执行的同账户并发、原请求号恢复及事务回滚已由 `R127_PAPER_ATOMIC_EXECUTION_2026_11_02.md` 增量验证。其他账户写入、跨刷新请求号交接、Postgres及完整故障/生产范围仍保留，未将“幂等”外推到实盘。
