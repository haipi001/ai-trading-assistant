# 15｜环境、上线与生产应急流程（只读/模拟/真实分离）

## 1. 环境拓扑

| 环境 | 用途 | 数据与凭证 | 真实交易 |
|---|---|---|---|
| local/dev | 前端/UI+单元测试 | fixture、SQLite/本机 Postgres、Mock provider | 禁止 |
| integration | GitHub CI | 合成密钥/Mock Broker、无外网账号 | 禁止 |
| staging | 完整真实授权 API 检查、Sandbox/Paper、后台任务 | 独立 Postgres/Redis/本机加密 secrets | 默认为禁止 |
| production | 真实用户和账户 | 独立数据库、受控 HTTPS、Secret Manager、KMS/受限文件 | 仅用户显式开启的某一账户/模式 |

**GitHub Pages 仍仅可托管前端静态资源**，不能充当交易执行服务。采用同域 HTTPS 网关/BFF 是建议的后续部署方案，特别是认证 Cookie 和 WebSocket/SSE 跨站权限问题。所有交易 API 必须留在授权的后端。

## 2. 生产开关与操作权限

- `LIVE_TRADING_ENABLED=false`、`LIVE_EXECUTION_ENABLED=false`、`LIVE_EXECUTION_DRY_RUN_ONLY=true`、`AUTOMATION_LEVEL=A0_READ_ONLY` 作为默认初始化值。
- 解除实盘需要：全量 CI、安全审计、管理员明确授权、适配器白名单、用户/账户级选择、最小额度/风险配置和经过证据验证的 Sandbox。
- 生产 `MANAGED_AUTH_REQUIRED=true` 应结合真实会话策略、前端登录/登出、CSRF 保护、RBAC、租户隔离和速率限制全链路验收，不能只编辑 YAML。
- 交易适配器/Secret Manager 权限区别于研究 Worker；自动化策略只拥有受限调用执行协调器的能力，不能读取原始 Key。

## 3. 上线运行手册

1. 确认干净工作树、代码审查、明确 commit、可回滚版本；环境变量清单由运营管理员维护，**不放任何密钥到 ZIP/仓库**。
2. 生产数据库备份+迁移 dry-run/upgrade/downgrade 或恢复演练，验证 `alembic` 迁移顺序和历史用户归属。
3. CI：backend pytest（含 mcp optional extra）、migrations、front models/interaction、E2E、dependency audits、secret scan、API contract test 全绿。
4. 在 staging 回归：登录/跨用户资源、币种/订单模式分隔、Agent 研究/费用、执行网关订单与故障注入。
5. 部署数据/行情/Agent 服务，先保持 LIVE=false，检查服务健康、来源、时钟同步、行情时效、Private Broker 只读连接。
6. 单一账户执行人工小额 Live 验收，保存脱敏真实订单/成交/费率/仓位对账；在明确用户同意下进行。未通过不可扩展交易权限。
7. 开启白名单用户，逐步扩大至可控范围；优先配置监控和人工值守，设置紧急终止入口。

## 4. 不同故障如何响应

| 情况 | 后端措施 | 用户 UI | 恢复要求 |
|---|---|---|---|
| 行情断线/报价过期 | 禁止基于过期报价新增执行 | 图表保留历史、明确 STALE | 新行情校验/序号恢复 |
| Agent LLM 超时或额度尽 | 任务失败/取消/排队，不影响订单状态 | Ace Tasks 显示失败/重试/费用 | 人工恢复任务 |
| Broker API 提交超时 | 持久记录 UNKNOWN，按 client ID 查询 | 订单待核实；禁止自动同单重发 | 对账确认是挂单/已成交/失败 |
| 私有 WebSocket 断线 | 暂停自动策略新单、轮询对账 | LIVE 连接退化提示 | 恢复订阅并补齐事件 |
| Redis/Worker 重启 | 从 DB/outbox/checkpoint 恢复 | 明确后台处理中 | 保证不重复交易与不丢资金事件 |
| 账本与交易所不一致 | 开告警/限制新策略单 | 资产显示对账失败及最近快照 | 人工/程序纠错留审计 |
| 密钥泄露或异常交易 | 全局/账户 Kill-switch，吊销密钥 | 高优先级安全通知 | 轮换/冻结/调查后重新授权 |

## 5. 必须长期有的操作工具

- 按账户/策略暂停开新单；查看并处理已挂单（不将 kill-switch 误等于自动撤掉全部已挂单）。
- 查询同一 clientOrderId 在交易所的状态、重新对账、导出审计证据、验证最近备份、查看上次执行版本。
- 统计回调延迟、错误率、未知订单持续时间、账户/报价时效、Agent Token/成本、策略任务积压；异常状态能直接定位到资源 ID。

## 6. 版本与部署回滚

新前端 UI 回滚不能导致后端订单/账本丢失；API schema 需兼容至少一个发布窗口。部署失败采用灰度回退；DB migration 回退需考虑有无不可逆数据迁移。恢复后应先完成订单和账户对账，再开放实盘。
