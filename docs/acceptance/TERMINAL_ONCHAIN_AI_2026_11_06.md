# 链上AI引用附件 · 开发与受控验证

状态：服务端与前端合同已实施，原生浏览器动态验收未完成；不代表完整Web3研究闭环。

聊天POST /production/human-control/llm/chat新增可选onchain_context引用对象：schema_version=1、snapshot_id、wallet_id、chain_id、contract_address、context_version、allowance_ids、protocol_ids。两个记录列表分别最多20个唯一ID；拒绝客户端直接提供余额。服务端重新读取当前用户活跃且链匹配的钱包，核对带读取审计的来源快照、钱包地址、链合约、10分钟时效及之后的读取失败。上下文版本冻结客户端提供值，不宣称后端知道当前浏览器焦点。不能同时附带股票/CEX图表材料。

沿用原配置、预算及preflight门禁。冻结research_chat_onchain_context快照，回答只能引用本次W1、A/P条目；结构、身份和引用校验通过才保存validated_reply。来源包和回复通过GET /production/human-control/llm/chat/onchain-context/{snapshot_id}取回，沿用readiness:read且限制当前用户。该材料不进入普通数据源列表、不提升为交易可信数据，也不是经过完整独立评估的ResearchReport。历史授权/协议可能陈旧或为示例；无完整索引或USD估值。

前端提供显式附件勾选、公开钱包数据发送说明、历史上下文标记及来源展示；版本/身份变更撤销附件选择，回包展示身份必须与引用和W1一致。未进行本增量的浏览器动态验收，也未调用真实付费模型。

受控检查：89项相关后端通过，1依赖弃用提示。包括正常冻结回复取回、跨用户拒绝、来源过期、伪造引用/模型异常不保存有效回复、配置未就绪不构造Provider。此前43整合、55模型组和终端构建通过；本轮仅增加后端故障测试，未重复构建。

仍需：原生附件勾选/发送、切换中晚到回复、刷新后的产物入口、黑白动态状态、真实模型与独立报告评估、股票/CEX研究至Paper及全量旧功能验收。完整目标active，旧版备份保留，Live关闭。


## 2026-11-06 链上研究历史入口
新增当前用户/钱包/链/合约范围的最近20条服务端材料列表（has_more提示）及页面读取入口，展示原上下文和有效/失败回复，不自动附带新研究。列表使用readiness:read权限及用户过滤，后端89项相关测试通过，新增同用户列表命中、跨用户和跨链空列表断言。55模型组通过，终端构建通过；修复读取新范围时不能短暂沿用旧列表。原生浏览器与完整评估仍未验收，目标active，Live关闭。


## 2026-11-06 历史入口响应合同补齐
列表增加数量、唯一ID、时间、上下文版本、状态和权限校验；详情增加来源身份及回复状态/引用校验，失败或未完成记录不能附带有效回复。异步读取同时核对请求实例，较早回包不得覆盖新请求。44整合测试通过，55模型组和终端构建通过；原生浏览器验收仍待继续，不计完整闭环。


## 2026-11-06 研究历史HTTP权限合同
新增真实FastAPI/TestClient路由验证：未认证401、认证用户不可被本地头覆盖、跨用户详情404、跨链列表为空，失败产物无有效回复且execution_available=false。查询参数增加钱包长度、链ID和合约格式校验，非法值422。相关后端90项通过（1依赖弃用提示）；并非浏览器动态验收。完整目标继续，Live关闭。


## 2026-11-06 历史回复内容完整性
补齐历史页的有利/不利情景、风险、研究建议及模型自报置信度。后端保存原结构化建议与置信度，前端核对类型与范围；明确研究建议不执行、置信度不等于事实核验。90相关后端、44整合、55模型组与终端构建通过。原生浏览器及完整目标仍未验收，Live关闭。


## 2026-11-06 授权及协议证据明细
研究来源展示补齐授权合约/spender/额度/记录风险，以及协议类型/合约/历史估值；明确无撤销授权或签名操作。前端交叉校验A/P引用与所选记录ID、数量、类型、合约与额度，防止来源列表仅显示抽象ID。45整合、55模型组、终端构建通过；完整实时索引及原生动态验收仍待完成。目标active，Live关闭。


## 2026-11-06 账户隔离与受控链上AI验收环境
原生浏览器在同一AAPL/股票只读上下文切换账户：第二Paper账户数量和理由为空，切回原账户恢复数量7及受控理由。截图位于terminal-ui/evidence/paper-second-account-empty-20261106.png与paper-original-account-restored-20261106.png。此验收仅覆盖未提交表单隔离，不代表服务端审批、成交或完整闭环。
serve-onchain-fixture.py新增显式--research，禁止与--public-probe并用。仅挂载四个原有研究chat/status/历史/详情路由，保留真实HumanControlService快照、引用、预检逻辑，用本地明确标注受控Provider替代外部模型，临时假凭据独立写/tmp。支持ai-fail/ai-invalid/ai-delay控制，订单接口不存在。
HTTP实际验证：受控W1响应成功、历史记录匹配；W999无效引用失败且validated_reply=null；订单路由404。证据onchain-ai-fixture-http-20261106.json。py_compile通过。尚未完成浏览器AI发送/历史/晚返回验收，不算真实模型验证。
当前临时Web3 AI fixture为PID11438、执行会话85911、端口8002、数据库/tmp/terminal-onchain-ai-20261106-b.sqlite、控制文件同前缀.control，已确认运行。旧Paper fixture端口8001仍用于页面，切换后端前需清理当前受控输入，避免修改生产配置；下轮先核实进程/句柄，勿重复启动。tab4保留。整体目标active，旧版备份保留，Live关闭，无提交部署。


## 2026-11-06 原生链上AI材料与历史验收
上一轮属于progress（账户隔离原生证据与受控fixture实现）。本轮已读完整目标，继续原生页面验证。旧fixture9458/11438均通过其原会话CtrlC确认正常结束；新research fixture进程通过会话28830运行在8001，数据库/tmp/terminal-onchain-ai-20261106-c.sqlite，控制文件同前缀.control。不重复启动；下轮先核实活跃会话。
原生tab4选择Base钱包时旧身份被后端404拒绝，刷新账户后绑定fixture-base成功，读得区块21000000/ETH精确2。页面准备附件，显式发送受控问题，真实chat handler与HumanControlService生成冻结研究包/W1引用；历史列表、详情读取成功，显示原上下文、风险、未知、模型自报置信度及不可交易边界。刷新后同钱包可读取保存的研究。黑白主题切换保持材料和历史。截图terminal-ui/evidence/onchain-ai-history-dark-20261106.png、onchain-ai-history-light-20261106.png、onchain-ai-reply-light-20261106.png。
页面发现AI标题误继承旧AAPL，main.jsx已修正嵌入AI symbol取terminalContext.instrumentId，缺失时为空，不回退旧marketSymbol。build:terminal最终成功（仍有大bundle警告），原生刷新复查标题未选标的、链8453附件与W1内容正确，不再出现AAPL。首次构建前路径错误已更正并重新构建，不将旧构建算修复验证。
Paper受控输入已通过页面清空；订单意图/执行计数均0。tab4保留，当前Base/只读/黑色主题，研究历史详情打开。切换中返回、失败展示、完整股票/CEX研究到Paper与逐项迁移验收仍未完成。无外部模型调用，无生产数据库变更，无提交部署，Live关闭，完整目标active。


## 2026-11-06 原生失败与跨市场延迟返回
用户续作完整目标；上一轮为实际页面材料/历史/主题验证及标题修复progress。本轮已读目标并轮询原会话28830，确认Web3研究fixture PID11700仍运行，未重启。
将临时控制文件设ai-fail后通过页面发送：明确模型/响应验证失败alert；历史出现failed，详情“该请求未保存有效回复”。SQLite对应ceca056f的validated_reply为空。设置ai-delay后页面发送，工具在约0.7秒内切换到股票，收到pending时原Base材料已冻结；股票页没有旧Base附件/回复。服务端完成后返回Web3，读取最近历史，6c4c17fe的回复仍绑定fixture-base/链8453/上下文1/来源快照30176e23，当前全局上下文已更新，不自动成为新附件。保持原链研究可读。
尝试链ID文本输入时仅DOM值变更、未得到上下文切换证据，不将该尝试记作链切换验收；后续仍需直接链切换/钱包变化覆盖。此次通过的是跨市场切换、服务端持久化和回原上下文读取，不是跨iframe持续显示聊天或持久任务取消恢复。
证据terminal-ui/evidence/onchain-ai-failure-20261106.png、onchain-ai-return-after-market-switch-20261106.png、onchain-ai-failure-switch-20261106.json。数据库订单意图0、执行0。控制文件已恢复ok，fixture保持会话28830/8001以供后续；tab4已handoff保留，当前Base只读黑色历史详情。未修改产品源代码，无外部模型调用，无提交部署。整体目标active，股票/CEX研究-Paper闭环、逐页AI和全部功能验收仍待完成。
