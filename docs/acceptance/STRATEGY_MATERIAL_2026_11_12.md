# 策略参数私有材料接口

新增POST /api/v2/workspaces/research/strategy-material，要求readiness:write；GET同路径/{snapshot_id}要求read。准备时校验stocks/cex账户归属和兼容性、正数金额、严格参数白名单与长度。保存DataSnapshot terminal_strategy_parameters及审计；读取校验归属、内容hash、准备审计与当前账户可访问性，响应no-store。通用DataSnapshot列表排除该类型，未将用户陈述当作独立可信数据。

17个相关后端测试通过：私有读取、跨用户拒绝、错市场、未知字段、无效金额、managed viewer与未登录拒绝；managed测试使用受控会话。实际8001重启PID90807，OpenAPI两个新接口存在。未向实际数据库写入测试策略参数。

本轮仅完成材料接口，前端准备/预览、AI引用校验、专属结构化参数差异、历史列表仍未接通；未调用外部模型或执行交易，不代表策略AI完成。

## 前端准备与预览

策略向导第三步新增StrategyMaterialPreview：显式准备服务端快照，只允许已校验stocks/CEX账户；严格比对返回账户/市场/contextVersion与全部参数，校验来源、hash格式、时间和非执行标志。请求中切换用户/工作区/修改参数或卸载后丢弃返回；材料仅在原签名下展示，变化后提示重备。权限、登录、后端失败可见。

109终端测试和本地构建通过，已有bundle体积警告。未浏览器点击、真实本地账户写入或真实模型调用。该面板仅准备/预览；现有准备AI问题仍是用户参数文本，不会自动附带快照；后续需完成reference-only传输、服务端加载/引用校验和历史，不能称策略AI材料链路完成。

## 现有聊天后端接收策略引用

research_chat新增strategy_context严格reference（snapshot/account/market/context_version/content_hash）。服务端读取owned材料、校验hash/审计、当前账户及10分钟时效，preflight前后各校验一次，拒绝与行情/链上/组合/Paper材料混用（可选缓存新闻）。模型输入前保存research_chat_strategy_context；提供SP1用户参数引用，要求正文与evidence.strategy_citation_ids严格一致，裁剪后复验，失败不保存validated_reply；存私有回复状态，通用快照列表排除。没有新建正式交易报告或执行权限。

32项相关后端测试通过（控制Provider，无真实付费调用），109项终端回归通过。当前仅源码/测试证明，运行服务尚未重载这轮聊天变更；前端引用附件、回复展示/校验、历史列表/详情、专属结构化参数差异仍待接通。不能由此声称策略完整AI已实现。

## 策略快照聊天附件前端接通

材料预览提供准备AI快照审阅；原App校验附件身份后打开现有AI抽屉，用户必须显式勾选附件再手动发送。引用仅含snapshot/account/market/context_version/content_hash，不发送客户端材料副本。用户/上下文变化清空附件；时效、账户、版本及互斥材料发送前再次检查。成功回复校验来源范围及SP1引用，展示参数来源，历史会话标记SP1属于此前快照。未增加自动策略执行。

110终端测试通过；32相关后端测试通过（含后端真实TestClient响应由前端researchResult解析）；本地构建通过。实际8001已重载PID91514、health200；未调用实际付费模型、未浏览器点击、未真实账户写入验收。尚缺策略研究历史列表/详情、结构化参数差异及人工采纳、九类完整参数专属适配。page-ai strategy仍missing，不能把此切片当作全部策略AI完成。

## 策略研究历史

新增owned账户+市场历史列表（最近20条、has_more）和详情接口，read权限、no-store。详情包含冻结参数、问题、provider/model、reply_status、有效reply或null及可选新闻来源；检查材料hash及当前账户权限，跨用户404。前端手动读取、切换账户/用户失效、Abort/latest guards、strict历史DTO与researchResult复验；不自动附加历史材料或修改策略。

9个相关后端测试通过，包含实际TestClient历史DTO进入前端校验、失败回复null、跨用户读取拒绝；111终端测试与本地构建通过。实际8001重载PID91785，OpenAPI两个历史路由存在。未真实付费模型、浏览器点击/刷新验收；历史限最近20条，尚无完整历史分页。结构化参数差异/人工采纳、九类全参数适配及总体迁移仍未完成。

## 结构化参数修改建议

既有模型结构化回复evidence增加strategy_parameter_changes（最多5条），严格字段before/after/rationale/citation_ids，只允许amount/risk/trigger/invalidation/constraints；before必须等于冻结快照，拒绝重复、额外字段、空值、错误SP引用及非正/非有限金额。后端返回并随validated_reply保存；前端复验，当前回复/历史来源面板显示原值/建议值/理由。无建议允许空数组并说明缺口。

10相关后端测试、112终端测试及本地构建通过，包含后端实际测试响应由前端解析。此轮后端运行进程未重载新建议校验，未真实模型调用。当前仅差异预览，无人工采纳按钮；编辑参数建议与复制到新本地草稿仍待接通。九类策略及全目标继续未完成。

## 人工编辑建议并打开新草稿

来源面板差异表支持编辑建议值，点击审阅并另存为新草稿时重读owned历史artifact，校验reply/status/changes/hash；当前会话、账户、市场、contextVersion及时效匹配后才打开既有strategyCreate向导。原策略不改、不自动保存/启动。新草稿没有原ID，保留source_snapshot_id/request_id/content_hash；缓冲使用suggestion来源单独键，避免覆盖原未提交新策略参数；用户需再次确认保存。过期/跨账户建议须重新研究，不自动套入当前账户。

113终端测试、本地构建通过；后端已重载PID92241，health200，包含前轮结构化修改校验。未真实模型或浏览器操作证明；新草稿当前仍本地保存，人工采纳没有独立服务端事件；九类完整参数和其余逐页AI/迁移验收仍未完成。

## 网格专属研究材料

实际GridPanel新增AI审阅当前网格，读取当前手工上下界/整数格数/预算，校验后带入既有策略向导。材料parameters可选严格grid对象(kind arithmetic_grid,lower,upper,intervals)，后端校验上下界、2–500格、预算>=20；旧通用参数不新增null字段。前端请求/响应/历史/编辑缓冲保留typed grid且核对全部值。杠杆配置不进入此材料，明确未适配。向导只读展示专属区间，可回原网格编辑后重新准备。未自动调用模型/执行。

16相关后端测试、115终端测试及构建通过，包括typed grid端到端受控模型与历史DTO进入前端校验、错误区间/小数格数/bool/额外杠杆字段拒绝。实际8001重载PID93036。前轮1034全后端结果是本次grid扩展前的回归，本次仅重跑相关测试。尚未提供AI对grid上下界/格数的结构化修改建议（当前通用建议仍限定原五字段），未浏览器/真实模型验证；其它策略适配继续。

## 网格专属参数建议与另存

strategy_parameter_changes扩展grid.lower/grid.upper/grid.intervals（总计最多8字段）。原值精确匹配冻结快照，intervals按规范整数字符串返回；前后端同时验证全部修改后的typed grid与预算，不逐项误判可组合修改。无grid来源不能新增grid、修改kind或杠杆。差异表支持编辑网格建议，人工另存按嵌套grid合并到新草稿，原配置不变；仍需用户确认本地保存，不启动策略。

17相关后端测试、117终端测试及本地构建通过；包含受控模型返回grid字段并经前端历史解析、原配置不变、错误区间和小数格数拒绝、另存嵌套字段正确。后端已重载PID93978。未真实模型/浏览器验证；本次不含杠杆、交易所规则或实际回测，其余九类/全目标继续未完成。

## 策略材料币种绑定

parameters可选独立budget_currency/quote_currency字段，严格大写币种格式，旧材料不补猜测。前端准备时从实际CEX pair或已验证股票账户读取已知单位，拒绝表单已有字段与当前工作区不符；未知股票报价单位不生成字段。后端stocks预算币种与自有账户base_currency比较，读取prepared材料时再次校验当前账户币种，改变后拒绝旧附件。材料hash、历史、AI输入、另存草稿及编辑缓冲保留单位，不允许模型修改币种。网格原页带入已知单位。

18相关后端测试、123终端测试及构建通过，含带币种grid实际受控回复/历史由前端解析，以及错误股票预算币种拒绝。后端已重载。仍未独立验证股票价格币种；CEX单位来自工作区选择声明，非交易所资金可用性证明。真实模型/账户/浏览器验收、其它专属表单币种及完整目标继续未完成。

## 现货DCA专属材料

Actual DcaPanel新增AI审阅当前DCA，把实际每期金额/频率/手动首次计划时间/止盈意向带入原策略向导。parameters可选strict dca(kind spot_dca,frequency每天每周每月,first_run_local可选本地datetime字符串,take_profit_percent可选正十进制)。日期日历有效性/非时区字段/未知字段严格校验，禁止混合grid与dca；首次时间仅用户计划，不建立后台排程。前端准备/快照/历史/缓冲/新草稿保留typed dca。

24相关后端测试、外部127/镜像131终端测试及本地构建通过，含受控DCA模型/历史实际DTO进入前端校验、错误日期/模式/零止盈/混合配置拒绝。8001已重载PID15634。当前模型结构化修改仍仅通用字段和grid字段，dca.frequency等专属修改未接；真实模型/浏览器/实际调度或交易未验证，完整目标继续。

## DCA专属差异建议

结构化修改扩展dca.frequency/first_run_local/take_profit_percent，仅源快照已有dca时允许；可选缺失before为空字符串，after为空明确移除可选条件。必须精确匹配原值、保持完整SpotDcaConfiguration有效，禁止时区/非法日期/非正止盈与不支持频率。差异表有专属标签，可人工编辑后沿既有来源重读/当前范围校验流程另存新草稿；不会建立、取消或执行后台排程，也不保证止损/止盈成交。原参数不修改。

25相关后端测试，外部128/镜像132终端测试及本地构建通过，包括受控模型返回dca频率修改及真实TestClient历史由前端解析、可选条件移除/非法日期拒绝。后端重载PID15958。未真实模型或浏览器验收；合约DCA/跟单专属AI与其它全目标仍待完成。
