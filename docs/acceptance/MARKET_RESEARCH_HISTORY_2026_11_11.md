# 股票／CEX 行情研究历史 — 2026-11-11

本轮推进完整 terminal-ui 整合目标中的“研究跨页保留原始快照与产物”。上一目标轮已修改权威代码，属于 progress；本轮核实原测试句柄缺失后重新执行，继续完成契约和路由验证。完整目标仍 active。

## 实现

行情研究在现有 DataSnapshot 元数据内保存原问题、页面／标的标签、响应风格、模型来源、回复状态以及仅在验证通过时保存的结构化回复。既有快照无这些字段时显示未保存完整回复，不补造历史结果。没有数据库表结构变更，因此无需 migration。

新增 GET `/production/human-control/llm/chat/market-contexts`，可选 `symbol`（最多24位证券标识）及 `market_type`（stock/spot）筛选；返回当前认证用户最近20条记录和 has_more。只要求 readiness:read，返回 execution_available=false 与 Cache-Control:no-store。既有 GET `/production/human-control/llm/chat/market-context/{snapshot_id}` 增加上述历史字段及原新闻快照；新闻必须同属当前用户，否则拒绝。研究 POST 仍走原配置、预算、preflight、结构及引用校验，不增加模型或交易权限。

AI 对话面板新增“已保存行情研究”折叠区，支持显式读取列表和详情，显示原问题、原始 K 线范围、来源、模型与引用、看多／看空、风险、建议、限制及模型自报置信度。来源标为原请求；研究建议不触发操作。历史不自动加入新对话／附件，不代表当前报价或当前账户持仓。账户数据没有被这条路径读取；目前历史的持久范围是用户＋行情身份，而非账户快照。

请求实例和工作区身份双重核对，切换身份后不能重新显示前一列表；较晚响应不能覆盖新范围。前端核对所选记录的 snapshot/request ID、标的、市场、场所、币种、周期、材料类型、OHLCV、统计与引用；失败／未知状态不得携带有效回复，原资讯链接需通过安全 URL 校验。

## 文件

- backend/app/services/human_control.py、backend/app/api/production.py：持久化、列表与详情。
- src/market-research-history.js / .jsx：契约与界面；research-ai-chat.jsx / .css：入口及发送说明。
- src/research-market-ui.jsx、src/research-news-context.jsx：历史来源标签。
- backend/tests/test_market_research_history.py、test_market_history_http.py 与 terminal-ui/tests/market-history.test.mjs：新增回归。

## 验证与边界

86 项相关后端测试通过，含真实 FastAPI 路由的股票／CEX 成功和失败持久化、匿名拒绝、跨用户拒绝、伪造本地用户头不生效、旧记录及外部新闻关联拒绝。56 项终端测试及55组模型脚本通过；build:terminal 通过，保留既有大包警告。机器记录见 MARKET_RESEARCH_HISTORY_2026_11_11.json。

受控 Provider 没有请求付费模型。原测试进程句柄已缺失，重新执行的测试均确认结束成功；未因观察超时重启活跃进程。旧前端服务不存在监听时重新启动了 loopback 8850 服务；新 API 仍须由更新后的后端提供。没有部署公网服务。

尚未完成浏览器实际点击、刷新与双主题验收，也未证明外部模型、真实数据源、生产服务或全部旧功能可交付。下一步是该历史入口原生浏览器验收及逐页专属 AI 动作／真实数据覆盖，股票/CEX 研究到 Paper 和 Web3 只读闭环仍按完整目标继续。Live 关闭，无钱包签名入口。


## 独立进程 HTTP 与前端契约联验

扩展既有 `terminal-ui/scripts/serve-onchain-fixture.py --research` 的研究路由白名单及本地 Provider，支持原股票/CEX行情研究材料；保持禁止 public-probe 混用、无外部模型、无订单/执行路由。新增 `check-market-history-http.py`，仅接受 loopback URL、现存 /tmp 控制文件及明确的受控 fixture 标题，避免误测真实服务。没有另建业务后端。

实际 uvicorn 服务跑在临时 SQLite 与8001端口。探测脚本经过真实 HTTP：股票/CEX各覆盖成功、调用异常、无效引用；另以8秒延迟验证模型回复前已保存原材料，股票筛选不会读出正在等待的CEX材料，完成后原snapshot可恢复完整回复。七份实际回包均通过产品前端 marketHistoryList / marketHistoryArtifact 校验；数据库 order_intents、order_drafts、executions 均0；订单/实盘执行URL均404。

可复现命令：`python3 terminal-ui/scripts/check-market-history-http.py --control-file <受控服务的/tmp控制文件> --output <验收JSON>`。结果及源码哈希：MARKET_HISTORY_HTTP_FIXTURE_2026_11_11.json。数据是明确标注的受控合成CSV，不代表真实行情或付费模型。浏览器 inventory 再次连接超时，未使用替代浏览器自动化框架，不计原生点击/截图验收。

本轮还将左栏与“全部功能”目录改为共用 FunctionRegistry 的10类自然名称，68个功能入口无缺失分组，策略两处均显示“策略”。56项终端测试、脚本语法与build:public通过，旧版导出保留。同期其他工作区新增的子页样式与说明保留，没有覆盖或删除。

仍需继续：FunctionRegistry尚未覆盖每个二级页允许读取的数据、产物类型、失败状态和跳转目标，现有aiActions不能作为逐页AI完成证明；组合源的估值/时间/账户来源需要明确绑定，不能将旧PortfolioSummary的存储估值当作独立验证的实时持仓。完整目标继续active。
