# r127 跨阶段研究证据重验（2026-11-02）

本增量落实既有研究门在草稿、普通审批与 Paper 执行边界的证据复核；整体 T0–T7 开发目标继续，未启用实盘。

## 行为

研究门评估保存版本为 1 的 SHA256 指纹，绑定原报告、原快照、当前质量报告、当前可信目录记录、资产身份、订单证据引用和评估条件。保存的验证条件包含质量/研究阈值与缺失数据要求。数字在数据库 Numeric 往返后保持一致，UTC 时间统一；JSON 数字变成字符串等类型变化仍会改变指纹。

以下入口复核精确研究门，而非无条件采纳最近的新研究门：

- `DecisionGateService.require_all_gates_passed`：两条建草稿 API 的共同依赖，防止预览后、建草稿前证据已变化。
- `RiskEngineService._ensure_draft_approvable`：批准前继续重算账户风险，然后复核草稿绑定的研究门证据。
- `PaperExecutionService`：既有审批指纹/TTL、账户风险和报价检查继续生效，模拟成交前再次复核研究证据。

报告修订或删除、快照/资产身份变化、质量/目录记录改变或可信目录禁止交易，会阻止使用旧草稿。即使修订后的报告本身仍符合研究阈值，也必须重新预览、建立新草稿并由人明确审批。没有新指纹的历史门记录同样要求重新预览；不自动升级或重放交易。

普通批准指纹新增绑定订单 `evidence_json`；批准后改变引用同样失效。创建无关的新报告不会影响原本已选中的有效报告；追加/更换同快照的质量或目录记录则需重新预览。

每次复核保存 `research_evidence.revalidated` 或 `research_evidence.blocked` 审计；失败审计在返回 422 前已提交。未改数据库表结构或前端 UI。

## 文件与验证

- `backend/app/services/decision_gates.py`：证据指纹、原报告复核、审计及建草稿入口。
- `backend/app/services/risk.py`、`backend/app/services/paper_execution.py`：审批与 Paper 执行复核。
- `backend/app/services/approval_grants.py`：批准绑定订单证据引用。
- `backend/tests/test_research_evidence_revalidation.py`：25 项，包括三个阶段、七种失效情形，以及无关新报告、重新预览不升级旧草稿、新质量报告和订单引用修改。

先运行原相关回归 39 passed / 1 warning；新专项第一轮因测试 helper 未调用实际评估而失败，补齐评估后 21 项通过，再补数字类型变化及订单引用变更检查。最终全量 **804 passed / 1 warning（57.13 秒），退出 0**；密钥扫描及 diff 检查通过。结果与源码 SHA256 见 `R127_RESEARCH_EVIDENCE_REVALIDATION_RESULTS_2026_11_02.json`。

使用已有 Python 3.13 环境及当前仓库源码，不表示干净环境或远程 CI 已验收。本轮无前端改动，未重做浏览器端到端成交测试。依赖警告来自 TestClient 的 httpx 弃用提示。

## 边界与后续

- 本指纹用于检测可信数据库中证据内容变化，不是抵抗数据库控制者篡改的签名，也不是报告撤回/版本管理产品的完整实现。
- 当前检查与模拟成交之间尚无跨记录锁或数据库级快照事务保证，不能据此宣称并发条件下已消除所有时间差；Postgres/故障注入/幂等验收仍待完成。
- 本轮覆盖研究证据复核。完整 Thesis/Behavior/Constitution/策略政策的跨阶段状态重验仍需按规划完成，不由此页代证。
- LiveExecution 的准备/沙箱证明流程不是本轮 Paper 执行验收范围；真实账户与实盘适配器未启用/未验证。
- 既有历史 symbol-only 快照和通用报告仍受上一页说明的兼容边界约束；报价导入按 symbol 的来源资产映射问题仍待修复。
- 完整手动理由路径、真实行情、OIDC、生产部署与 113 项任务验收保持未完成。


## 后续增量

既有 Thesis/Risk/Behavior/Execution 评估器的建草稿、普通审批和 Paper 执行前重验见 `R127_DECISION_GATE_REVALIDATION_2026_11_02.md`，最终完整后端 840 项通过。该后续页更新本页关于其余门禁尚未接入的状态；未覆盖指标/政策字段及并发事务等仍待完成。
