# r127 普通订单与 Paper 的其余门禁重验（2026-11-02）

整体开发仍进行中。本页在研究证据重验的基础上，将现有 Thesis/Risk/Behavior/Execution 评估器接入建草稿、普通审批、Paper 执行前的当前状态复核，不代表所有策略/政策需求已完成。

## 实现

- `backend/app/services/decision_gates.py` 保存每个实际评估的输入条件；复核校验草稿绑定的精确 gate_id、订单归属、门类型、原通过状态及输入是否存在。旧门缺少可复核输入时，要求重新预览/新建草稿。
- 复核从原条件开始，重新读取服务器 Paper 账本、当前章程、预算、策略规则、Thesis 检查点、已保存的行为干预与报价/关联政策。审批和执行排除当前草稿的重复预留，保留其他已批准订单的资金占用。
- Thesis 显式引用丢失、跨资产或跨账户时阻止通过；状态失效、最新检查点弱化/失效等按既有门禁结果处理。复核不新增 ThesisViolation。
- 策略规则覆盖显式绑定的 Playbook 及 Thesis 绑定的 Playbook；两个引用冲突、Playbook 缺失或停用时阻止。最小 Thesis 置信度取实际存储值，未知时不默认通过；最大委托金额采用保守服务器估值。
- 行为门读取同一订单的已保存干预。BLOCK 和未知干预级别阻止；HARD_CONFIRM 需要非空回应与明确 bypass 标记；SOFT_WARNING 需要回应。无关订单的干预不串扰。复核不重新生成行为 pattern 或 intervention。
- 已关联 AutomationPolicy 缺失、停用或账户/资产作用域不符时阻止，原动作限制继续检查。
- `backend/app/services/demo_seed.py` 修复 NVDA 样例复用仅授权 AAPL 的政策，建立并绑定资产对应的独立模拟政策。
- `backend/app/services/risk.py`、`backend/app/services/paper_execution.py` 在既有研究证据重验后调用新复核。两条建草稿路径通过 `require_all_gates_passed` 使用相同守卫。
- 保存 `decision_gate.revalidated` 或 `decision_gate.revalidation_blocked` 审计；失败审计在 API 返回前提交，原通过门不被伪造为新通过结果。

无前端源码或数据库表结构改动，无实盘、外部 LLM 调用、发布或 Git 推送。

## 验证

新增 `backend/tests/test_decision_gate_revalidation.py` 36 项：三个订单环节分别测试 Thesis 停用/跨资产、失效检查点、章程禁止资产/资产类别限额、Playbook 停用、策略金额/置信度规则、行为 BLOCK、政策停用及政策跨资产；另验证 HARD_CONFIRM 显式回应恢复、无关干预隔离、重复复核不生成违规/行为记录，以及直接绑定 Playbook 无 Thesis 时置信度规则不会跳过。

原相关专项 64 passed / 1 warning（11.31 秒）；新增专项第一版 33 passed / 1 warning（7.40 秒）；首轮完整回归 826 passed / 11 failed（98.49 秒），均为演示 NVDA 错绑 AAPL 政策触发 EXECUTION_GATE 阻止。修复种子政策后相关 36 passed / 1 warning（8.42 秒），随后补三项政策跨资产检查并重跑完整回归。最终完整后端 **840 passed / 1 warning（67.03 秒），退出 0**；密钥扫描及 diff 检查通过。结果与源码 SHA256 见 `R127_DECISION_GATE_REVALIDATION_RESULTS_2026_11_02.json`。使用既有 Python 3.13 环境；非干净环境/远程 CI/浏览器端到端证明。警告为 FastAPI TestClient 的 httpx 弃用提示。

## 剩余范围

- 复核与成交之间的并发变化仍需数据库事务/锁/幂等及故障注入验证；没有宣称消除所有时间差。
- 本轮复用现有评估器，不代证其所有输入均已成为真实市场或账户事实。完整行为历史检测、月度回撤计算、政策限额/市场白名单等未覆盖字段仍需逐项审计完善。
- 现有行为干预仅按订单关联复核，尚非账户/用户全局的完整行为授权系统。BLOCK 不可通过回应绕过；历史软警告的回应语义以本页实现为准。
- 当前约束仍满足时，章程/策略文字修订不强制废弃草稿；完整不可变策略版本与授权快照属于后续规划。研究证据内容变化则继续按上一增量强制新建草稿。
- LiveExecution 准备/沙箱流程、真实账户、Postgres、完整生产/实盘验收均不由本页证明。
- 历史弱作用域、来源资产映射、无强制报告的手动路径、完整 UI/113 项任务验收继续保留。
