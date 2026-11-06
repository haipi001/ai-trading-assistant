# r127 研究证据身份增量（2026-11-02）

目标继续进行；本页仅覆盖研究门评估时的报告/快照/订单资产一致性，不代表 T0 或整体规划完成。

## 行为与文件

- `backend/app/services/decision_gates.py`：订单持久化证据中的 `report_id` 或 `research_report_id` 优先绑定实际报告；两个引用冲突、指定报告不存在、报告引用其他快照或其他资产均阻止研究门通过，不再悄悄改用最新报告。没有指定报告时，只允许同快照且同资产或通用报告作为候选。
- 同服务仅从快照成功导入的 `quotes` 行判断市场覆盖；请求的 symbols 不作为已成功证据。行必须匹配 symbol，存在 asset_id/venue/currency 时也必须匹配。多资产快照可支持其实际覆盖的资产。
- `backend/app/services/data_sources.py`：新报价导入将内部 asset_id、venue、currency 与 symbol 一起保存在快照报价行；没有数据库 schema 改动。
- `backend/app/services/demo_seed.py`：补齐 NVDA 独立合成报告，避免演示 NVDA 草稿依赖 AAPL 报告；情景正文明确为模拟，不调用模型或外部交易服务。
- `backend/tests/test_research_evidence_identity.py`：12 项用例，覆盖两种引用字段、丢失/冲突引用、跨快照/跨资产、回退候选、错误报价身份及合法多资产快照。

## 验证

- 首轮相关测试 30 passed；完整回归曾为 766 passed / 11 failed，失败均来自演示种子共用 AAPL 报告支持 NVDA。保留失败日志 `/tmp/r127-research-identity-full.log`，修复演示资料而没有豁免门禁。
- 修复后专项：15 passed / 1 warning（4.09 秒），覆盖新增身份测试、演示种子与研究到订单追踪。
- 最终完整回归 **779 passed / 1 warning（78.69 秒），退出 0**；密钥扫描与 diff 检查通过。结果见同目录 `R127_RESEARCH_EVIDENCE_IDENTITY_RESULTS_2026_11_02.json`。
- 使用已有 Python 3.13 环境和当前仓库源码执行；不是全新环境安装或远程 CI 验证。警告来自 FastAPI/Starlette TestClient 的 httpx 弃用提示。
- 本轮无前端源码改动；未重复浏览器 Paper 成交验收，也不将上轮浏览器证据当作本轮服务端改动的端到端证明。

## 限制与下一步

- 历史快照仅有 symbol 时仍按 symbol 匹配；无 quotes 的宏观/其他数据集不强制资产覆盖。通用（asset_id 为空）研究报告仍允许使用，完整证据作用域契约尚待完善。
- 新快照身份来自当前资产映射；报价导入服务仍按 symbol 查找资产，不能据此宣称跨 venue 同名资产的来源映射已可靠。需要单独修复资产标识/连接来源/平台的映射契约并补迁移策略。
- 本轮核对发生在研究门评估时。草稿、审批、执行仍依赖已保存研究门结果；报告/快照在评估后被修改或撤回时的再次验证与完整证据指纹，属于后续必做项。不能将当前结果视作跨阶段不可变证据保证。
- 真实行情与交易账户、Postgres、并发幂等、OIDC、无强制报告的手动理由路径、完整 UI/113 任务验收均未由本页完成。实盘默认关闭，无外部 LLM 调用，无发布或 Git 推送。


## 后续增量

普通草稿/审批/Paper 执行的研究证据内容指纹和重新核验已在 `R127_RESEARCH_EVIDENCE_REVALIDATION_2026_11_02.md` 实现并以 804 项完整后端回归验证；本页关于跨阶段研究重验的待办由该后续页更新。并发事务、其他门禁及来源映射等限制仍按各页保留。
