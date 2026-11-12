# 所选账户账本研究 · 2026-11-11

完整目标继续active。上一轮逐页契约及权限状态修改属于progress；本轮不是全部后端、真实账户或完整交付验收。

## 数据与调用

新增所选账户的应用账本研究材料。服务端按认证用户与Account.user_id校验归属，复用工作区的账户/市场分类；显式读取该账户的Position及公开Asset标识，不调用旧PortfolioSummary的估值更新，也不刷新券商/交易所余额。不发送账户名称、凭据或私钥。数量/成本/记录价格及估值保留十进制字符串，不转换为JS浮点。记录更新时间不是报价时间，quote_as_of=null、valuation_verified=false及valuation_freshness=unknown明确保留；默认零值不等于真实零暴露。最多20条，显示总记录数和截断，不计算跨币种总值、实时收益或跨账户分布。

来源冻结到现有DataSnapshot，记录读取审计、内容hash及账本revision。发送只提交reference，服务端重新核对所有权、市场、原上下文、审计、10分钟材料有效期以及当前账本revision；变化/过期/伪造引用在构造Provider前失败。开始模型调用后保存不可变研究包，期间账本改变也不重绑原回答；下次发送需重新读取。

研究仍走原配置、权限、预算、preflight与结构/安全/身份/引用校验。采用既有portfolio_daily_review输出分类但只审阅所给账本，不推断每日行情、实时估值或收益。H1表示账户账本范围、H2及以后表示记录；引用与文本不一致则保存failed及validated_reply=null。可选附带当前用户缓存资讯（N引用），暂不与行情或链上附件同发。普通未选账本的聊天不会增加新body字段，兼容旧后端。

这些材料/回复不创建ResearchReport或Agent执行任务，不经过正式报告评估和数据可信晋级，不能进入交易门禁。新source/reply快照从普通数据源清单排除，测试确认DataCatalog不信任它；不创建订单、审批或执行。

## API

- POST `/production/human-control/llm/chat/portfolio-context/prepare`：typed PortfolioPrepare，account_id、market(stocks/cex)、context_version；requires readiness:read。
- POST `/production/human-control/llm/chat`：可选portfolio_context仅为上述reference，requires readiness:write；不接收浏览器余额。
- GET `/production/human-control/llm/chat/portfolio-contexts?account_id=...&market=...`：当前用户/账户/市场最近20条与has_more。
- GET `/production/human-control/llm/chat/portfolio-context/{snapshot_id}`：原问题、材料、原资讯及完整/失败回复；所有权过滤、no-store。

沿用Account/Position/DataSnapshot/AuditLog现有表，无迁移。资料准备会写只读观察与审计，viewer能读自己的记录但不能调用模型。

## 前端

AI面板增加读取、预览、显式勾选账本材料及历史恢复。已校验兼容账户才可读取；准备不会自动发送。页面动作要求相应材料，额外未声明材料被拒绝。单账户账本可供首页/所选账户组合研究使用；API账号分布保持独立未接入状态，不能用单账户摘录替代跨账户汇总。当前注册表134条需审阅、70条分析/风险动作仍缺资料，数字不代表全部功能可用。

会话隔离另加防护：用认证用户及不含凭据的会话身份区分消息，渲染时立即过滤旧/未知身份内容；身份变化清除材料与准备，晚到旧请求的回复、错误及通知不再进入新会话。历史读取按新身份立即隐藏旧内容，未完成的旧读取不得回填附件。已知材料失败不再错误地永久关闭模型配置状态，重新读取后可重试。

## 验证

113项相关后端测试通过，包含股票/CEX真实FastAPI路由的准备/发送/恢复、成功/失败、匿名/跨用户/市场拒绝、viewer只读、精确数量、20条截断、账本变更、过期/损坏、混合材料拒绝及资讯联合引用。77项终端测试通过，含真实异步发送函数在换用户后丢弃旧回复/错误、前端材料和历史校验、引用重绑及旧后端body兼容。55组模型脚本通过。静态保留3份导航约定/845控件，不代表运行时全验收。秘密扫描和build:public通过，legacy保留，既有大包警告不变。

已确认先前受控进程正常结束后换用新临时数据库/服务，原数据文件保留。独立uvicorn实际HTTP验收：股票/CEX分别成功、异常、伪造引用；延迟模型期间改变临时账本，原产物保持旧数量、旧reference再用在Provider前blocked，刷新可得新记录。7份实际回包通过前端校验器；order_intents、order_drafts、executions均0，执行路由不存在。证据PORTFOLIO_RESEARCH_2026_11_11.json含启动源码hash及真实回包，全部为明确标注的受控假账户/记录，无付费模型和真实余额访问。

新增/修改源码：services/research_portfolio_context.py、account_identity.py、human_control.py、data_sources.py；api/production.py、workspaces.py；src/research-portfolio*.js/.jsx、portfolio-research-*.js/.jsx、research-request-scope.js、research-ai.js、research-ai-chat.jsx/.css；terminal-ui的PageAI契约、注册表、fixture及HTTP探测脚本和测试。

可复现：backend目录执行本轮九个相关pytest文件；`node --test terminal-ui/tests/*.test.mjs`；`npm run test:models`；`npm run build:public`。临时fixture启动后运行 `check-portfolio-research-http.py --control-file <tmp/control> --database <tmp/research.sqlite> --output <tmp/portfolio-artifacts.json>`，仅允许loopback及明确受控数据库。

## 未完成

浏览器getState再次连接超时，未完成原生点击/刷新、主题和全部英文化验收。本机8001为临时受控服务，不是生产后端；没有提交、推送或部署。真实交易所/券商余额、独立估值、多账户汇总/转账去重、订单/复盘专用材料、正式报告评估及完整研究到Paper闭环仍需继续。Live关闭、Web3只读。
