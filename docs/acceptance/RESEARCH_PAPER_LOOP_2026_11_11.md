# 股票与CEX研究到Paper人工复盘 · 2026-11-11

状态：两市场受控业务API闭环通过；完整产品目标未完成。行情和报告提供器均mock，无真实账户、真实模型或浏览器交互验收。

## 已验证路径

通过真实FastAPI路由和领域服务：明确配置Paper账户与允许手动交易的测试标的 → mock行情导入 → 数据目录reviewed/trusted晋级 → ReportGenerator及报告评估 → 人工投资假设 → 引用报告的人工假设审阅checkpoint → 研究计划与五道门禁 → pending草稿 → 未审批执行拒绝且无成交 → 独立人工审批 → 带幂等键的Paper成交 → 按成交读取日志/复盘 → 保存并明确完成人工复盘 → 重新读取相同保存记录。

分别覆盖AAPL/USD股票和BTC/USD CEX现货；同一用户/同一隔离数据库连续运行两市场，确认账户、标的、来源快照、成交与复盘分离。同幂等键重复执行返回原成交，不增加成交数量。此处不是浏览器市场切换验收。

测试中为明确配置测试资产与风险规则进行了配置准备；不会把导入研究变成获准交易。首次测试确认只读导入标的默认未启用交易，服务端拒绝创建草稿，随后使用显式配置的Paper测试标的完成正例。模拟目录trusted仅用于测试门禁，不代表真实行情可信度。

命令：backend/.venv/bin/pytest（在backend目录使用.venv/bin/pytest）tests/test_terminal_research_paper_loop.py tests/test_paper_review_edit.py -q。结果5 passed in 1.57s。测试读取隔离数据库Quote价格用于构造票据，未新增或假称存在GET /quotes接口。

## HTTP启动验证

修复serve-paper-fixture.py的CEX预算硬编码user-1，改为当前fixture会话owner；仓库与外部终端脚本同步。使用新/tmp数据库启动8009，实际PID72500/会话90043；真实导入和评估生成两份mock报告。

HTTP检查：3个Paper账户、2份已评估mock报告、更新后的expected_updated_at复盘契约、0笔executions。检查后同句柄Ctrl-C正常退出0，8009临时服务已停止。没有替换8001旧研究fixture。未通过此HTTP检查宣称已用网络完成交易闭环；完整闭环由上述TestClient执行。

## 仍未验收

浏览器研究→票据预填→审批→成交→人工复盘的页面操作；跨市场/分屏/刷新期间的完整交互；真实只读来源和实际模型报告；所有二级页专门AI产物及旧功能逐项动态验收；生产部署。Live与钱包签名未开放，未发布。

验收补正：部分无新增意图断言原比较GET /orders/intents的405响应，现以隔离数据库计数替代并复跑。详见MANUAL_PAPER_THESIS_2026_11_11.md。
