# AiCoin 前端补齐：当前实施状态

用户要求使用 https://github.com/bbylw/rea-cn 分析 `/Applications/AiCoin.app`，补充现有前端，并明确选择保留现有 3002 界面。

## 当前验收摘要：2026-10-29 r104

原始目标仍是保留现有3002界面，全面补齐AiCoin前端及交易所功能；尚未完成，不给出单一完成百分比。下方旧增量为历史记录，不代表当前最新状态。

| 范围 | 当前已实现及证据 | 仍缺的验收或功能 |
| --- | --- | --- |
| 原应用代码恢复 | 已有renderer/readable/模块工厂及r53哈希/语法验证记录 | 不是原始工程等价恢复；原生IPC、服务和全部模块运行未证明 |
| 公开现货行情 | Binance/OKX/Bitget报价、盘口、成交及主要周期K线WebSocket实网证据；真实深度/自选主页面 | Bitget长周期边界和小时线浏览器验收、更多平台、股票、长断线完整性仍待补齐 |
| 图表 | 多窗、指标、绘图、布局、CSV、PNG、复盘、视口及精确同步 | 全原版指标/比较同步/非规则切分/跨新小时实网等仍有缺口 |
| API连接 | 五家特定账户范围只读核验/可选保存/复查/禁用，52项当前后端回归通过 | 没有真实私有Key正向验收；地区/子账户/其他账户模式及交易权限未全面接入 |
| 资产 | 真实连接余额视图、直达连接表单，r77隔离假凭证完整流程截图 | 真实余额正向验收、跨账户估值、流水与盈亏同步未完成 |
| 脚本与策略 | 本地编辑保存/版本/导入导出及模型检查 | 原脚本编译运行服务、真实回测/策略执行未完成 |
| 资金/合约 | Bitget分组资金流；Binance/OKX/Bitget永续费率及基础币OI，r100–103浏览器证据 | 资金流单位/其他平台、更多合约指标、新闻与其余模块尚未全面接入 |

当前前端工作树回归：39个模型脚本、静态交互审计及构建通过（r104）。后端最近已有52项连接/凭证测试通过，未在本轮重跑；有1条Starlette/httpx弃用警告。模型检查和静态交互审计不是全页面端到端测试，也不证明实盘可用。

前端统一入口：`npm run test:models`（自动发现check脚本，逐项执行，任一失败或超时返回非零）；独立运行`npm run test:interactions`及`npm run build`。本轮前端证据：`../../output/aicoin-integration-20261027/regression-r104.json`；r80记录仅为历史边界。

## 最新增量：r33 单对象锁定与可见性

schema2绘图增加可选boolean locked/hidden，导入校验。对象管理器锁定时不能编辑价格/文字/样式或删除，图上不提供拖动手柄；解锁入口仍可用，全局锁定优先。更新守卫在锁定记录上仅允许解锁且保留原内容，避免同时夹带价格变更。隐藏移除绘图层及PNG中的图形，但列表保留对象与状态。批量清除仅清未锁定，菜单明确命名。

浏览器锁定趋势线后删除按钮disabled；清除未锁定后剩1个、撤销恢复8个；解锁后隐藏趋势线，DOM0个，保存刷新仍0且管理器hidden勾选true，无控制台错误。截图 `../../output/aicoin-integration-20261027/market-drawing-lock-hide.png`。模型检查锁定拒改、解锁不应用额外改动、隐藏与非法状态拒绝；交互检查与生产构建通过。完整原版工具和服务迁移仍未完成。

## 最新增量：r32 十字光标行情读数

每窗显示当前十字光标对应bar的UTC时间/OHLC/成交量，无对应bar时回当前窗口最后可用bar。程序化十字光标不触发库的move事件，增加同步回调直接更新目标读数；离开图表清理联动。读数基于实际显示的candles，复盘切换不会读到未显示未来bar。另将布局导入初始存储读取纳入catch，避免存储受限时未处理的Promise。

浏览器主窗点击后SOL与ETH时间均2026-10-24 13:00，收盘145.43与3110.37，成交量333与159，各自来源不同而不复制价格；切到复盘，readout1792710000不晚于last1792746000，无控制台错误。截图 `../../output/aicoin-integration-20261027/market-ohlcv-readout.png`。本轮并行运行现有13组专项（导航、分析、轴、菜单、绘图、布局、迁移、复盘、时间定位、视口、数据模型、指标、脚本）全部退出0，生产构建通过，仍有大包体提示。非全部原版功能验收，整体目标继续。

## 最新增量：r31 布局配置迁移

增加自有格式ai-trading-chart-layout/v1 JSON导出/导入，包含当前完整结构化布局（非行情/账号/脚本密钥）。导入先校验再写入，新建独立标签，最多100套、2MB；拒绝未知版本、损坏绘图、重复ID、旧版无效坐标及读文件期间列表变化，不覆盖原标签。该文件格式不宣称兼容原AiCoin私有布局格式。

浏览器导出chart-layout.json后真实文件选择器导入，出现“导入 未命名/已保存”新标签，原两标签保留、8绘图恢复，无控制台错误。截图 `../../output/aicoin-integration-20261027/market-layout-import.png`。专项覆盖往返和异常结构，交互检查与构建通过。原App完整功能与服务接入仍未完成。

## 最新增量：r30 图表PNG导出

每窗PNG按钮调用实际`takeScreenshot`，按设备像素比例合成当前SVG时间/价格绘图，排除选中手柄及UI控件。图片底部说明交易对/报价币、平台、周期、演示或后端快照来源、复盘标记、Lightweight Charts及导出时间。没有伪造服务端分享链接，原布局快照记录继续保留。错误及图层10秒超时可见，释放临时Blob URL。

浏览器实际导出ETH-1时-chart.png，打开看到面积图/均线/成交量和矩形、水平线等当前可见绘图，来源明确演示数据与网络/跨域限制。补全USDT与导出时间标注后再次下载ETH-1时-chart (1).png，状态PNG已生成且无控制台错误。原始导出复制作为验收产物 `../../output/aicoin-integration-20261027/market-export-verified.png`。交互检查568按钮191表单、生产构建通过，仍有包体提示。未完成原版完整导出/分享服务或其他全量迁移。

## 最新增量：r29 实际时间定位

“定位到…”和“日期范围”原来仅有弹窗/成功提示，现在根据当前已载入bar计算逻辑范围并调用主图API，复盘时仅允许已显示bar。UTC时间定位选择邻近真实bar并提示实际时间；日期范围含结束日，拒绝无数据/反向/越界范围；失败回调阻止弹窗关闭和虚假成功提示。命令带当前市场上下文，切换后不应用旧命令。

发现相同主范围重复应用时库无变化事件，增加显式同步；原expected回调Set改为按实际日期/跨度匹配的Map，不吞掉未匹配的新用户事件。验证同步用实际可见timeRange，而非不同序列的逻辑索引。移除半bar日期留白后，浏览器两窗均from1792800000/to1792882800，即2026-10-24 00:00..23:00，24根小时bar。定位10月25日12:20提示邻近12:00；2025越界保留弹窗/视口。截图 `../../output/aicoin-integration-20261027/market-date-navigation.png`。时间导航专项覆盖UTC邻近/含结束日/越界/反向范围；同步模型覆盖重复显式请求及旧回调标记不吞新请求。真实行情数据正向仍受后端登录/Origin限制，整体目标继续。

## 最新增量：r28 真实游标驱动复盘

原复盘面板用step百分比推导价格、固定胜率，图表仅固定截断62%，均已替换。现在冻结主图当前载入快照，按真实bar索引/UTC收线时间推进，单步/播放/1x2x4x/重置和日期起点接通同一游标。主图价格与指标按当前复盘数据更新，多周期副窗只展示该游标之前结束的bar，避免完整4hOHLC提前泄露；逐根推进时视口跟随。演示快照保持演示标注，复盘中隐藏装饰买卖信号、筹码/大额假标记和交易员标记；图外盘口资讯明确不参与复盘。

模拟记录按当前bar.close买卖0.01，均价成本、realized/unrealized PnL实际计算，卖出不超过持仓。结果不含假68.4%胜率，注明无手续费/滑点/撮合、不提交委托，仅当前页训练。选择新有效起点重置记录。真实后端仍受Origin/login限制，本次验证只使用演示快照。

浏览器实测主图15/132->单步16，4x连续推进到99后暂停；买146.1932/卖146.2195×0.01=已实现0.0003USDT（四位显示），持仓清零、2笔记录，结束结果一致。补齐视口跟随后单步16时逻辑范围1..19。日期弹窗原默认固定2026年7月且native输入未同步React，改用当前UTC预设/当前复盘bar默认并接onInput；实际选2026-10-23T00:00后主19根、副103根，主last1792713600；选2025范围外保留弹窗/原复盘状态且报错。截图 `../../output/aicoin-integration-20261027/market-replay-cursor.png`。专项模型覆盖时间选择/跨周期已结束bar/成本和盈亏/跨年闰年日期；交互检查及生产构建通过。原版更完整复盘工具、持久结果和完整服务迁移未完成。

## 最新增量：r27 报价币与后端故障边界

修复仅传BTC可匹配USD、页面却写USDT的问题：主图和副图按WEB3传USDT、股票传USD。资产筛选核对平台、显式pair后缀及currency，拒绝矛盾目录、缺少报价信息的裸标的及重复候选，不将USD自动当USDT。请求缓存身份包括marketMode；对比工作区展示实际asset/venue/currency，继续要求使用者确认单位。

新增专项覆盖同平台USD/USDT/USDC选择正确asset_id、错误报价不请求K线、裸BTC元数据、目录冲突/重复、股票USD。HTTP错误保留status，401登录/403权限/500服务错误分别报告；fetch TypeError说明网络或跨域，不断言服务停机。

当前本地curl `/health`200，`/assets`及`/health/status`无Origin401；带127.0.0.1:3002或localhost:3002 Origin的请求及OPTIONS均403，无可读CORS响应。因此浏览器只能得fetch失败，不能据此宣称收到401。未更改Origin白名单或绕过登录。浏览器复验显示“浏览器无法读取后端（网络或跨域限制）·演示回退”，各窗来源提示相同。截图 `../../output/aicoin-integration-20261027/market-feed-status.png`。真实后端报价正向链路尚未验证，整体目标保持进行中。

## 最新增量：r26 精确价格范围

坐标菜单增加真实读取及输入上下限，正数有序校验，应用到当前窗价格轴并关闭自动范围。视口保存priceRange与priceMode，按标的/平台/周期/回放key和模式匹配恢复，自动范围时不套固定值。价格轴拖动抬起时也重新捕获范围。百分比模式禁用绝对范围。

首次浏览器测试暴露LW5.2公开setter原样存raw数、log getter当作变换值的差异，曾出现异常刻度；直接切换模式也因库的options合并顺序无效。最终使用公开set/get校准库中整数对数偏移，按本地源码的正数对数公式转换并回读核对；修正版库的直接setter若已正确则不适配。无私有API调用/节点模块改动。适配失败则恢复自动并提示，NaN/Infinity不保存。

复测SOL140..155与ETH3100..3250分别应用，保存刷新精确回读；读取按钮仍3100/3250；输入上限3000拒绝且旧范围不变；关闭坐标同步后仅ETH开启自动，回到实际数据3086.7..3191.26，SOL仍140..155；再应用固定范围成功，无控制台错误。截图 `../../output/aicoin-integration-20261027/market-price-range.png`。专项模型覆盖范围验证、身份/模式隔离、原5.2对数偏移4/7与已修正版setter路径；交互检查567按钮191表单与生产构建通过。完整原版功能/服务迁移仍未完成。

## 最新增量：r25 坐标轴与原版快捷键

参考原版locale的linear/logarithmic/percentage、contextmenuInvert和axisLocked选项，接入每窗线性/对数/百分比、翻转和自动范围。调用真实`priceScale.applyOptions`，百分比以可见区间首值0%且强制自动范围。支持独立设置、启用坐标轴同步时以主窗统一，随后任一窗更改同步18窗配置；新布局保存paneAxes，旧布局回默认。

对恢复模块`reference/aicoin/modules/main/18607.js`重新运行REA选定源码分析退出0，证据`rea-axis-shortcuts-evidence.json`，文案与恢复代码明确invert-scale/lock-scale的Alt+i/Alt+l。图表获焦时接通两快捷键，输入框不拦截。分析限于选定模块，不证明整个App动态语义。浏览器验证主线性、副对数翻转；副百分比实际显示百分比轴且自动开关disabled；同步后两窗mode1/invertScale true，保存刷新仍一致；Alt+i变false、Alt+l使真实轴autoScale false，无控制台错误。截图 `../../output/aicoin-integration-20261027/market-axis-sync.png`。`scripts/check-chart-axis.mjs`验证模式映射、独立/同步、百分比约束及不可变布局往返。精确手动价格范围、完整键盘作用域及原版其余功能继续接入。

## 最新增量：r24 图上选择与拖动

光标模式直接点击绘图选择，显示价格/时间锚点手柄，拖动整体平移或拖动单个锚点修改。拖动过程中只更新预览，抬起后提交一次，统一撤销/重做/布局保存。整体移动保持各锚点时间差和价差，禁止移出当前数据范围或非正价；不到3px不作修改。全局锁定禁用图上编辑，Esc/指针取消丢弃预览。长画笔超过50点只展示首尾手柄，其余点仍可在对象管理器编辑。

浏览器实际整线拖动后坐标从x-36.72..254.30变为-19.60..271.42；拖第二锚点后第二点x305.66/y325，第一点不变；一次撤销回第二点x271.42/y364.66，重做并保存刷新回305.66/325。最终点选趋势线显示2手柄且撤销记录保持0步，无控制台错误。截图 `../../output/aicoin-integration-20261027/market-drawing-drag.png`。纯模型覆盖平移、不可变原记录、越界/非正价拒绝；静态交互检查与生产构建通过。Esc中途取消尚未做浏览器按住鼠标专项验收。完整原版工具集、单对象锁定等继续接入。

## 最新增量：r23 绘图对象编辑

每窗对象列表只列当前scope标的绘图，选择后可精确修改UTC时间、价格、文本和颜色/线宽。多锚点逐个编辑，字段校验拒绝日期溢出、非正价格和无效样式。修改及单对象删除走统一撤销/重做；全局锁定禁用表单和删除，布局保存包含新样式与锚点。直接拖动选择/修改、锁定单个对象等仍未完成。

初次浏览器验收暴露Grid漏传新回调导致加载ReferenceError，随后补齐参数并刷新复验。实际验证趋势线第一锚点从3168.09修改3200后再3175，线宽4且SVG属性更新；价格0显示错误；单对象删除从8到7，撤销恢复8；文字改ETH复核区；锁定后应用/删除均disabled；保存刷新回读3175/4及新文字。截图 `../../output/aicoin-integration-20261027/market-drawing-editor.png`。计算/UTC解析/样式测试、565按钮186表单静态检查和生产构建通过，包体警告仍在。整体目标未完成。

## 最新增量：r22 时间价格绘图

八种现有绘图工具改为schema2真实锚点，包含scope市场/平台/标的及时间/价格points，按每窗价格主图区转换和绘制。趋势线/矩形/斐波那契/测量两点，平行线三点，水平线一点；文字点击后输入，自由画笔采集拖动轨迹。磁吸选择当前K线OHLC最近价。测量显示实际涨跌幅及时间差，缩放/滚动/尺寸/价格拖动时重投影。同标的不同时框按实际时间插值定位，范围外不制造锚点。布局和新快照保存绘图；旧屏幕百分比记录保留并标注旧版，不自动伪造转换。

浏览器在ETH副窗实际创建全部八种图形，SOL绘图计数0。趋势线缩放前x141.74..347.30，缩放后x-36.72..254.30（价格轴自动调整），锚点随图移动。测量+0.29%/3360分，文字ETH观察区，画笔生成polyline，斐波那契7层，平行线2条。撤销计数7、重做8、保存刷新仍8，无控制台错误。截图 `../../output/aicoin-integration-20261027/market-anchored-drawings.png`。`scripts/check-chart-drawings.mjs`验证锚点转换、磁吸、跨时框定位、测量、无效结构及不可变布局捕获。尚缺逐对象选择/拖动编辑、样式和完整原版绘图工具集；完整迁移继续。

## 最新增量：r21 价格坐标与副窗上下文

右键命中改到各窗实际价格canvas，使用主价格序列`coordinateToPrice`，只接受主价格绘图区内有效正价，排除坐标轴/指标副图区。价格按标的精度取整，菜单与预填共用同值，演示数据菜单标明演示。副窗标的贯穿预警/自选/限价预填；预填同步主标的避免订单面板仍使用原主图。未授权状态显示待填入摘要，未提交委托。切换其他标的不延用旧预填价。复盘按钮改为“打开K线复盘”，不再宣称从点击位置启动。

浏览器验收SOL主窗/ETH副窗，右键ETH菜单为ETH/USDT，实际转换价格3125.59，选择卖出后主标的ETH且未授权摘要显示ETH/限价卖出/3125.59，无委托提交。截图 `../../output/aicoin-integration-20261027/market-order-prefill.png`。`scripts/check-chart-context.mjs`覆盖实际转换调用、越界拒绝、空/负价拒绝、股票标签和精度。绘图工具激活时仍使用旧绘图层，真实绘图锚点和其余完整功能待接通。

## 最新增量：r20 视口持久化

各窗保存逻辑范围、可见日期范围、数据首尾及标的/平台/周期/回放身份，改指标/图表类型后重建保留视口。数据首尾相同恢复逻辑范围，发生移动但日期仍重合则按日期恢复；其他标的不复用。新布局/快照包含视口，旧schema1不含视口仍兼容。增加真实LW API放大、缩小、显示全部按钮，缩放后标记未保存。

验收先发现旧图异步事件覆盖恢复视口，随后增加存储代际校验修复；浏览器复测副窗范围从0..135缩至40.5..135，改EMA保持，保存/刷新保持68.85..135；最终再放大保存刷新为88.695..135。开启缩放同步后两窗均40.5..135，无控制台错误。`scripts/check-chart-viewport.mjs`覆盖身份隔离、逻辑/日期选择、无交集、损坏结构及不可变布局往返。截图 `../../output/aicoin-integration-20261027/market-viewport-restored.png`。绘图锚点、价格轴视口及完整原版功能仍待接入。

## 最新增量：r19 布局持久化

补齐布局和新快照的结构化状态：市场类型、平台、主标的、图表类型、周期、窗数及18窗交易对/周期/指标/同步项。兼容仅含symbol的旧布局及旧快照，未知版本拒绝恢复。当前标签持久化，跨市场恢复按市场默认重置之后应用布局，避免初始周期覆盖。布局管理器从写入指标名称修正为设置真实窗数。保存前检查存储写入，错误时保留当前页面设置。

浏览器在127测试域验证：保存SOL/ETH、不同周期/面积图/BOLL后刷新恢复；第二套AVAX副窗保存后双向切换正确；刷新回到第二套；将第二套改股票再切第一套恢复SOL/ETH面积图，无控制台错误。`scripts/check-chart-layout-state.mjs`验证完整往返、不可变副本、无效版本/周期/窗数/字段拒绝。截图 `../../output/aicoin-integration-20261027/market-layout-restored.png`。视口/缩放已在r20补齐，每窗绘图和完整原版布局结构尚未保存；不等于全量迁移完成。

## 最新增量：r18 多窗指标与计算副图

每个图窗头部可选择技术指标，关闭指标同步后副窗修改独立；启用同步后副窗修改更新全局。浏览器已验证主EMA关/副EMA开，以及同步BOLL两窗均开启。RSI14、MACD12/26/9（柱为2×DIF-DEA）、KDJ9/3/3按当前各窗K线计算并绘制单独副图；短样本不填造RSI/KDJ默认值。计算约定为EMA首值初始化、RSI Wilder、K/D初值50，与原版所有细节的数值一致性仍待对照。`scripts/check-market-indicators.mjs`覆盖已知RSI算例和平盘/涨跌/空输入。浏览器三副图实际显示且无控制台错误，截图：`../../output/aicoin-integration-20261027/market-oscillator-panes.png`。独立设置在后续r19纳入布局持久化，真实订阅和其余完整功能继续接入。

## 最新增量：r17 行情多窗

每窗交易对选择可独立运行；开启交易对同步时从任何图窗选择将更新主标的。独立副图只在标的与周期均一致时共享主图数据，否则单独请求。请求结果按标的/平台/周期键隔离，避免切换时显示旧行情。浏览器验收BTC/ETH独立、启用同步后副图选SOL得到SOL/SOL，无控制台错误。截图在 `../../output/aicoin-integration-20261027/market-symbol-sync.png`。目前真实订阅、独立指标、坐标轴/对比联动等仍待完成。

本机脚本及指标库已完成r16增量，见文末记录。下方r15/r14为历史阶段范围，不代表当前全部进度。

## 当前增量：r15 对比与组合价差

- 根据原版 6416/14948、8884/92332 及公式显示模块补入现有行情工作区，加入对比/价差入口及两个原版地址。当前基础映射21个，原4种面板参数保留。
- 支持2–10项、后端/CSV、OHLC栏位、共同起点涨幅/价格叠加、收盘/所选栏位价差及价差率、基础算术公式、对齐统计、数据表和CSV导出。无数据不会合成替代曲线，无效公式清除先前结果。
- REA所选价差模块分析退出0；计算与CSV专项、导航专项、541按钮173表单合同及生产构建通过。CUA用合成本地夹具验证实际计算/导出/零分母恢复，最终修改后验证离线与Escape关闭。
- 该增量尚不等于原版完整对比图/组合OHLC、行情订阅、hash持久化、策略联动已完成；真实行情正向验收仍待完成。[详细证据与剩余范围](AICOIN_CHART_ANALYSIS_2026_10_27.md)。整体目标保持进行中。

## 当前增量：r14 源码恢复与导航纠正

- 用户选择继续保留现有界面，按原版代码补齐；整体目标保持进行中。
- 新增 `scripts/recover-aicoin.mjs`：使用 webcrack 2.16.0 + Node 24.22.1 为全部 224 个 JS 生成可读版本；每个输入/输出保留 SHA-256、退出码和处理记录。webcrack 的解码在 isolated-vm 内执行，不运行 App bootstrap。
- 其中 223 文件默认处理成功。`im-client.js` 默认 JSX 转换 180 秒超时；日志未检测到字符串数组，关闭解码/JSX 转换后静态格式化成功。失败记录保存在 `previous_attempts`，不能把格式化结果称为完整语义还原。
- 新增模块拆分与验证脚本。可读文件位于 `reference/aicoin/readable/`，模块位于 `reference/aicoin/modules/`；这些工厂仍可能依赖原 Webpack 环境，不等于可直接运行的独立 React 组件。
- 最终验证：1,099 原始文件、224 可读 JS、4,660 工厂文件均通过哈希和相应语法检查。9 个文件未被当前工厂匹配器拆分，原始与可读全文均保留；全局 ID 候选索引有28个静态依赖目标未匹配。不同 runtime 的模块 ID 可能重用，因此既不能把这一候选数字当完整依赖缺口，也不能声称所有模块已独立可运行。详见本地 `verification.json`。
- 对 6.6KB 的恢复模块 `main/99719.js` 运行 REA，退出码 0；Evidence 为 `rea-routes-module-evidence.json`。这是单模块静态证据，不能替代全 App 分析。
- **纠正首批映射错误**：当前安装包明确 `EXCHANGE=/main/exchange` 为行情、`INFO=/main/info` 为要闻、`NEWS=/main/news` 为快讯。首批将 `/main/info` 映射行情、`/main/news` 映射要闻的判断已被当前源码推翻。当前对应跳转已修正，新增链上入口，共 19 个基础导航映射。
- 从恢复工厂通过只允许字符串/对象/常量引用的 AST 解释器导入 83 个地址与 70 个名称到 `src/aicoin-navigation.generated.js`。不执行模块或导入原 bootstrap。
- 从恢复代码观察到 `fundPanel=editor/grid/dca` 及 `fundPanel=editor&tab=backtest`，已接入现有指标编辑/AI网格/现货DCA/策略回测面板。重复参数、未知参数、账号/脚本/订单上下文及 `tab=start` 保持未支持，不能静默丢弃。
- 实际浏览器已验证要闻、快讯、行情三种纠正后入口；网格/DCA/回测定位，回测刷新保持、手动切换指标编辑清除旧参数。导航检查、531按钮/163表单静态合同和生产构建通过；原大 bundle 警告保留。
- 以上只证明代码恢复产物、导航和现有面板交接，不能证明原版全部算法、图表、指标、后端服务和交易能力已迁移。

## 首批已完成（历史记录，映射以 r14 纠正为准）

- 安装包版本 2.16.28；完整提取 `dist/renderer` 的 1,099 个文件、185,836,870 字节。
- 全部 1,099 个文件 SHA-256 与 ASAR 内声明相符；完整清单为本地 `reference/aicoin/manifest.json`。
- 224 JS、91 CSS、5 HTML 及其图片/字体/媒体全部保留。没有 source map，不能称为原始 React/TypeScript 工程。
- `scripts/import-aicoin.py` 可重复提取到新目录；拒绝覆盖、路径穿越、link、unpacked renderer 和声明哈希不匹配。
- `scripts/index-aicoin.mjs` 对全部 224 个 JS 语法解析成功，记录 115 个入口字符串候选及文件偏移。候选包含偏好/API 等，并非完整路由清单。
- `src/aicoin-routes.js` 增加 17 个明确导航映射，初次加载和 hashchange 均可处理；未知地址及带参数地址保持未支持。
- 修复策略初始化覆盖原版跟单入口分类的问题；手动导航退出旧 hash，避免刷新又回到原地址。

## 验证范围

- `node scripts/check-aicoin-routes.mjs`：17 个映射、原包入口出处、返回值隔离、未知/参数地址拒绝。
- `npm run test:interactions`：531 按钮、163 表单，既有 10 一级页、59 频道静态合同。
- `npm run build`：生产构建；原有大 bundle 提示保留。
- 实际浏览器：Hyperliquid 地址加载及刷新、导航至资产清除旧地址、未知交易所入口保留当前页并提示、跟单入口展示 CEX 分类、手动切换 DCA 清除旧地址。测试运行于独立 3012 端口，未替换用户 3002 服务。
- 静态合同、导航映射和空数据演示页面，均不能证明原版功能完整迁移或真实数据接通。

## REA 证据与限制

使用 rea-agents 6.8.0 CLI 和 Node 24.22.1，没有写入 Codex MCP 配置。

首次扫描原 ASAR 因 unpacked 原生 Helper 声明哈希不符失败。该矛盾保留，未关闭校验、未执行 Helper。随后只分析经逐文件哈希校验的 renderer。

全 renderer 语义分析在大 JS 文件达到 300 秒超时，返回 `provider_timeout`。部分 Evidence 原样保存在本地 `reference/aicoin/rea-summary.json`；不宣称完整语义分析成功。Babel 全文件语法和字面量索引是独立的辅助分析，不能冒充 REA 的完整语义结果。

后续针对 `main.js` / `commons.js` 的选定源码请求采用较低语义节点限额和 60 秒预算，仍返回 `provider_timeout`，其部分结果保留在 `rea-entry-summary.json`。未反复重跑相同请求，也未把局部 Evidence 当完整模块图。

## 未完成的原版功能迁移

- 原版行情工作区的 AI 指标/Copilot 及全部上下文参数。当前代码证明 `/main/exchange` 是行情；旧资料所谓额外独立“交易所”页面的判断不再作为验收要求。
- 多线、价差、专业回测、模板、脚本与筛选器独立窗口的完整语义。
- 机器人管理、量化、策略广场、DEX 和跟单的全部原版配置及交互差异。
- 原版图表绘图/指标全清单、委托/持仓抽屉全部参数与状态。
- Electron IPC、原生行情插件及桌面窗口能力的 Web/自有后端替代。
- 登录、付费、账户授权、实时数据以及交易接口：不能因导入界面资源即变成可用服务。

每个模块仍需核对原版证据、实现缺口、现有后端能力、错误恢复、实际交互验收。19 个基础映射和4种面板参数只说明入口导航，不能据此计算功能完成率。当前整体状态为进行中。

## 本地复现

```bash
python3 scripts/import-aicoin.py --output reference/aicoin-new
node scripts/index-aicoin.mjs reference/aicoin-new
node scripts/check-aicoin-routes.mjs
npm run test:interactions
npm run build
```

`reference/aicoin*/` 已加入 Git 忽略，不进入 `public`、`src` 或 `dist`，不会随现有发布脚本发布。源 App、用户资料、账号和交易权限未改动。

## 2026-10-28 行情实现增量（未完成全量迁移）

- 本机脚本已支持保存、副本、版本恢复、归档恢复、导入导出、编辑缓冲和多标签冲突保护。检查仅为基础词法检查，原编译服务未接入；回测仍明确标为固定演示。
- 行情周期统一解析秒/分/时/日/周/月/季/年；不再将未知周期静默回退。月季年按UTC日历，周从UTC周一计算。倒计时是UTC周期边界，股票交易所日历尚未接入。
- 面积图使用实际AreaSeries；EMA不再顺带启用MA，EMA序列一次计算。
- 同周期副图共享主图快照，不同周期独立取数；资产匹配核对平台和报价对，重复时间、错误OHLC、混合来源或不符请求的K线拒绝显示为后端数据。无数据的图明确标演示。
- 多窗周期切换已接通；十字光标、日期范围和缩放比例已接入图表API，回调重入保护有模型测试。独立指标、对比K线、坐标轴和其他联动仍待接入（交易对独立切换与同步已在后续r17补齐）；自定义分隔线编辑待接入。
- 浏览器验收：面积图双窗，从第二窗选择4时后两窗均为4时，无控制台错误。截图：`../../output/aicoin-integration-20261027/market-area-two-panes.png`。十字光标/拖动缩放的跨窗视觉行为尚待完整浏览器验收。
- 新增 `scripts/check-market-chart-model.mjs` 验证UTC周期、行情校验、平台精确匹配和同步回调。生产构建通过，仍有大包体提示。
- 完整renderer、可读恢复及模块副本属于参考材料，不等于现有前端全部服务/交互已迁移完成。大体积超时报告保存在 `reference/aicoin/rea-summary.json.gz`。

## r34 主行情CSV入口

每窗可导入1MB以内、1–10000行OHLC CSV，严格校验时间/重复时间/正数OHLC/非负成交量；应用前确认当前标的、周期和报价币。缺失volume时禁算成交量/VWAP，保留其他价格指标。本页内存数据不写入布局，不等于已验证的交易所行情。回放期间禁止切换文件。

验证：check-market-csv、check-chart-analysis、test:interactions和build通过；浏览器主SOL图导入24根合成小时K线后实际读数147/149/146/148、volume70对应07:00UTC；独立ETH图保留演示标识。截图market-csv-import.png。回放CSV完整交互回归仍待验证。

## r35 CSV回放浏览器验证

合成24根小时CSV进入回放，初始15/24根主图14:00收盘155，单步后15:00收盘156、量150；独立ETH图按同一截止时间过滤。回放中文件输入和恢复数据按钮均禁用。缺失成交量时新增VWAP/Volume禁用说明。build及交互审计通过；截图market-csv-replay.png。未证明真实交易所数据连接或完整迁移完成。

## ai-trading-assistant-full-2026.10.28-r36

- 每窗新增K线CSV导出，携带标的/平台/周期/来源类型；使用当前可用快照，隐藏未来回放使用已过滤数据。
- 缺失volume省略该列，支持重新导入；包含CSV转义和表格公式保护。
- 往返测试、交互审计、构建通过；浏览器下载实检132根demo数据。完整迁移继续。

截图market-data-export.png；导出为当前图窗可用快照，并非仅当前缩放区间。

## ai-trading-assistant-full-2026.10.28-r37

- 多窗新增1–6列及各列1–4倍宽度设置，所有行共用列宽，取消不应用，恢复默认等宽可用。
- 列宽进入布局捕获/校验/恢复与布局JSON导入导出，兼容旧布局。
- 浏览器实测双窗4:1宽度1016.53/254.135px，保存刷新后保持；几何/布局/传输检查、交互审计及构建通过。
- 任意分隔线直接拖动尚待接入，完整AiCoin迁移未完成。

截图market-custom-columns.png。这里只完成矩形网格列数和列宽设置，尚非原版任意分隔线编辑。

## ai-trading-assistant-full-2026.10.28-r38

- 图窗列分隔线支持指针拖动、左右键微调、Shift加速、Esc/指针取消恢复、双击等宽；相邻列总权重保持，权重范围0.25–4。
- 浏览器验证1016/254px拖至836/434px，键盘调整823.823/446.844px，保存刷新保持。
- 几何边界模型检查及生产构建通过；仅整列调整，局部分割及完整迁移尚未完成。

截图market-divider-drag.png。

## ai-trading-assistant-full-2026.10.28-r39

- 多窗补充横向行分隔线，支持拖动行高、上下键微调、Esc取消及双击等高。行权重与列宽一起保存到布局并校验，旧布局默认等高。
- 浏览器四窗实测上下行408.656/331.010px，刷新后368.885/298.771px（容器高度改变，约1.235行高比保持）。
- 行列模型、布局传输、交互检查与构建通过。仍为整行整列网格，局部非规则分割和完整迁移尚未完成。

截图market-row-divider.png。

## ai-trading-assistant-full-2026.10.28-r40

- 对照原版zh/chart.json的copyTemplate文案补齐复制布局入口，复制当前未保存设置为独立标签，包含画线/指标/视口/行列比例；行情文件不进入布局。
- 先写入本机存储再切换标签，失败显示错误，100套上限。
- 浏览器验证原标签保留、新副本出现；刷新恢复四窗及368.885/298.771px行高。构建和交互审计通过。完整迁移仍未完成。

截图market-layout-copy.png。原版依据：../_aicoin_reference/02_功能文案_locales/zh/chart.json -> copyTemplate/copyTemplate_success/copyTemplate_reachLimit。

## ai-trading-assistant-full-2026.10.28-r41

- 依据原版chart.json editTemplate补齐布局重命名，1–80字符、空白拒绝，支持Enter保存/Esc取消；只修改名称，先写存储再关闭编辑。
- 浏览器验证空名称错误保留编辑，副本改名“行情四窗复核”刷新保持，其他标签保留。构建及交互审计通过。
- 完整前端迁移仍在继续。

截图market-layout-rename.png。

## ai-trading-assistant-full-2026.10.28-r42

- 依据原版templateUnsavedTips补充跨页面布局版本核对，布局列表不再挂载自动回写；保存/复制/命名/导入/关闭/创建统一显式提交，存储失败不继续显示成功。
- 旧页面发现列表变化时拒绝覆盖，保留当前图表并提供重新读取列表；损坏存储也拒绝覆盖。
- 浏览器双页面验证B复制后A保存被拒绝且显示冲突；存储模型/交互审计/构建通过。此为写前版本核对，尚未实现跨进程同时写入的互斥锁。
- 完整AiCoin迁移未完成。

截图market-layout-conflict.png。

## ai-trading-assistant-full-2026.10.28-r43

- 所有布局列表写入统一使用Web Locks独占锁，在锁内检查存储版本并提交；同页重复提交也受保护。浏览器无锁支持时拒绝写入并提示导出备份。
- 所有创建/关闭/保存/重命名/复制/导入调用改为等待提交成功后再切换或提示。
- 模型并发测试仅一次提交；实际双浏览器页面同时复制时A冲突、B成功，列表新增一个副本。构建及交互审计通过。
- 仅协调使用此锁的当前前端页面，其他旧版本写入者不受锁约束。完整迁移未完成。

截图market-layout-exclusive-lock.png。

## ai-trading-assistant-full-2026.10.28-r44

- 图表类型新增实际平均K线（Heikin Ashi），递归开盘与OHLC均值计算，保留原成交量；读数标明合成OHLC/非成交价，数据导出来源附合成说明。
- 图形/指标使用合成序列，回放先截断再计算；模拟交易仍按原始收盘，不使用合成成交价。布局可保存新类型。
- 模型验证递推、极值、不可变和无未来依赖；浏览器SOL合成开148.13/收148.29（原始收148.32），保存刷新类型保持。构建/布局/交互检查通过。
- 标准平均K线实现，未证明与AiCoin初始化细节完全一致；全局设置面板尚未统一接线。完整迁移未完成。

截图market-average-candles.png。

## ai-trading-assistant-full-2026.10.28-r45

- 根据原版chart.json ContrastCandle_ohlc和preference.json stick-OHLC补齐美国线，使用真实BarSeries含开盘短线，保留原OHLC/成交量。
- 布局类型校验支持美国线；浏览器验证4窗各132根并实际切换，原始SOL收148.32，保存刷新保持。构建、布局和交互审计通过。
- HLC为原版独立类型，尚未映射为美国线；完整迁移继续。

截图market-ohlc-bars.png。

## ai-trading-assistant-full-2026.10.28-r46

- 根据恢复chart-core源码bb.getOpen（46365起）和yb绘制（46182起）接入K线图(HLC)：前一根收盘作为实体开端，绘图极值扩展覆盖实体，第一根保留原开盘。
- 仅绘图数据转换；原始OHLC读数、指标和CSV保持原口径，读数标明实体以前收绘制；布局保存支持新类型。
- HLC模型检查首根、跳空极值、不可变和无未来依赖；浏览器读数提示及刷新保持验证通过，构建及交互审计通过。附属成交量/价格线颜色细节尚未逐项对齐原版。
- 同时找到原版平均K线transformer（83395起），其首根均值和递推公式与当前实现一致；未据此宣称全部渲染像素等同。完整迁移继续。

来源reference/aicoin/readable/chart-core/deobfuscated.js。截图market-hlc-candles.png。

## ai-trading-assistant-full-2026.10.28-r47

- 按恢复chart-core 55826/55866的价格线比较规则，以实际序列收盘和开盘（HLC用前收盘）决定颜色，移除对页面quote.change的依赖。
- 读数颜色按52855/54439规则：HLC索引大于1用前收盘，否则原开盘；平盘读数非跌，价格线严格上涨。
- 合成跳空CSV浏览器验证同一末根普通蜡烛读数绿rgb(32,180,134)、HLC红rgb(237,83,98)。模型边界、构建、交互审计通过。
- 成交量颜色未发现足够源码证据，本轮保留原规则；完整迁移继续。

截图market-hlc-colors.png；测试文件hlc-colors-fixture.csv仅合成验收数据。

## ai-trading-assistant-full-2026.10.28-r48

- 系统K线设置保存后实际应用样式、价格线、倒计时及网格到所有当前图窗，包括独立指标图窗；保留已有指标选择。
- 全局默认值用于新工作区初始化，已保存布局恢复自己的显示配置；再次保存全局设置显式覆盖当前显示。取消面板不触发图表应用。
- 浏览器四窗验证统一切为美国线，12个价格线/网格/倒计时检查项全部关闭。映射与保留指标模型检查、交互审计及构建通过。
- 持仓成本线仍需真实账户数据，不据此宣称全局全部开关已接线；完整迁移继续。

截图market-global-display-settings.png。

## ai-trading-assistant-full-2026.10.28-r49

- 系统显示偏好改为面板内草稿，取消不持久化；保存将systemSettings与生效prefs一起写入同一记录，再更新UI，失败保留草稿并提示。
- 兼容读取旧system-settings，后续优先读取prefs.systemSettings；Webhook列表仍为独立即时操作，不属于此次草稿改造。
- 浏览器验证美国线改平均K线后取消重开仍美国线；保存重开才为平均K线。构建与交互审计通过。跨页面系统偏好并发写入尚未统一加锁。
- 完整AiCoin前端迁移继续。

截图market-settings-draft.png。

## ai-trading-assistant-full-2026.10.28-r50

- 对照chart-core getShowMainChart逻辑补齐每窗隐藏主价格序列，保留指标及画线；价格读数换成隐藏状态说明，主图信号与筹码装饰同隐藏。
- 开关使用每窗studies保存，可与已有指标同步开关一起传播，布局恢复保持。
- 浏览器仅第二窗关闭，四窗状态true/false/true/true，刷新保持；canvas仍保留指标。交互审计和构建通过。完整迁移未完成。

来源chart-core/deobfuscated.js 46422附近；截图market-hide-main-series.png（主图信号装饰随后一并隐藏）。

## ai-trading-assistant-full-2026.10.28-r51

- 根据chart-core 52875起读数规则补充前收盘基准的涨跌额/涨跌幅及振幅；跟随当前悬停K线与回放可用数据，缺失/零基准和溢出显示无值。
- 浏览器合成CSV末收140、前收150、高145低95显示-6.67%(-10.00)、振幅33.33%，与原版公式一致。
- 计算边界检查、交互审计及构建通过；截图market-change-amplitude.png。完整迁移继续。

## ai-trading-assistant-full-2026.10.28-r52

- 按chart-core 52760/52902的末根收盘基准补齐光标价格差，使用主价格pane实际coordinateToPrice，副指标pane不映射成价格；切换图表和离开时清除。
- 回放基准来自已过滤的candles末根，不读取未来收盘；同步十字光标时各目标窗用自身对应K线收盘定位。
- 浏览器光标142.98相对末收148.32显示-3.60%(-5.34)，离开图表后消失。模型检查及交互审计、构建通过。完整迁移继续。

截图market-cursor-price-difference.png。

## ai-trading-assistant-full-2026.10.28-r53

- 集中运行19组check专项全部通过；git diff --check通过，移除1处行末空白；重新生产构建通过（仍有大包体提示）。
- 完整核验原始1099资源哈希、224可读脚本哈希及语法、4660模块哈希及语法；并核对当前安装app.asar与提取manifest SHA一致。
- 9份无匹配工厂的脚本完整保留，单独记录大小、哈希及包装特征；28个静态依赖ID仍未解析。文件完整性不证明运行等价或完整功能迁移。
- 仍需完成真实授权行情验证、原版编译执行、多窗对比/其他联动、非规则局部分割及其余模块功能迁移。目标保持未完成。

证据：output/aicoin-integration-20261027/regression-r53.txt、source-recovery-audit-r53.json；reference/aicoin/verification.json。

## ai-trading-assistant-full-2026.10.28-r54

- 按原版chartsSyncOptionsTips.others（样式、背景等）补齐每窗独立类型/背景及其他联动，支持布局捕获/恢复。浏览器独立第三窗美国线，其余HLC；开启其他后第三窗面积图传播到四窗。模型及构建通过。
- 用户目标扩大到交易所API连接页面和功能，要求真实可用。审计发现旧授权向导及检查仅写本地假成功；已改为未连接账户草稿，检查不宣称成功，临时禁止在尚未接线的演示字段输入真实密钥。
- 后端broker-connections仅登记api_key_ref，create_config未请求交易所；不得作为真实连接证据。已有local_secrets可作为后续安全接入基础，尚未实施真实适配器连接。
- 后续必须完成服务认证/CORS下的真实密钥导入、交易所连接与权限核验、只读资产/账户获取、错误处理及各交易所验证；订单另需实盘确认。不得把当前前端模拟记录当作已完成新增目标。

截图market-appearance-sync.png。完整目标保持未完成。

## ai-trading-assistant-full-2026.10.28-r55

- 定位8000实际为Fieldwork desktop_server，非交易后端；未修改该服务。独立启动交易后端127.0.0.1:8001，禁启自动调度器，前端默认API_BASE改为8001（环境变量仍可覆盖）。
- /health实际service=ai-trading-os-backend、数据库/Redis均ok；assets和data-sources/providers返回200，Origin localhost:3002的CORS正确。
- 浏览器显示API已连接，行情明确显示缺少匹配USDT与平台的标的数据并演示回退，不再为错误服务的跨域失败。
- 增加scripts/start-trading-backend.sh供重启，复用交易系统现有Python依赖环境，可用TRADING_PYTHON指定。构建和行情模型检查通过。
- 已有BinanceSpotReadOnlyAccountAdapter支持签名/api/v3/account读取，凭证导入及授权页仍需接线；本轮没有真实密钥/交易所授权验证。完整目标未完成。

截图market-correct-backend.png。后端当前exec session72797，进程42159，后续须实时核对存活状态。

## ai-trading-assistant-full-2026.10.28-r56

- 后端新增POST /exchange-connections/binance/probe，复用现有身份权限，签名GET官方时间/Key权限/账户接口；Key权限与账户canTrade分开判断，仅明确只读时返回余额。
- URL固定官方域名、TLS校验、拒绝携带凭证重定向、不回显请求/交换错误文本；本次只验证不持久化凭证，不提交订单。
- 授权列表新增币安只读API验证页面，实际请求后端、显示权限错误和余额，finally清空Key/Secret，不写浏览器存储。
- 9项后端测试通过（合成响应/签名/危险权限/余额异常/错误脱敏/角色），运行服务负向422验证成功；浏览器短测试值返回密钥格式错误且密码字段清空。构建通过。
- 官方依据https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account。真实用户密钥成功路径、持久化账户连接与其他交易所尚未完成，不宣称全面可用。

截图binance-readonly-probe.png。服务当前session3374、PID43506，需实时核对存活。

## ai-trading-assistant-full-2026.10.28-r57

- Binance验证页新增显式保存凭证选项及连接名称，默认不保存；明确本机文件0600、未加密。新增保存连接列表、重新验证并读取余额、确认禁用并移除凭证流程。
- 后端新增用户隔离连接创建/列表/检查/禁用，数据库仅存引用及权限元数据，重新检查实际发签名请求；失败改为verification_failed，禁用后拒绝检查。
- 本机密钥文件升级为fcntl互斥+0600临时文件原子替换；增加git忽略。账户查询前刷新服务器时间，避免前序权限查询耗时导致签名过期。
- 19项后端测试通过，含完整HTTP合成生命周期、用户隔离、无密钥回显、失败不保存、禁用清理、原LLM密钥回归。构建/前端交互审计通过。运行服务GET连接列表200且no-store、当前0条；浏览器验证保存选项和空凭证拒绝。
- 没有输入真实用户密钥，成功路径仍为合成交易所响应测试；其他交易所、交易权限/下单及完整AiCoin迁移仍未完成。

截图binance-saved-connections.png。服务当前session25653，后续实时确认存活。

## ai-trading-assistant-full-2026.10.28-r58

- 新增OKX全球站只读探测，三字段Key/Secret/Passphrase，时间同步、Base64 HMAC-SHA256签名，固定官方主机与GET路径；account/config perm必须恰为read_only后读取交易账户余额。
- OKX接入保存、列表、重新验证、禁用和凭证移除，同样用户隔离、DB仅存引用。前端选择交易所会清空旧凭证，OKX显示Passphrase和交易账户范围说明。
- 27项组合后端测试通过（OKX签名、权限拒绝、余额错误、持久化Passphrase复用与删除、Binance及原密钥回归），构建与交互审计通过；浏览器Passphrase必填及短Key后端拒绝、三个密码字段清空验证通过。
- 官方依据https://www.okx.com/docs-v5/en/。未使用真实OKX用户凭证，未覆盖区域专属域名、资金账户或实盘交易。其余交易所及完整迁移继续。

截图okx-readonly-connections.png；当前后端session40986，需实时核对存活。

## ai-trading-assistant-full-2026.10.28-r59

- 接入Bybit全球站UNIFIED只读验证/保存/复查/禁用，HMAC-SHA256请求签名与公开时间同步；Key信息readOnly必须整数1，并拒绝钱包转账/提现权限。
- 余额保留钱包余额、权益、冻结额；逐币种可用余额在官方接口已废弃，不进行虚构换算，前端显示未提供。持久连接返回balance_scope。
- 37项组合后端测试通过；真实网络公开服务器时间可达；浏览器Bybit字段与后端格式错误验证通过。构建/交互审计通过；验证超时扩至45秒以容纳四次受限时请求。
- 官方依据bybit-exchange.github.io/docs/v5/user/apikey-info、account/wallet-balance、guide。仅全球站统一账户，区域专属域名/资金账户/真实私有账户成功验收未覆盖，完整目标继续。

截图bybit-readonly-connections.png；当前后端session19013，后续实时核对。

## ai-trading-assistant-full-2026.10.28-r60

- 新增Bitget V3统一账户只读验证、保存、复查和禁用；三字段Key/Secret/Passphrase，服务器时间同步及Base64 HMAC-SHA256签名，固定官方GET路径。
- 读取account/info的明确read-only/readonly权限类型，拒绝提现及未知权限；按account/assets对象内assets结构解析可用、锁定、账户余额和权益。
- 44项组合后端测试通过，真实公开时间接口可达；浏览器Bitget短Key后端拒绝及三个密码字段清空通过。构建和交互审计通过。
- 官方依据www.bitget.com/docs/catalog/account/account-settings、assets-balance与classic/rest-api。当前不是旧版V2现货或资金账户，真实用户密钥正向验收仍未完成。其余交易所和完整前端迁移继续。

截图bitget-readonly-connections.png；服务当前session68651，后续实时核对。

## ai-trading-assistant-full-2026.10.28-r61

- Gate全球站主账户经典现货接入只读验证/保存/复查/禁用，固定api.gateio.ws路径、空体SHA512与HMAC-SHA512签名、公开毫秒时间转秒。
- 使用account/main_keys精确匹配当前完整Key，状态正常且经典模式、各权限read_only严格true并包含spot才读取余额；掩码/其他Key/写权限/统一模式均拒绝。
- 52项组合测试通过（含Gate签名、掩码不误匹配、权限拒绝及保存生命周期）；公开时间实网可达；浏览器格式错误真实返回。构建及交互审计通过。
- Gate接口若只返回掩码将明确报告权限无法核实，不降级判成功；真实私有账户、子账户与统一账户仍未验收。现有五家交易所均有特定范围只读接入代码，不等于全面可用或实盘交易完成。

官方依据www.gate.com/docs/developers/apiv4/en/account/及spot/；截图gate-readonly-connections.png。服务当前session36491，后续实时核对。

## ai-trading-assistant-full-2026.10.28-r62

- 授权主页接入真实后端连接列表、重新验证读取余额、禁用及确认移除；原有本地草稿单独标识未连接，安全说明同步真实保存机制。
- 抽取共享余额与连接列表组件，验证权限证明/响应字段/重复资产，保留高精度数字字符串，丢弃密钥与引用字段，余额50项分页，缺失金额不补零。
- 隔离8002内存DB/临时秘密文件+3003前端，用固定假Key和合成HTTP传输验证五家真实签名代码；浏览器五家创建保存、余额展示、返回主页5条、逐家重新读取、刷新仍5条、逐家禁用后全部不能读取，API确认5条均无凭证引用。
- 该正向验收没有访问真实交易所私有账户，不可替代真实Key验收。测试服务及空的临时凭证目录已清理，正式3002/8001未停止。
- UI模型检查、交互审计和构建通过；52项后端测试为此前已验证基线，生产后端本轮未改行为。完整目标继续。

证据exchange-fixture-positive-results.json、exchange-fixture-disable-results.json；截图auth-real-connections-home.png（正式空列表）、exchange-fixture-positive-home.png及exchange-fixture-disabled.png（合成夹具）。


### r63 公开现货K线
- 行情主窗及分窗在本地缺失/空数据/网络不可用时，接入固定官方公开域名 Binance USDT 现货K线快照；不携带凭证，不跟随重定向，支持官方原生周期及周/月映射。
- 严格校验OHLC、时间、重复记录和数量，错误及不支持周期明确回退原因；401/403与无效数据库记录不触发替代。快照明确非实时推送。
- 新增公开行情检查和原有行情模型检查通过，交互静态审计通过，最终构建通过（保留已有包体积警告）。浏览器真实加载BTCUSDT 1h并切换5m成功，截图market-public-binance.png。
- 本轮未验证其他交易所公开行情、实时刷新或私有账户实盘交易；完整迁移目标仍在进行。


官方依据：https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md


## ai-trading-assistant-full-2026.10.28-r64

- 主窗和独立分窗请求完成后每30秒刷新，页面隐藏暂停、返回立即读取；CSV与共享分窗不重复请求。销毁时取消请求和计时，迟到响应不回写。
- 公开快照显示获取UTC时间和轮询说明，失败明确回退为演示，不将旧快照误标为新成功；复盘仍使用既有冻结数据。
- 新增调度检查覆盖无请求重叠、隐藏暂停/恢复、卸载取消、迟到响应丢弃；公开行情检查、静态交互审计、最终构建通过。
- 浏览器BTCUSDT 1h公开快照时间从13:25:40.462Z自动更新至13:26:11.196Z，截图market-public-refresh.png。完整实时推送、多交易所与真实私有账户交易仍待完成。



### r65 OKX公开行情


- 主窗/分窗公开快照回退新增OKX全球站USDT现货，固定www.okx.com/api/v5/market/candles，不携带凭证、不跟随重定向，沿用30秒完成后刷新机制。
- 日/周/月/季及6/12小时明确使用UTC参数，拒绝8小时等不支持周期；严格校验成功code、9列记录、毫秒时间、收盘标记、OHLC/成交量及重复时间，按时间升序显示，末根可能未收盘提示。
- OKX新增模型检查、Binance公开行情回归、静态交互审计和构建通过。curl实网成功，浏览器平台切换后OKX BTC-USDT 1h成功；UTC日线亦成功，截图market-public-okx.png。
- 完整多平台行情、实时推送和真实私有账户交易目标仍未完成。


官方周期与字段依据：https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks


## ai-trading-assistant-full-2026.10.28-r66

- 左侧行情列表接入Binance/OKX公开现货24小时报价与成交额；30秒完成后轮询，平台切换即清空旧报价，缺失不以固定数值补齐。股票列表明确演示，未接入平台明确不可用。
- 涨跌幅按交易所24小时开盘价计算，与图表单根涨跌区分；成交额排序使用真实USDT成交额。校验平台/报价币、SPOT类型、时间、价格成交额、重复记录，失败不保留旧成功。
- 新增报价模型检查、静态交互审计、最终构建及差异格式检查通过。浏览器币安BTC/ETH真实报价成功；切OKX时先清空并显示暂无报价，随后读取OKX BTC/ETH成功。截图market-live-ticker-list.png。
- 主界面其他装饰数值/行情频道、其他平台、实时推送及真实私有账户交易仍待补齐，完整目标未完成。


官方字段依据：https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market 和 https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-tickers


## ai-trading-assistant-full-2026.10.28-r67

- 顶部币对报价移除固定演示价格，优先当前平台24小时ticker，缺失时使用对应K线快照，明确24h/本根涨跌；无数据显示暂无报价。
- CSV使用自身数据，复盘使用冻结游标原始K线且不读取当前ticker，防止顶部泄露复盘未来价格。
- 新增报价优先级/缺失/非法值/复盘不泄露测试通过，交互静态审计与构建通过。浏览器公开顶部BTC为80806，进入复盘后变为历史游标82783.54并明确标注复盘原始K线；截图market-headline-replay.png。
- 其他报价区域/模块及完整多平台实时行情与真实账户交易仍待补齐，整体目标未完成。



## ai-trading-assistant-full-2026.10.28-r68

- 右侧盘口移除生成的固定买卖档位，新增Binance/OKX公开USDT现货快照，沿用请求完成后30秒轮询及隐藏暂停、取消机制；股票/未接平台明确不可用。
- 卖价升序/买价降序取最近9档，累计量按基础币真实数量计算，深度条按累计数量比例，显示真实买卖价差和获取时间；拒绝重复价格、无效数量及交叉盘口。
- 档位点击只向原订单面板预填快照价格，不下单；上方市场概览、成交/资金页尚为演示并新增明确标记。
- 新增盘口模型检查、交互审计（包含新组件）及构建通过。浏览器Binance真实盘口成功，点击卖档80773.72后显示“尚未提交委托”。截图market-public-depth.png。OKX盘口实网curl本轮超时，尚无浏览器正向验收，不宣称已实网通过。
- 完整实时盘口/成交资金流及真实账户交易仍未完成。


接口依据：Binance /api/v3/depth 与 OKX /api/v5/market/books 官方文档。


## ai-trading-assistant-full-2026.10.28-r69

- OKX盘口新增交易所ts严格校验，分别显示交易所快照UTC时间与本机获取UTC时间，避免混淆数据生成时间。
- 盘口校验新增无效ts拒绝案例，测试及最终构建通过，差异格式检查通过。
- OKX实网curl成功；浏览器首次读取超时，下一轮自动恢复，BTC/USDT买卖档位及交易所13:46:45.506Z/获取13:46:46.495Z成功展示，再轮询至13:47:17.616Z。截图market-okx-depth-verified.png，补齐r68缺失的OKX盘口浏览器正向证明。
- 本轮未完成OKX档位点击的额外浏览器验证（刷新替换节点导致定位失效）；共享价格预填处理此前Binance已验证。本轮未提交任何交易，完整目标仍在进行。



### r70 公开成交


- 右侧成交页移除固定价格数量时间，接入Binance/OKX USDT现货最近20笔公开成交快照，30秒完成后轮询并显示获取时间/非连续成交流提示。
- 严格校验标的、成交ID唯一性与整数精度、成交时间、价格数量及买卖方向；Binance isBuyerMaker=true映射主动卖出，OKX side按taker解释，UTC毫秒时间，点击仅预填不提交。
- 新增成交模型检查、交互审计、构建和diff check通过。浏览器Binance真实BTC成交成功，截图market-binance-public-trades.png；OKX亦成功展示真实成交，截图market-okx-public-trades.png。
- 资金流、概览、更多平台与实时推送及真实账户交易仍未完成。


官方依据：Binance /api/v3/trades 与 OKX /api/v5/market/trades。


## ai-trading-assistant-full-2026.10.28-r71

- 盘口概览/简况移除固定成交额、高低价、市值、波动率，使用当前平台/币种公开ticker的24小时成交额、高低价与振幅；市值和净流入明确未接入。
- ticker新增高低价范围校验，振幅明确(高低差)/24小时开盘；单标的概览改用Binance单ticker对象及OKX单ticker接口，避免为单个币读取全市场。
- 新增单标的响应及高低价/振幅检查，报价测试、静态审计、构建和diff check通过；浏览器Binance真实成交额1025478524.8307317、高81823、低79890，简况振幅2.42%且市值未接入。截图market-public-overview.png。
- OKX概览本轮仅模型验证未做独立浏览器验收；资金统计和更多模块仍待接入，完整目标未完成。



### r72 Bitget K线


- Bitget公开USDT现货K线接入主窗及分窗回退和30秒轮询，固定api.bitget.com V2现货端点，无凭证/禁止重定向；日周月线使用UTC参数，拒绝不支持周期。
- 按官方8列结构解析基础币成交量，严格成功code=00000、时间/重复/OHLC校验；末根未收盘明确提示。
- 新增Bitget校验、Binance/OKX公开行情回归、静态交互审计、构建及diff check通过。浏览器Bitget BTCUSDT 1h真实返回成功，UTC日K亦成功，截图market-bitget-public-candles.png。
- Bitget报价列表/概览/盘口/成交本轮仍未接入，其他完整迁移与真实账户交易目标继续。


官方依据：https://www.bitget.com/zh-CN/docs/catalog/classic-spot-market/classic-spot-market


## ai-trading-assistant-full-2026.10.29-r73

- Bitget V2公开现货ticker接入左列表、顶部及盘口概览/简况，统一24h开盘、高低价、报价币成交额、毫秒时间字段；涨跌及振幅沿用明确24h口径。
- 单标的请求带symbol，列表取全市场后严格筛选USDT及所需币种；成功码00000、时间、重复、OHLC范围校验，失败不显示旧平台/标的值。
- 新增Bitget报价检查、原报价回归、交互静态审计、构建和diff check通过；浏览器Bitget SOL顶部/概览成功，切BTC先清空概览，再显示BTC报价80500.33及成交额197576683.393274。截图market-bitget-tickers.png。
- 本次会话恢复时3002和8001均未监听，已启动现有前端及仅loopback交易后端，关闭调度；8001 health确认数据库及Redis正常。未改动8000。
- Bitget盘口/成交仍待接入，全功能迁移、实时推送、真实私有账户实盘仍未完成。


字段依据：https://www.bitget.com/zh-CN/docs/catalog/classic-spot-market/classic-spot-market


### r74 Bitget盘口成交


- Bitget公开现货盘口及最近20笔成交接入现有组件，固定V2端点、无凭证/禁止重定向、30秒轮询；盘口校验撮合时间与数量/排序/累计，成交校验标的/ID/时间/价格数量。
- Bitget成交方向明确为交易所字段口径，保留其他平台主动方说明；点击仅预填。
- 盘口/成交新增Bitget案例及原平台回归通过，静态审计/build/diff check通过。原“Bitget未支持”测试随实现改为Hyperliquid，并通过。
- 浏览器Bitget SOL/USDT真实盘口成功，基础币累计量和交易所时间可见，截图market-bitget-depth.png；成交页亦成功展示真实SOL成交与UTC毫秒时间，截图market-bitget-trades.png。
- 完整实时行情、其他平台和原应用其余模块及真实账户交易仍未完成。


官方依据：https://www.bitget.com/zh-CN/docs/catalog/classic-spot-market/classic-spot-market


## ai-trading-assistant-full-2026.10.29-r75

- 资产页默认新增真实交易所余额视图，复用后端已验证连接的重新核验/余额展示/禁用能力，直达只读API连接表单并返回资产余额；原资产组合/估值/流水/风控保留在明确标记的演示资产视图。
- 真实余额按连接和账户范围独立展示，不混合演示总资产/盈亏/价格，不伪造缺失字段或组合映射；明确左侧演示组合不应用于真实余额。
- 余额模型检查、静态交互审计及最终构建通过；浏览器默认真实视图读取后端空连接状态、切换演示保留、从资产直达连接页再返回成功。截图assets-real-exchange-balances.png。
- 本轮未输入真实凭证，未做真实账户余额正向验收；共享余额组件此前仅隔离夹具已验收。真实资产聚合估值、流水同步及全面交易功能仍待完成。



## ai-trading-assistant-full-2026.10.29-r76

- 修正apiRequest传外部signal时内部超时不生效：统一使用内部controller，同时订阅外部取消并清理监听，预取消立即传递。
- 已保存连接余额响应必须匹配请求连接ID/交易所且持久化状态有效；刷新列表和开始禁用先清旧余额，避免失败时仍显示之前成功结果。
- 新增超时+外部信号、主动取消、预取消与成功路径测试；新增错误连接/交易所/保存状态拒绝测试。两项检查、静态交互审计、最终构建和diff check通过。
- 本轮为请求/状态逻辑验证，未声称真实私有账户正向验收；全面功能迁移及实盘仍待完成。



## ai-trading-assistant-full-2026.10.29-r77

- 隔离8002内存DB/临时秘密文件及3003前端，实际浏览器从资产进入连接表单，以固定假Key保存明确标记夹具，再返回资产列表重新核验读取BTC可用1.25/冻结0.25，验证r76连接ID匹配可通过真实共享请求链路。
- 浏览器确认禁用后旧余额移除、读取按钮禁用；隔离后端GET确认disabled、credentials_persisted=false及order_submission_available=false。
- 证据assets-fixture-acceptance.json，截图assets-fixture-positive.png及assets-fixture-disabled.png。SIGINT正常关闭测试服务，临时文件上下文随正常退出清理，正式服务未停止。
- 此为签名验证代码配合合成HTTP传输的界面验收，没有连接真实私有账户，不替代真实Key正向证明。完整迁移及实盘仍未完成。



## ai-trading-assistant-full-2026.10.29-r78

- 视口保存增加可选barCount，兼容旧布局；新增K线时，原本跟随末根的视口保持跨度并继续跟随，历史视口保持日期，非重叠数据不套用旧范围。
- 追加/固定长度滚动/历史日期/非法barCount及旧布局模型测试通过，最终build/交互静态审计通过。DOM增加实际visibleLogicalRange用于界面验收。
- 浏览器SOL 1h公开快照17:26:23.907Z至17:26:54.247Z刷新，范围从158.7..228变为158..228，发现0.7根左边界漂移；未宣称浏览器精确保持通过。截图market-refresh-viewport.png。后续须排查多窗日期同步/重建初始化回调导致的范围取整。
- 完整迁移与实盘未完成。



## ai-trading-assistant-full-2026.10.29-r79

- 定位r78视口漂移：相同数据时间轴的多窗仍通过日期范围同步，导致逻辑范围小数边界取整。相同完整时间轴现改直接同步逻辑范围，不同时间轴继续日期同步；预期回调抑制增加精确逻辑范围分支。
- 新增相同时间轴小数同步/不同时间轴日期同步及回调不回流检查，原行情及视口检查通过；最终build/静态交互审计/diff check通过。临时恢复诊断属性已移除。
- 浏览器四窗SOL 1h缩放均158.7..228，下一轮公开快照17:30:30.457Z后四窗仍精确158.7..228，r78观察的取整问题在此场景修复。截图market-precise-range-sync.png。
- 新小时边界实网未在本轮等待，仅模型覆盖追加/滚动；全迁移和私有账户实盘仍未完成。



## ai-trading-assistant-full-2026.10.29-r81

- Binance左列表、顶部及盘口概览新增官方data-stream.binance.vision单标的ticker合并WebSocket订阅；REST30秒校准保留。其他平台沿用轮询。
- 校验订阅名/事件标的/24h价格数量字段，拒绝过旧/未来消息，逐币种时间戳合并避免旧REST覆盖新推送；15秒静默断开、1–30秒退避重连、隐藏暂停及卸载清理。
- 新增实时报价模型/生命周期检查通过，构建/静态审计/diff check通过。浏览器连续推送17:35:17.016Z至17:35:31.317Z，SOL报价101.19至101.18，概览同样实时。截图market-binance-live-tickers.png。
- K线/盘口/成交尚未切为推送，其他交易所和真实账户交易及原版其余模块仍未全面完成。


推送依据：https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md


## ai-trading-assistant-full-2026.10.29-r82

- Binance盘口新增官方depth20完整前20档WebSocket快照流，沿用最近9档显示与基础币累计；校验订阅身份、完整价格数量及更新序号，拒绝旧序号，不将partial快照误作增量合并。
- 实时状态带更新序号与本机接收时间；原流无交易所时间，不伪造。15秒静默及退避重连/隐藏暂停/卸载清理，断线回退原REST轮询，REST不覆盖有效实时档位。
- 新增模型/生命周期/序号顺序及REST隔离检查，构建/静态审计/diff通过；浏览器SOL实时盘口序号30475842325至30475843150，数量和累计量持续更新，截图market-binance-live-depth.png。
- 其他平台盘口仍轮询，K线/成交实时化及全面迁移与真实账户交易未完成。


官方依据：https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#partial-book-depth-streams


### r83 实时成交


- Binance最近成交新增官方trade WebSocket流，沿用原界面最近20笔，按成交ID去重、时间/同毫秒ID排序，拒绝同ID冲突数据及错误标的/过期事件，买卖方向按主动方。
- REST保留回补；明确重连间隙可能缺失成交，不宣称完整历史。界面最多每100ms合并更新；静默检测、退避重连、隐藏暂停和卸载清理沿用。
- 新增模型/去重/乱序/冲突/有界列表/合并更新生命周期检查，build/静态审计/diff通过。浏览器SOL实时成交显示17:39:30.997Z，后续更新至17:39:52.338Z，DOM严格20笔；截图market-binance-live-trades.png。
- K线与其他平台实时化及全原版模块/真实账户实盘仍待完成。


官方依据：https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#trade-streams


## ai-trading-assistant-full-2026.10.29-r84

- Binance公开K线历史快照后接官方UTC kline WebSocket，主窗及独立分窗接入；当前柱替换，紧邻新柱追加并保持240条，出现缺柱停止合并等待下一轮REST历史校准后重连。
- 校验订阅/币对/周期、事件时间、开闭时间边界、OHLC/成交量及收盘标记，拒绝旧事件及已收盘柱重开；REST请求期间较新的推送保留。断线显示最近推送时间并回退，15秒静默/隐藏关闭/卸载清理；重连以30秒历史校准为门槛。
- 新增柱更新/追加/缺口/月边界/REST竞态/重连清理检查通过，公开行情/视口/复盘回归及最终build/静态审计/diff通过。
- 浏览器SOL主图和ETH独立分窗真实持续推送，SOL收盘101.37至101.36、量36576.446至36702.928；缩放158.7..228跨多次推送保持。截图market-binance-live-candles.png。
- 实网新分钟/月边界和长时间掉线补齐未在本轮等待，仅模型覆盖；图表目前仍在数据更新时重建，有性能优化空间。其他交易所实时化及全原版模块/真实账户实盘未完成。


官方依据：https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#klinecandlestick-streams-for-utc


## ai-trading-assistant-full-2026.10.29-r85

- 实网1分钟边界验收首轮发现新柱时视口从约0..243缩为1..239，虽240条滚动正确但视口未通过；保留原失败证据live-kline-minute-boundary.json。
- 修正图表重建的初始化范围事件：等待两次绘制帧后才广播范围同步，初始化仍记忆本窗范围，不向其他未同时更新的时间轴回灌；清理时取消帧。
- 修复后真实跨17:47至17:48，首尾时间均前进60秒，数据仍240条，范围精确保持-2.84e-14..243。live-kline-minute-boundary-fixed.json passed=true，截图market-live-kline-minute-boundary-fixed.png。
- 最终build、实时K线检查、静态交互审计及diff通过。实网长断线/月边界、其他交易所实时化与全部原版/实盘仍待完成。



### r86 OKX实时报价


- OKX公开ticker实时推送接入原报价订阅器，使用官方443端点及subscribe/tickers协议，先REST确认存在的USDT现货标的再订阅，处理订阅回执并校验arg与data标的一致。
- 沿用时间戳合并、旧消息拒绝、静默/退避重连/隐藏暂停/清理及REST回退；状态正确显示OKX，不沿用Binance名称。
- 新增OKX消息身份与仅订阅REST确认标的检查，Binance回归、新检查及build/静态审计/diff通过。浏览器OKX列表/概览实时推送17:50:47成功，后续推送17:51:04且SOL101.75至101.78，截图market-okx-live-tickers.png。
- OKX盘口/成交/K线及更多平台实时化、全部原版功能和真实私有实盘仍待完成。


官方依据：https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-tickers-channel


### r87 OKX实时逐笔成交


- OKX公开逐笔成交使用官方443 business端点trades-all频道，避免普通trades聚合数量与REST单笔ID合并冲突；最多每100ms合并更新最近20笔。
- 校验channel/arg/每条instId/成交时间及原有ID价格数量方向，沿用重复去重、冲突拒绝、断线回退/静默重连/隐藏暂停与清理。
- 新增逐笔频道/错误频道拒绝/订阅协议检查，Binance实时成交回归、build/静态审计/diff通过；浏览器OKX SOL实时成交17:52:38.840Z成功，随后更新至17:52:45.117Z且DOM20条，截图market-okx-live-trades.png。
- 其他平台成交、OKX盘口/K线实时化及全功能/真实私有实盘未完成。


官方依据：https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-all-trades-channel


### r88 OKX实时盘口


- OKX实时盘口接官方443 public books频道，400档快照后维护增量，界面继续显示最近9档及基础币累计量；零量删除，不把增量误作完整快照。
- 严格seqId/prevSeqId连续性、标的/动作/时间/价格数量检查，支持官方序号重置及空更新保活；断序/非法数据断开回退再订阅快照。按当前官方文档checksum已停用且固定0，不用旧CRC规则误判。
- 新增快照/增量/删除/不可变状态/断序/重置/保活模型检查及Binance深度回归，build/静态审计/diff通过；浏览器OKX SOL实时序号32523746696及档位成功，后续序号32523749996与档位继续更新，截图market-okx-live-depth.png。
- OKX K线/其他平台实时化、原应用其余功能和真实私有账户实盘未完成。


官方依据：https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-order-book-channel


### r89 OKX 实时 K 线接入（2026-10-29）

官方业务频道 wss://ws.okx.com/ws/v5/business，candle + REST原生周期；仅公开行情。当前柱覆盖、相邻新柱追加，缺柱断开等待REST校准；UTC及季度月份边界计算。没有服务端事件时间，来源明确写本地接收时间。模型包含订阅、频道/标的拒绝、收盘防回退及月份边界；生产构建通过（已有大包警告）。实际浏览器正向连接及跨周期连续推送尚待验收，本轮不声称全功能完成。


### r90 浏览器实时K线验收与加载态（2026-10-29）

实际3002浏览器观察OKX SOL-USDT 1h持续推送，切换1m成功重新订阅（07:59:23.722Z，收99.80，量3.80663）。热更新重置平台后重新选择OKX，加载态显示读取标的和周期且隐藏演示画布；08:00:39.227Z 1h实时新柱开99.76收99.80量8.992475。截图output/aicoin-integration-20261027/market-okx-live-candles.png。35个模型脚本全通过，后续加载态改动构建和diff通过。并未连续观察同一订阅跨小时，因此不将该截图称为跨柱连续性验收；尚未完成全部迁移、真实账户与实盘。


### r91 行情与后端连接管理衔接

行情下单面板不再跳旧本地授权草稿，主连接入口进入后端真实只读连接管理。移除不会发送或保存真实密钥的错误说明，显示实际后端转发和按需保存行为；交易工具维持原有入口并明确尚未执行真实委托。浏览器确认连接管理及五平台验证表单可达，没有输入真实凭证。交互静态检查及构建通过（已有大包警告）。截图market-api-connection-handoff.png。只读连接不等于订单执行，后者仍是完整目标待办。


### r92 状态栏报价一致性

App接收行情headline的基础值快照，状态栏使用相同标的/模式/平台/价格/涨跌/来源；行情页外显示未提供报价，拒绝旧标的快照。撤掉固定费用/线路/日期/主力挂单金额和恐惧贪婪值。加载行情时额外信号及筹码图层同时隐藏。浏览器实际顶部SOL99.87/-2.40%和底栏同源，授权页空值。主状态栏构建、交互静态检查通过；截图market-footer-real-quote.png。


### r93 Bitget V3实时报价

按照官方https://www.bitget.com/docs/uta/websocket/public/Tickers-Channel 与quick-start，使用wss://ws.bitget.com/v3/ws/public，instType spot/topic ticker/symbol BASEUSDT。arg/action/ts身份验证，原生24h字段映射到共享严格报价模型；REST存在性校验后订阅，断线回退。模型检查及构建通过，浏览器来源推送时间08:06:10.069Z→08:06:19.119Z持续更新。截图market-bitget-live-tickers.png。仅报价实时化，Bitget K线/深度/成交仍轮询，完整目标继续。


### r94 Bitget公开实时K线

官方V3 public spot/kline原生周期1m/5m/15m/30m/1H/4H接入REST历史校准；较长UTC周期尚未确定边界所以保持REST。严格验证基础币成交量/价格/标的/周期/推送时间。实际初始消息500柱（约67KB），修复单柱假设及64KB上限为有界512KB/1000柱，逐柱验证后用最新柱衔接历史；不将历史快照旧柱覆盖新柱。服务端不提供收盘标志，来源写明。浏览器真实分钟线08:10:10.363Z收100.00量41.9012→08:10:15.545Z收100.04量120.8261，截图market-bitget-live-candles.png；模型与构建通过（已有大包警告）。本轮小时线REST曾超时，尚未完成小时线实际验收、长断线和跨柱等待；完整目标未完成。


### r95 Bitget公开实时成交

官方https://www.bitget.com/docs/uta/websocket/public/New-Trades-Channel，V3 spot/publicTrade。批量消息按i/p/v/T/S解码，string ID精度保留，基础币数量、字段方向、推送时间及update成交时间校验；首次snapshot允许历史成交，避免低流动性历史快照造成错误重连。实时阶段不合并V2 REST未经证明等价的执行ID；非实时回退REST来源明确。浏览器08:12:11.937Z→08:12:23.126Z连续成交更新，截图market-bitget-live-trades.png。模型、构建、diff通过。只展示最近20笔，不承诺断线完整成交历史；Bitget盘口实时与完整目标仍未完成。


### r96 Bitget实时盘口

官方https://www.bitget.com/docs/uta/websocket/public/Order-Book-Channel明确books50也是增量频道，采用spot books50首次快照/后续update。首次更新pseq≤快照seq≤新seq，后续pseq精确等于上一seq；pseq0重置或缺口回退重订阅。seq/pseq解析前保留整数原值，BigInt比较，避免官方示例超过安全整数失真；有界50档状态，零量删除，价格唯一、排序和交叉检查，前9档累计基础币数量。浏览器SOL序号1159942882053（08:14:04）→1159943383138（08:14:15）实际连续更新，截图market-bitget-live-depth.png。新增模型与已有深度模型、构建通过（已有大包警告）。没有真实订单执行验收，其他原应用模块继续迁移。


### r97 真实深度主页面

深度tab原固定曲线和82.4M/79.8M金额替换为MarketDepthWorkspace。与PublicOrderBook共享单订阅快照，不重复拉取，按可见9档基础币数量绘图。百分比分组买盘向下/卖盘向上取整，累计与增量（分组数量）模式；可见量不冒称全平台完整深度。AI入口使用实际快照描述。浏览器Bitget SOL序号1159951130157时实际曲线及可见买量22218.1252/卖量18157.0083，中间价100.015；切增量与0.01%成功。模型、静态交互、构建通过（大包警告）。截图market-real-depth-workspace.png。其他资金流/合约等模块仍待真实化，完整目标未完成。


### r98 深度页与主图上下文同步

深度页平台从内部独立状态改为Market受控平台，新增交易对选择并写入共享标的；报价底栏随同一Market headline更新。未接入平台选择不静默替换币安，股票入口保留明确尚未接入状态。浏览器深度切OKX ETH后主图标题/图窗/侧栏/底栏均OKX ETH，返回深度选择保持。截图market-depth-context-sync.png仅证明往返选择，不替代本轮未等待完成的深度WS重连证明。37个模型脚本全部通过，静态交互审计、构建、diff通过（已有大包警告）。完整目标继续。


### r99 自选主页面真实报价

MarketWatchWorkspace取当前市场已自选标的和共享平台，observePublicTickers驱动价格/24h涨跌/报价币成交额，换平台和列表身份拒绝旧数据。数值排序缺报价置尾，真实平台同源，不交替假分配Binance/OKX。保留管理自选、增加查看图表带标的和平台。浏览器观察币安WS来源，切Bitget并价格排序，SOL进入主图保留Bitget；截图market-real-watchlist.png。静态交互及构建通过（已有大包警告）。本轮未做全部空值/所有排序浏览器组合验收，股票行情尚未接入，完整目标继续。


### r100 合约数据主页面首批真实数据

OKX /api/v5/public/funding-rate + open-interest?instType=SWAP，身份固定BASE-USDT-SWAP；明确当前周期资金费率不年化，持仓oi张/oiCcy基础币/oiUsd美元价值分列，两个时间分别显示。匿名固定官方GET、超时外部取消、30秒轮询，无授权或订单。浏览器ETH当前费率0.006371%、持仓665912.021 ETH，资金费率更新时间08:24:27、持仓08:24:50，截图market-okx-perpetual-data.png。模型、静态交互、构建diff通过。其他平台/多空比/爆仓/合约成交额未接入，主图及底栏仍现货，完整目标继续。


### r101 Bitget永续资金费率与持仓

官方https://www.bitget.com/docs/catalog/market/derivatives，V3 current-fund-rate与open-interest固定category=USDT-FUTURES&symbol=BASEUSDT；严格成功码、单标的身份、正负费率、周期枚举、毫秒时间及非负持仓校验。Bitget OI官方定义多空之和，不能无标注与单边口径比较；费率未提供更新时间，显示requestTime为请求时间；张数和USD值保留空。浏览器ETH0.007500%/8小时，OI796021.44 ETH，请求时间08:26:48.490Z，截图market-bitget-perpetual-data.png。模型、静态交互、构建diff通过（已有大包警告）。币安及其他合约指标/完整迁移未完成。


### r102 币安永续公开数据

官方fapi/v1 exchangeInfo、premiumIndex、openInterest固定公开GET。exchangeInfo拒绝非PERPETUAL/非TRADING/非匹配baseAsset或USDT报价保证金币种；资金费率和OI同时匹配symbol。最近资金费率lastFundingRate保持原语义，不当作未来预测；基础币OI不当作张数或美元。浏览器ETH0.003964%及2403608.252 ETH，费率08:28:23/OI08:28:19，截图market-binance-perpetual-data.png。模型、静态交互与构建通过。当前三平台合约页均匿名快照，不代表真实账户或订单执行，完整目标继续。


### r103 首批真实资金流

Bitget官方https://www.bitget.com/docs/catalog/market/trading-stats，V3 spot-fund-flow固定symbol及白名单period，匿名GET 30秒轮询。验证非负Whale/Dolphin/Fish买卖量后计算净量和总量；无单位/阈值证据所以不标美元或推断主力，requestTime显示接口请求时间。保留周期/标的/平台/分组筛选及实际快照AI入口。浏览器ETH1h买2047.5761/卖1496.6598/净550.9163，08:30:26请求时间，Whale筛选执行；截图market-bitget-fund-flow.png。模型、静态交互及构建diff通过。其他平台尚未接入，完整目标继续。


### r104 行情入口清理与集中回归

四个行情tab全部已有实际工作区，删除不可达的旧固定资金流/合约金额/假自选平台表格与无效状态。静态审计改为要求真实四组件及对应控制名称，不继续检查死代码的旧字符串。39个模型脚本全部通过；589按钮/215控件都有handler（仅静态，不证明业务端到端），构建通过且大包警告仍在。记录regression-r104.json。完整原应用迁移、真实私有账户和订单执行仍未完成。


### r105 API验证响应绑定

ExchangeProbePanel改用validateProbeSnapshot绑定本次exchange和save，不再只校验任一支持平台的通用合法快照。要求保存布尔值显式且一致，保存时ID非空且长度有界；失败不展示余额成功。余额拒绝Number非有限输入以及大小写重复币种，原始字符串精度仍保留。保存请求失败或结果错配仍刷新下方连接元数据，提示核查避免重复保存。正负模型、静态审计与构建通过；未输入真实密钥，未做新的真实私有账户正向验收。完整目标继续。


### r106 平台卡片直达真实验证

添加授权卡片旧apiAuth草稿跳转改为ExchangeProbePanel(initialExchange)，平台ID固定映射，白名单初始化及key重新挂载；对应真实账户范围说明更新，安全说明CTA同样真实验证。本地草稿入口保留独立说明。授权频道变化关闭子表单。浏览器五平台逐家点击、预选、返回均成功，Bitget实际Passphrase字段存在；无凭证输入。静态交互与构建通过（大包警告）；api-platform-card-selection.json及api-platform-card-form.png。仅入口与表单验收，非真实账户验证，完整目标继续。


### r107 默认实时视图复用图表实例

新增当前柱复用路径，仅支持MA/Volume等基础显示开关且非复盘；完整历史OHLCV签名+末根时间判断可复用，任何历史修正或时间轴变化重建。主序列用LW公开update，MA和Volume setData，十字光标回调使用最新candles引用避免闭包旧价。复杂指标保持原完整重绘。浏览器OKX ETH一小时当前柱收2317.22→2317.09、量3464.151115→3464.69476，chartInstance一致且缩放范围147.3..239不变，控制台error空。记录chart-live-instance-reuse.json/png。专项模型/视口模型/交互静态/构建通过；跨新柱仍完整重建，本轮不称全指标增量或性能基准完成。完整目标继续。


### r108 标准指标实时实例复用

EMA/BOLL/VWAP及三类振荡指标加入当前柱更新路径，沿用已有公式；BOLL/VWAP初始化和更新共用生成函数，振荡指标每次更新计算一份供DIF/DEA/柱/RSI/KDJ各线使用。浏览器启用MA/Volume/EMA/BOLL/VWAP/RSI/MACD/KDJ，OKX ETH1m收2316.34→2315.69，量0.013494→8.171506，RSI50.72→47.73、MACD/KDJ同时变化，实例cc45d167与视口108..239一致，无error。chart-live-studies-reuse.json/png。模型、振荡公式回归、静态交互、构建diff通过。测试后关闭额外指标。未逐条独立导出对比八个序列、未证明全原版指标或新柱无重建，完整目标继续。


### r109 真实近期大额成交筛选与演示边界

高级大额成交使用observePublicTrades真实最近20笔，用户设置USDT notional门槛与买卖方向，price×基础币quantity计算金额，详情含原执行ID与UTC时间。不是完整大单历史/交易者身份推断。复盘及股票未接入场景不订阅实时。真实主图隐藏固定大单胜率、B/S及筹码分布演示层，选中未接入统计显示文字；其他高级面板显著标演示样例，复盘时不提供假历史统计。浏览器币安ETH实际WS成交08:45:06.781买入3428.379045 USDT，门槛0和买入筛选执行，截图market-large-trades-real.png。模型、静态交互、构建通过。对比同步明确禁用仍待窗内对比序列实现，完整目标继续。


### r110 整体美观要求首轮表单与高级行情整理

用户新增“注意整体UI美观”，应用本地redesign-existing-projects技能，保持现有UI结构和技术栈。视觉检查原连接表单左侧拥挤、checkbox与说明分离、原生控件风格不统一。新增exchange-connection-ui.css：居中1120px、621px表单与按当前平台说明双栏，保存复选框行内，统一字体/边界/间距/焦点/禁用/错误框，1000px以下单栏规则；高级行情面板宽430px、数据11px、说明12px与金额右对齐。浏览器OKX+保存名称+空Passphrase错误实际可用，无凭证输入，实际formOverflow false。恢复未保存选项并存api-connection-ui-polish.png；静态交互/构建/diff通过。没有实际窄屏或完整主题组合验收，整体UI与全功能迁移继续。


### r111 行情数据页统一视觉

沿用已读取的redesign-existing-projects技能，三类页面加market-data-workspace作用域，限制1600px并居中，统一平台/标的/周期控件、来源状态、数字表格；表格容器独立overflow-x:auto，避免列宽挤破正文。错误/未接入有独立色阶，资金流分组aria-pressed可见选中。浏览器合约区1600px、表1486px无横向溢出，Bitget资金流真实来源且Whale筛后1行，自选最新价排序箭头下降有效。market-data-ui-polish.png已查看实际效果。静态交互与构建diff通过，仍大包警告；没有窄屏或完整主题组合实测。功能和整体UI完整目标继续。


### r112 当前UI五平台隔离流程验收

只运行已有exchange_browser_server.py，内存SQLite+临时凭证目录，传输函数逐个断言真实probe的签名但不外连，无网络fallback；3003显式VITE_API_BASE_URL=127.0.0.1:8002，不连接生产8001。OKX保存、密码字段清空、刷新保留、重新核验余额BTC1.25/0.25、禁用失效通过。Binance/Bybit/Bitget/Gate保存、清空与禁用均通过，各平台也执行重新验证动作（四者未逐个保存余额读数断言，不扩大证据）。Gate仅验证模式返回明确未保存。后端最终5条均disabled、credentials_persisted false、order_submission_available false。JSON api-fixture-five-platforms-r112.json；截图api-fixture-recheck-r112.png是合成账户余额，不是真实资产。两测试服务正常退出，端口无监听，临时目录随context清理。完整目标继续。


### r113 多连接管理筛选与分页

connectionListPage按NFKC/大小写无关名称平台搜索、精确平台与凭证状态筛选，再25条分页，页码合法化与数据收缩夹取。UI筛选/翻页清除旧余额与待禁用弹框，确认显示目标名称平台。列表reload用AbortController取消前次请求、generation拒绝过期响应，卸载取消。61条纯模型覆盖末页命中/组合筛选/空集/越界；浏览器现有空列表搜索/OKX/disabled选择与无横向溢出通过，未建立61个浏览器账户或网络竞态模拟。静态交互595按钮219控件、构建通过。api-connection-list-filters.png。完整目标继续。


### r114 余额搜索与原精度表格

余额展示按NFKC/大小写无关币种搜索，再50条分页，不对金额做Number转换或四舍五入；换验证快照清空搜索。表格独立横向滚动、数字列右对齐并等宽。121条模型验证跨页目标/空集/越界/原小数字符串及null；本地3003/8002隔离Bybit成功后btc命中1行，cells BTC/未提供/0.25/1.5/1.75，missing为空，清空恢复，无布局溢出。截图api-balance-search-fixture-r114.png是合成余额。静态交互与构建diff通过，两临时服务正常退出。完整目标继续。


### r115 新增目标：资讯及时性与设置AI Key首批接入

用户扩展目标：消息及时、资讯API和AI Key可在设置配置并使用。暂缓尚未修改的45m聚合调查，优先AI服务设置，接既有/production/human-control/status、llm/credentials、llm/test-call。字段只在组件内存，提交后Key清空；保存不自动调用。模型/预算/授权修改与已保存配置不一致时禁用测试；载入响应不覆盖已编辑表单。原后端mock也可测试成功，现明确blocked且未尝试外部，实际测试回报模式/平台/模型/尝试标记供UI匹配；8个后端测试通过（包含替代provider模型，非真实API验证）。浏览器仅读已有非秘密配置、空Key提交本地拦截，未保存密钥或调用外部AI。长设置弹窗修复min-height后main598px、内容475px且可滚动、标题及footer可见。settings-ai-provider-r115.png。静态交互与构建通过（大包警告）；8001确认旧PID6105及cwd后正常重启既有脚本，新session1743，scheduler关闭。资讯Key配置和信息聚合及时性链路、所有AI入口接同配置尚待完成，完整目标继续。


## r116 — 资讯来源、设置与真实消息页面（2026-10-29）

保留3002现有导航和页面结构，替换快讯/要闻专页及共用资讯侧栏中的固定消息。资讯展示为来源标题、摘要、发布时间与原文链接；没有正文时不生成正文。频道和当前标的使用标题/摘要关键词筛选，明确不等同于AiCoin原始频道分类或完整关联集合。侧栏当前标的支持BTC/bitcoin、ETH/ethereum/ether等名称。

新增 `/news-feed/settings`（GET/PUT）、`/news-feed/latest`（GET）及 `/news-feed/refresh`（POST）：遵循现有production_user认证与readiness:read/secrets:write权限。设置/缓存按LocalUserConfig.user_id隔离，NewsAPI Key使用用户摘要命名，仅存本机0600未加密凭证文件；响应、DB配置、URL不携带Key。缓存身份包含来源、检索、股票、语言与凭证版本；失败不覆盖最近成功消息与获取时间。每用户进程内并发请求去重及30秒冷却，未宣称跨进程全局额度保证。保存不请求来源，测试单独发起；自动获取仅在相应组件打开且页面可见时启用。

- Cointelegraph官方公开RSS：默认来源，每60秒自动获取；真实网络及3002浏览器成功显示30条，最新来源发布时间为2026-10-29T15:00:02+00:00，获取时间独立显示。RSS禁跳转、2MB上限、拒绝DTD/ENTITY；HTML摘要转为文本，不加载远程图片。
- Nasdaq公开股票新闻：保留独立选择与股票配置，本轮真实网络未能连通，UI显示失败，不宣称可用。
- NewsAPI `/v2/everything`：固定HTTPS主机、X-Api-Key请求头、publishedAt排序、最大100条；配置支持关键词及中文/英文/全部语言。官方开发套餐24小时延迟与额度限制已在界面注明。切换该来源默认900秒并关闭自动获取，可自行开启；保存Key不构成验证成功。
- 要闻阅读模式实际隐藏列表；朗读从当前选中DOM标题/摘要取文本，切换消息取消旧朗读。未实际播放音频验收，不宣称浏览器语音引擎正常。
- 旧 `/research-feeds/news/latest` 为既有研究快照读取入口，与新用户隔离新闻流分开；新页面使用 `/news-feed/*`。

验证边界：前端44模型脚本通过（含链接/去重/日期/筛选），后端news_feed21、research_feeds10、LLM凭据14合计45通过；交互审计590按钮/235控件均有处理器，属于静态证据；构建通过且保留既有大包提示。隔离8002/3003环境的NewsAPI合成Key验证保存后清空、请求头传递、成功响应、CPI筛选及文章切换，无真实Key/外网fallback。真实RSS快讯/阅读/资讯侧栏/当前ETH筛选及阅读模式在浏览器验证，截图 `output/aicoin-integration-20261027/news-live-reader-r116.png`。

仍未证明：真实NewsAPI账户、AI Key真实调用及其它AI入口统一配置、Nasdaq可用性、持续长期时效SLA、中文原生消息源、完整多源合并与AiCoin所有资讯分类、完整行情/交易/API功能与实盘。完整目标继续进行。

r116补充：自动请求使用 `POST /news-feed/refresh?automatic=true`，后端再次检查自动开关与配置间隔，避免专页和侧栏各自定时器导致额外来源请求；手动请求保留30秒冷却。独立组件共享间隔测试覆盖31秒拒绝、61秒成功及关闭后不请求。最终8001后端已重启采用本轮代码，PID42804，调度器继续关闭；8002/3003隔离服务已停止且临时凭证目录清理，未修改真实NewsAPI/AI Key。


## r117 — AI设置连接实际研究入口（2026-10-30）

核对发现，悬浮AI原先直接生成固定字符串；首页智搜调用确定性command-bar而非保存的LLM配置；aceResult弹窗还叠加了固定行情分数/价格。现将两个入口接到认证用户保存的LLM配置，并让aceResult仅展示通过验证的模型输出或明确错误。command-bar既有其它业务入口保持原实现。

接口：`GET /production/human-control/llm/chat/status`读取配置就绪条件，不调用模型；`POST /production/human-control/llm/chat`校验问题（1–4000字）、page/symbol标签、brief/detailed答复方式及最多6条user/assistant历史（每条≤2000字）。必须具备readiness:write并通过既有研究授权、预算、调用频率检查。mode=mock不调用provider；provider从冻结配置构造，使用实际OpenAI/DeepSeek适配器和SecretManagerResolver。验证ResearchReportOutput及report_type/agent_name/data_snapshot_id，返回来源模型、请求ID和明确context_scope；没有订单执行路径。异常使用固定错误码，连通测试异常也不再回显原始provider异常。状态与聊天成功响应no-store。

预算边界沿用现有调用前检查：不代表真实账单扣费上限或月度成本结算保证。没有自动获得实时价格、图表、账户、新闻或联网搜索材料；当前仅发送问题、有限历史与页面/标的标签。界面直接披露发送内容与可能计费，模型被要求说明证据缺口。没有配置、授权、预算或有效输出时不生成模拟答案。对话仅在当前页面会话内保留，关闭面板不撤销已发送的模型请求。

设置与密钥：修复r116第二个独立if导致AI设置最终被Webhook分支覆盖的回归（改为同一else-if链），浏览器验证两个栏目均能显示正确表单。从两个研究入口直达AI服务。新导入命名为USER_PROVIDER_用户摘要_API_KEY，测试两用户保存不会相互覆盖；已有全局env引用不自动迁移/读取/覆盖。本轮不声称已修复整个通用secret-reference管理面的多租户访问控制。

验证：
- 前端45个模型脚本全部通过，新增research-ai来源/请求/执行标志验证；静态审计594按钮/235表单控件有处理器；最终构建通过，保留现有大包提示。
- 后端LLM/凭据32与human_control10，共42项通过；覆盖无配置不构造provider、调用前限流、结构化身份错配/坏JSON/异常脱敏、历史边界、两用户密钥命名、API权限及输入字段、实际OpenAI/DeepSeek适配器解析保存Key和模型。测试均使用合成数据/替代transport，不代表真实模型响应。
- 独立8002/3003：内存DB、临时凭证目录、实际适配器+无网络fallback的合成transport。OpenAI与DeepSeek配置经UI保存、Key清空、首页及悬浮对话得到带清楚合成标签的回复；最终版本4次DeepSeek请求记录在`output/aicoin-integration-20261027/ai-chat-fixture-r117.json`。测试初版直接装配APIRoute未应用依赖替换，仅GET状态读到本机配置；发现后立即停止，在任何Key提交或模型调用前修正为include_router复制，并验证mock空配置。后续API回归覆盖相同路由装配方式。
- 正式3002：AI设置恢复已有DeepSeek配置，Key字段保持空；聊天仅GET读取模型状态，未发送模型请求。760px面板中消息区417px，页脚可见；正式页宽/scrollWidth均2560。旧隔离标签曾记录9px滚动差异，未将其计作无溢出证明。截图`ai-settings-real-r117.png`、`ai-chat-real-config-r117.png`；合成截图`ai-home-fixture-r117.png`、`ai-chat-fixture-r117.png`均在同一output目录。
- 正式8001已重启（PID93409，session96676，RUNTIME_SCHEDULER_ENABLED=false），3002仍原服务；临时8002/3003已停止并清理TemporaryDirectory凭据。无真实Key更改、真实付费调用、订单、commit/push。

仍待完成：真实模型账户/费用/质量验证；AI分析使用具体行情、图表/资讯证据与完整上下文；其它AI入口统一接入；Nasdaq可用性与多源中文资讯；完整AiCoin模块、API能力和交易功能迁移。整体目标仍进行。


## r118 — 可追溯资讯材料与模型协议兼容（2026-10-30）

在两个研究入口新增默认关闭的“附带已获取资讯”。选择后GET读取当前用户news-feed缓存，最多预览5条；发送时后端重新读取该用户当前缓存，不接收客户端任意正文/URL，不请求新资讯、不读取账户或K线。回复清单是本次实际提供给模型的内容，包含原文、来源、发布时间/来源原始时间、获取时间、缓存年龄、陈旧和最近刷新失败状态。资料并非独立核实的事实，刷新时间也不表示发布时间；不要求模型对每个普通问题强行引用新闻。

后端`research_chat_context.py`对材料限长/安全HTTPS链接过滤，计算内容hash并以user_id=actor.user_id保存DataSnapshot(type=research_chat_news_context)，不保存问题/会话内容。模型data_snapshot_id与这份记录绑定；evidence.news_citation_ids必须对应提供的N1–N5并和文本标记一致，未知引用/错配回复被拒绝，counts_as_external_evidence仍为false。缺少自身缓存直接blocked，不消耗模型调用。历史回传为之前回复加上所属快照及来源说明，防止把旧N1误当作新材料；不能把这一结构校验当成语义事实验证。

`GET /production/human-control/llm/chat/news-context/{id}`要求当前认证用户readiness:read，并同时匹配owner/type/id，no-store；跨用户返回404。通用快照列表隐藏新类型，通用daily-use配置列表/写入排除news_feed:、human_control:命名空间。这是在既有托管认证/tenant机制上的额外边界，不代表已审计或封闭全部既有通用接口/非托管模式权限面；未新增数据库表或运行迁移。

核对官方模型协议还修正了两处兼容问题：
- OpenAI严格模式要求对象closed及所有属性required，原ResearchReportOutput中的任意facts/evidence字典不满足。现通过JSON-object字符串wire表示保留任意嵌套内容，接收后必须解码为对象并由Pydantic校验，canonical facts由服务器恢复，避免重复输出大段上下文；其它结构化schema递归关闭对象。依据：https://developers.openai.com/api/docs/guides/structured-outputs 。这证明请求形状按文档修正，未用真实OpenAI账户验证。
- DeepSeek当前Anthropic示例使用deepseek-flash；新UI/后端默认值更新，已有deepseek-chat配置不自动改名。设置允许同用户同提供商留空Key只更新模型/预算/授权并保留原引用，测试证明凭证文件字节不变；其它用户或切换提供商仍需新Key。结构化工具调用显式thinking.disabled，详细回答仅是答复方式，不冒充thinking模式。依据：https://api-docs.deepseek.com/guides/anthropic_api/ 与 https://api-docs.deepseek.com/guides/thinking_mode/ 。

验证：
- 45前端模型脚本通过（research-ai增加来源URL、快照hash/ID、未知引用和历史归属边界）；静态审计594按钮、236控件有处理器；最终构建通过，保留现有大包提示。
- 单次联合回归137 passed：LLM凭据/上下文、human_control、production_foundation、ai_provider_status、daily_use、data_sources、reports、thesis_delta。覆盖资料所有者、缓存变化后快照保持、陈旧/失败/发布时间区分、错误引用、私有列表排除和认证快照HTTP访问、JSON wire嵌套还原、同用户空Key模型更新不触碰文件。仅有既有Starlette/httpx弃用提示。
- 隔离8002/3003、内存DB/临时凭证、无外网fallback的实际适配器transport：OpenAI保存后留空Key更新模型再携带2条合成资讯，回复引用和原文清单正确；最终DeepSeek默认deepseek-flash通过聊天附带2条合成材料。快照持久化/读取权限由自动化测试验证。调用摘要`ai-news-fixture-r118.json`，截图`ai-news-home-fixture-r118.png`/`ai-news-chat-fixture-r118.png`均明确合成数据。前一张OpenAI合成截图来自首次验收，静态fixture时间后已调整为相对时间，不用它证明真实时效。
- 正式3002只勾选资料预览，显示当前RSS缓存中的真实5条来源；未点模型发送/测试，真实Key及原deepseek-chat配置未修改。截图`ai-news-preview-real-r118.png`。完整市场/图表数据尚未传给模型。

整体目标保持进行：真实模型账户/套餐/费用与回答质量；完整行情/图表身份快照、其它AI入口；中文多源资讯/更多分类；剩余AiCoin行情/API/交易交互与全部功能。静态恢复、目标回归与合成模型输出不证明完整功能或实盘可用。

r118运行收尾：正式8001已采用本轮代码（session87997/PID184，cwd为交易后端，调度器仍关闭）；新上下文接口对不存在ID返回预期404错误码，验证实际数据库查询可执行。3002原服务继续运行。隔离session91857/PID99106与前端71657正常停止，8002/3003无监听；本轮验证tab47已关闭，保留用户原有界面。未向真实模型发送问题或更改真实Key/已保存模型。

## r119 主图原始行情研究上下文（2026-10-30）

保留当前UI，研究对话新增可选30/60/120/240根主图原始OHLCV。在线、CSV、冻结复盘分别标注；演示数据拒绝，回放按周期收盘时间过滤未来K线，缺失CSV成交量不汇总。切换标的/周期或离开普通图表时不沿用旧附件。发送时复制选定材料，回复绑定交易所/交易对/报价币/周期及逐根数据。

后端在模型调用前校验身份、结构、数值和回放截止时间；按用户持久化行情快照，可同时关联资讯快照，模型使用[M1]引用，错配或无材料引用拒绝。通用快照列表排除研究私有材料。结构校验不代表独立核实交易所行情，也不包含指标、画线、其它窗口或账户。

验证：46组前端模型脚本全部通过；78项市场上下文、LLM凭据、human_control相关测试通过（含新增7项引用匹配测试）；静态审计594按钮/238控件通过；构建通过，仍有既有大包提示。实际3002浏览器观察ETH/币安/1h附件60根；切换BTC及5m时旧材料立即清空，新数据到达后显示BTC/币安/5m，切换120根预览正确。截图output/aicoin-integration-20261027/ai-market-preview-real-r119.png。没有向真实模型发送问题或修改Key/已保存模型。本轮尚未进行合成模型浏览器端到端行情回答验收。

8001原服务正常停止后通过原启动脚本重启，保持127.0.0.1及调度器关闭；新market-context缺失ID返回预期404。整体目标保持进行，完整AiCoin功能、其余AI入口和真实交易执行均未据此宣称完成。

## r120 行情AI入口统一接入配置模型（2026-10-30）

审查发现旧aiChart弹窗及AiAnalysisPanel仍展示固定62分、78%可信度、65,553支撑及主力挂单等示例。现移除该固定答案和仅toast的画线/预警/策略完成提示，统一通过根openOverlay路由打开真实研究对话。图表入口及底部AI工作台预填研究问题并预选普通图表K线附件；其它深度/资金流来源将页面快照明确作为未经独立核实的问题文本，仍可预览和编辑。点击入口不会自动请求模型，发送按钮才触发既有认证后端与模型适配器。

保留综合/趋势/主力/风险分类，分类形成研究问题；自定义输入原样带入，新增4000字限制。底部布局调整为研究说明与可用材料两栏，避免遗留评分栏占位。静态审计原先要求旧假完成文案，已随真实流程更改为实际研究入口契约，不能将该审计当模型端到端验证。

证据：46组前端模型脚本通过；589按钮/238控件静态审计通过；最终构建通过（既有大包提示）。正式3002浏览器点击图表AI解读，显示ETH/币安/1h、60根附件和预填问题；底部自定义问题逐字进入研究对话。截图output/aicoin-integration-20261027/ai-chart-entry-real-r120.png；未发送真实模型请求、未修改Key或模型，后端本轮未变更。全量AiCoin功能仍未完成，其它静态示例入口和合成模型浏览器行情回答继续处理。

## r121 行情与资讯组合材料双适配器浏览器验收（2026-10-30）

顶部原固定BTC波动、主力净流入、3篇笔记建议轮播已改为明确研究入口；不再假称后台AI已分析市场或笔记。入口继续打开同一真实配置研究对话。

扩展隔离acceptance服务：捕获模型输入的market_count/symbol/timeframe；合成模型按实际收到材料返回[M1]及资讯[N1]。隔离服务内存数据库、临时合成Key、实际OpenAI/DeepSeek适配器但替换网络transport；/assets返回空列表，让浏览器正常走独立公开行情路径。不能因此宣称整个浏览器测试无外网。最初缺少/assets造成HTTP404，正常行情错误路径不作fallback且附件正确不可用；补齐隔离资产路由后正常公开行情可用，未绕过正式权限处理。

浏览器验收：图表AI解读预填问题，选择120根BTC/币安/1h公开K线及2条合成资讯。OpenAI返回合成回复并渲染[M1]/[N1]、120根范围/统计、资讯和行情各自快照ID；切换隔离配置到DeepSeek-flash后再次发送同样通过，适配器输入摘要记录两次均market_count=120、market_symbol=BTC、market_timeframe=1h、news_count=2、key_matched_fixture=true。证据ai-market-fixture-r121.json、ai-market-openai-fixture-r121.png、ai-market-deepseek-fixture-r121.png位于output/aicoin-integration-20261027。

静态审计589按钮/238控件通过，最终构建通过（保留已有大包提示）。本轮没有改变生产AI配置/Key，没有真实模型付费请求、没有订单。隔离8002(session31361)、3003(session28733)已正常停止、临时tab51关闭。实际3002/8001保留。完整AiCoin目标仍进行，双适配器合成回答只证明材料传递/后端校验/快照/引用展示链路，不证明外部账户额度或真实模型质量。

## r122 45分钟与缺失8小时公开行情聚合（2026-10-30）

现有周期选择器的45分原来在三家公开行情接口均unsupported；OKX/Bitget的8时也缺失。本轮保留入口并补实现：仅在本地无数据/可正常回退公开行情、且公开接口明确unsupported时，对45m读取同平台15m，对缺失8h读取同平台4h。已有币安8h直接使用原生支持。不跨交易所、不混标的、不在401/403后回退。

新增market-candle-aggregation.js，以固定UTC桶聚合首open/最高high/最低low/末close/成交量总和。子周期严格整点对齐/连续；历史桶必须齐全，当前桶必须从桶起点到当前子周期齐全；缺失桶跳过且source显示数量，不插值、不填零。聚合数值溢出拒绝。数据来源明确聚合base/target、30秒轮询及当前是否未收盘，移除native WS provider/interval避免将15m推送混进45m数据。单次240根子周期产生约80根45m或120根8h，实际根数按资料显示，不宣称240根聚合结果。

证据：新增模型脚本检查OHLCV合并、缺失/开头截断桶、当前桶未收盘与缺少最新子周期、未来/错位/重复/溢出拒绝；通过Binance45m与OKX/Bitget8h接口隔离形状测试，校验请求15m/4h和身份/无原生WS。47组前端模型脚本、589按钮238控件审计和最终构建通过，保留大包提示。

实际3002浏览器选择ETH/币安45分后显示真实公开数据，来源为15m按UTC聚合、30秒轮询、末根未收盘、跳过1个不完整区间；AI解读附件显示ETH/USDT/币安45m的60根材料。没有发送模型请求。截图output/aicoin-integration-20261027/market-45m-real-r122.png。验收后恢复ETH/1时，临时tab52关闭；后端无需变更。OKX/Bitget8h尚未做本轮真实浏览器验证；不据此宣称全周期、原版完整或实盘完成。

## r123 OKX/Bitget八小时真实验收及平台入口（2026-10-30）

实际3002浏览器分别选择欧易OKX及Bitget、ETH/USDT、8时：均显示当前平台4h按UTC聚合的8h真实公开OHLCV、30秒轮询、末根未收盘、跳过0个不完整区间。AI解读附件分别显示正确平台及8h，未发送模型请求。证据market-okx-8h-real-r123.png、market-bitget-8h-real-r123.png位于output/aicoin-integration-20261027。

验收暴露图表交易所选择依赖展开自选列表，新增工具栏“图表行情平台”选择框，与原侧栏共用setMarketPlatform，影响当前工作区窗口并保留已有数据身份清空机制。已实际通过新增入口切换Bitget并加载8h。并修正长数据来源挤压布局按钮：来源单行省略，原title仍提供完整文本；按钮不折行。浏览器读取布局栏height42、width2124、scrollWidth2124，按钮未被长来源撑高。最终截图market-bitget-8h-layout-r123.png。

589按钮239控件静态审计及最终构建通过（既有大包提示）。本轮仅界面及验收，无后端改动，无真实模型调用/订单/凭据改动；验收后恢复币安/ETH/1时，临时tab53关闭。完整AiCoin目标仍进行，不能由这两个周期验收推定全部模块或实盘就绪。

## r124 已保存交易所连接名称管理（2026-10-30）

连接列表增加修改名称/保存/取消表单。新增PATCH /exchange-connections/{id}，只接受label且最大1024字节请求；名称1–80字，拒绝控制字符，按当前用户归属和既有secrets:write权限校验，响应no-store。服务只修改DataSourceConnection.name，不读取或重写凭证、不联系交易所、不改变验证时间/权限/启停状态。禁用记录允许整理名称但不会恢复连接。前端校验返回id/exchange/label，busy期间阻止重复操作。

9项交易所连接回归通过：原生命周期以及新增重命名、文件字节不变、验证状态不变、无网络验证、其他用户404/无权限403、额外密钥字段及非法名称422、禁用后不重新启用。592按钮240控件静态审计和构建通过（已有大包提示）。隔离8002内存DB/临时合成凭据、真实交易所探针但签名transport合成，3003浏览器完成改名“研究账户·隔离验收”、刷新持久保留、随后重新验证和合成余额读取。截图output/aicoin-integration-20261027/exchange-rename-fixture-r124.png；该余额不是实际账户资产。

原8001 session70947正常停止，原启动脚本启动新session27575，仍为127.0.0.1/8001且调度器关闭；新PATCH对nil UUID返回connection_not_found404用于路由加载确认，没有改动真实连接。测试8002 session90885和3003 session95661正常停止，tab54关闭。没有真实凭据修改、外部账户操作或订单；完整AiCoin功能继续。

## r125–r126 中文快讯、重点资讯弹窗及刷新竞态（2026-10-30）

用户明确要求资讯中文，并检查参考项目的重点资讯弹窗。已在AiCoin readable/9571/deobfuscated.js的renderNewsflash（约2171–2222行）确认独立消息卡，来源/时间/标题/可选正文、newsflash_pro背景；约1328/1391/1482行有自动收起/关闭行为，isProFlashNotice约1414行区分特色消息。这是恢复代码证据，不等同于取得原版推送服务。

新增PANews官方中文快讯RSS：https://www.panewslab.com/rss.xml?lang=zh&type=NEWS 。该地址来自官方https://www.panewslab.com/zh/rss页面的RSS alternate标签；实际HTTP200，解析100条中文原文标题/摘要。后端固定HTTPS来源白名单新增该地址，不请求文章URL、不跟随重定向，继续2MB/XML实体限制。新默认来源panews/zh，保留其它来源可选及已有Key。当前实际后端用户设置已按用户指令切到PANews中文、60秒自动更新，NewsAPI Key/模型Key均未改。初次10秒超时不够，独立同参数HTTPS探测约15.89秒成功，将PANews超时改20秒；正式服务最终ready/100条/last_error无。来源网络仍可能失败，保留错误状态与上次缓存。

新增应用内重点资讯弹窗（news-notices.jsx），全应用打开时按后端自动刷新配置更新、后台隐藏暂停；标题/摘要按可配置关键词匹配，明确标注本地规则，非媒体评级或AI判断。默认关键词涵盖被盗/攻击/提现暂停/监管/利率等。首次最多弹一条、仅30分钟内及非未来消息自动提醒，后续最多3条进队列、总队列最多5条，单条20秒自动收起，可保留/关闭/查看原文/打开设置。右下“重点资讯”入口可随时查看当前缓存命中规则的最新一条。原“设置→快讯弹窗”的空转开关已替换为真实设置，并在资讯设置中提供同一组件；本机保存自动开关和关键词，不启用系统通知，不虚构声效/原版媒体重点等级。

同时修复r125发现的资讯配置竞态：设置保存时替换正在进行的旧请求，取消并以generation丢弃迟到响应，先清除旧来源材料；普通重复刷新仍合并。提取news-feed-reader.js以可控延迟测试证明旧响应/旧失败不能覆盖新来源及加载状态，卸载后不更新。

验证：49前端模型脚本通过（新增reader竞态及notice重复/过期/未来/禁用边界）；90项后端资讯/模型凭据/行情上下文相关测试通过，随后20秒超时修改重跑22项资讯测试通过；600按钮242控件审计及构建通过，仍有既有大包提示。实际3002显示PANews中文快讯100条，手动重点入口成功展示真实来源中文卡片、保留按钮正常；“提醒设置”进入真正的快讯弹窗页并保存成功。截图chinese-news-popup-r126.png、chinese-news-popup-settings-r126.png位于output/aicoin-integration-20261027。自动新消息及去重规则由模型测试验证，本轮未等待真实下一条重点新闻到达。未发送模型/订单。

运行：原8001 session27575正常停止后启动33652，超时修正后正常停止33652并启动最终session75258，仍使用原启动脚本/127.0.0.1/调度器关闭。旧参考BlockBeats接口超时且官方旧仓库标明停用，未接不可用旧API；PANews官方源已实际可用。整体完整AiCoin迁移仍进行，当前重点采用透明本地规则，不冒充原版会员推送。

## r127 多媒体中文聚合与真正的快讯/要闻分流（2026-10-30）

用户指出单源不符合AiCoin多来源特点，且已有快讯/要闻分类不能共用同一消息列表。恢复代码main/deobfuscated.js约12990–13048确认快讯分类v3/newsflash/tab、列表/未读列表以及only_important独立参数。现纠正此前单源及混用问题，不宣称获得原版私有推送服务或全部媒体授权。

新增chinese_news_sources.py官方目录：PANews RSS type=NEWS为快讯、type=NORMAL为文章（来自官方RSS配置页面真实选项；ARTICLE不是有效类型）；Odaily官方https://github.com/ODAILY/RSS列出/rss/newsflash与/rss/post；律动官方https://github.com/BlockBeatsOfficial/RSS-v2列出/v2/rss/newsflash与/v2/rss/article。固定HTTPS白名单，保留不重定向/2MB/XML实体限制；六路并行抓取、独立状态/成功时间/错误/文章缓存。合并按URL去重、保留媒体来源，同事件多家报道不当作独立核实；快讯与文章各最多100条再按发布时间排序。单路失败保留自己旧缓存，不借其它路成功时间冒充新鲜，返回source_status及每篇source_fetched_at/source_stale/source_error，AI资料也保留这些状态。

设置新增中文多源模式及三家媒体勾选，当前用户已切换、选择三家、60秒更新，不更改Key。前端快讯只读取flash、要闻只读取article，细频道仍有明确披露的关键词筛选；来源筛选在类型内生效，跨页重置筛选。右栏快讯/要闻及重点弹窗同步按kind分流，重点仍为透明本地关键词规则。

真实验收：PANews快讯/文章各100原始条，Odaily快讯/文章各10条；合并截取后各类型100条（PANews90/Odaily10）。律动两路超时，status=error/count0，无成功时间，页面明确显示，没有伪装接通。快讯页面可见两家即时报道；筛选Odaily显示10/100；要闻页面包含独立文章/深度标题，两家来源并列且不是快讯复用。设置三家独立勾选已验证。证据multisource-flash-r127.png、multisource-articles-r127.png、multisource-settings-r127.png和multisource-status-r127.json在output/aicoin-integration-20261027。

验证：96项后端资讯/LLM凭据/行情上下文相关测试通过（新增分流、部分失败保留旧缓存、全部失败陈旧标记、固定目录参数、AI材料失效来源状态）；49前端模型脚本通过；602按钮243控件静态审计及最终构建通过，保留既有大包提示。原8001 session75258正常停止启动59838，最终排序修正后正常停止59838启动41860，仍原脚本/回环8001/调度器关闭，GET latest确认200条及6路状态。未模型付费调用、未订单、未更改Key。完整AiCoin媒体数量/分类/会员推送及整体目标仍未完成，律动可用性继续受当前网络限制。
