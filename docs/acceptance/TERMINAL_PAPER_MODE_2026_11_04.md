# 新终端 Paper 模式与受控订单验证 · 2026-11-04

状态：受控手动理由流程通过，完整整合目标未完成。旧版和完整备份保留，Live关闭，无提交/推送/部署。

## 实现

全局模式明确选择只读/Paper；Web3仅只读，Live禁用。切市场、账户、钱包、登录身份、刷新或恢复布局均不能继承执行权限。锁定面板仅锁定研究对象，其Paper权限受当前全局市场/账户/钱包约束。

嵌入面板API在发出交易变更请求前检查模式；即使共享HTTP桥接缺失也不回退绕过只读。服务端既有门禁、风控、审批、幂等执行继续有效，前端模式不授予服务端权限。

未提交票据按用户、市场、标的、场所、链/合约及账户暂存在父页面内存，切回可恢复表单；不暂存服务端审批或执行授权。身份变化清空缓存。此缓冲尚不支持跨刷新恢复未提交表单。

修正股票下单标题误加USDT后缀；Paper票据长文本和按钮支持侧栏换行。完整暗色视觉及窄屏回归未完成。启动器改用scripts/serve.py，仅监听loopback并发送Cache-Control:no-store，避免开发模块缓存影响联调。

## 实际浏览器与数据库证据

使用scripts/serve-paper-fixture.py启动独立临时SQLite/mock报价后端（端口8001）。只挂白名单业务路由，不提供Live/自动执行路由，不读取本机连接凭据，不运行调度器/真实模型。修复当前FastAPI嵌套路由包装导致旧白名单筛选错误，改从各业务模块路由构建测试App。测试后端已经停止。

1. 股票AAPL只读票据准备：账户A输入1股、限价225.12和明确受控测试理由；预览按钮禁用。
2. 切账户B：标的/数量/价格/理由为空；切回A：原表单恢复。
3. 明确切Paper，重新打开票据并预览：服务端mock报价凭据、五道门禁PASSED，草稿pending，执行按钮禁用。
4. 单独批准：approval_status=approved；随后单独执行：paper_filled，执行按钮禁用。
5. 数据库：1笔executions、1条order_drafts、1条trade_journal_entries、1条post_trade_reviews；USD现金99774.857488，AAPL数量1，含费成本225.142512。关键审批、执行、门禁、持仓、日志、复盘审计存在。
6. investment_ledger_entries为0；不能称统一投资账本闭环已经通过。后端Paper使用positions与交易日志，这一边界后续需核对。
7. 刷新恢复只读；可以读取已成交草稿及回执，审批/执行仍禁用。锁定MSFT研究面板后全局切CEX，面板仍MSFT但只读。

证据：terminal-ui/evidence/paper-controlled-20261104.json、paper-controlled-20261104.jpg、paper-readonly-restored-20261104.jpg。数据库/tmp/terminal-paper-browser-20261104-c.sqlite只含受控测试数据。

## 检查与限制

node --test terminal-ui/tests/*.test.mjs：23通过；npm run test:models：55组通过；npm run build:terminal及npm run build通过，仍有大bundle提示；Python编译与启动脚本语法检查通过。

本次未重跑此前117项后端隔离测试；未修改产品后端逻辑。原型行情侧栏仍显示明确SIM/DEMO数据，不代表真实行情；受控fixture没有candles路由，图表显示HTTP404/不可用，没有生成演示K线。

这不是股票研究到Paper全链：仅手动理由+mock报价。CEX Paper、真实模型、Web3只读数据与链合约身份、全局账户选择、每市场布局记忆、跨刷新未提交票据、超时/中途切换/重复执行浏览器故障路径、全部949控件和视觉验收仍待完成。


## 2026-11-06 Paper研究与成交复盘连接
上一轮为原生失败/延迟跨市场证据progress；本轮已读完整目标，推进研究到Paper和复盘连接。
serve-paper-fixture.py新增--research：通过真实mock数据导入、目录reviewed/trusted晋级、ReportGenerator和报告评估器准备AAPL研究报告，不直接插入假报告。一次真实启动8003/PID13744/会话42362成功，报告bb90beab与来源3a6f635e已生成。验证完后通过同会话CtrlC正常退出（终态exit0），当前8003不应再复用旧句柄；后续需用新/tmp数据库启动更新源码。链上fixture会话28830/8001上轮确认运行，本轮未停，勿未经检查重复启动。
新增GET /paper-executions/{execution_id}/review-context，read权限，仅当前用户Paper成交，要求原草稿、同用户日志和复盘关联完整；未找到成交404，关联不完整409。响应execution/journal_entry/post_trade_review/execution_available=false。无新数据库字段或迁移，无执行能力。
发现服务将PostTradeReview.user_id设为审批人字符串，现继承execution.user_id，审批人与数据所有权分开。旧有不匹配历史没有自动重写；新接口会返回409，需后续迁移评估，不虚称全部历史兼容。对应策略本fixture用户从human-user对齐default-user，保留审批人human-user，避免原fixture跨所有者错误。没有删除或绕过归属校验。
前端paper-order-ticket.jsx新增每笔模拟成交“查看此成交的日志与复盘”，按成交ID读取，再核对草稿、成交、日志、账户、资产和不可执行标志；上下文/表单/草稿变化清空旧详情。展示真实日志、待人工复盘状态和问题，不把自动日志当作人工复盘完成。页面动态验收尚待做。
验证：build:terminal通过（保留大bundle警告）；Paper成交/原子性/新上下文三文件25passed，新增日志归属不匹配409断言后单文件再次1passed，均仅Starlette弃用警告。初始两项策略本fixture归属回归失败已通过对齐真实所有者修正并复跑通过。命令路径错误已更正，未将失败命令计为通过。
完整股票/CEX研究-Paper页面闭环、复盘编辑保存、全功能和逐页AI仍未完成。无实盘，无外部模型，无提交部署，目标active。
