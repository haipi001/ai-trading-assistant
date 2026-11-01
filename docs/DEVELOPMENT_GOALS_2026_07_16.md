# AI Trading OS 后续开发目标

日期：2026-07-16
当前基线：本地工程成熟、后端 395 项测试通过、前端类型检查和生产构建通过；产品仍处于本地自用 / 私有 Beta 候选阶段，真实交易默认禁用。

## 总目标

把 AI Trading OS 从“功能广泛的本地工程 Alpha”推进为：

1. 创始人每天愿意使用的个人投资工作台；
2. 能稳定接入真实只读资产与研究数据的可信终端；
3. AI 输出可评测、可追溯、不可越权的决策辅助系统；
4. 可供小规模私有 Beta 用户安全使用的产品；
5. 在独立授权后，才进入券商 Sandbox 和小额受控实盘验证。

## 统一完成定义

每个开发目标必须同时满足：

- 用户能够在正式界面完成，不依赖开发者手工改数据库或环境文件；
- 后端接口、前端状态、审计记录和错误恢复形成闭环；
- 缺数据、数据过期、外部服务失败时 fail closed；
- 新能力有自动化测试和用户路径 E2E；
- 不把模拟数据、准备度报告或人工填写的元数据计作真实外部证据；
- 不扩大交易权限；实时交易、钱包签名、提现和自动审批继续禁用。

---

## G1：完成本地每日投资闭环

优先级：P0
目标：让用户每天只沿着一条主线完成“开盘检查 → 变化识别 → Thesis 复核 → 风险审查 → 计划 → 收盘复盘”。

### 交付物

- 清理 Plan、Risk、Research 和 Copilot 中剩余的静态叙事卡，全部接入真实数据或明确显示暂无数据。
- Today 工作台统一待办来源，支持完成、延期、忽略、分派、批量处理与状态恢复。
- 自动生成 Thesis checkpoint、数据过期提醒、风险变化提醒和待复盘任务。
- 完成每日开盘、每日收盘和月度复盘的历史记录与可回看时间线。
- 统一空状态、错误状态、加载状态和下一步操作文案。
- 完成桌面端主路径和关键移动端适配。

### 验收标准

- 新数据库从首次启动到完成一轮纸面交易复盘，用户无需进入 Admin/Dev 页面。
- 核心按钮全部调用真实能力，不存在假按钮或伪造结论。
- 本地每日闭环 E2E 连续运行 20 次无随机失败。
- 用户可在 10 分钟内完成一次每日检查。

### 当前进度（2026-07-16）

- 已完成右侧 Copilot 真实数据接入与失败关闭。
- 已完成 Today Queue 批量完成、延期、忽略、分派及每日历史时间线。
- 已完成数据过期、组合风险的自动队列提醒。
- 已完成 Thesis checkpoint 复核任务与待交易复盘任务的自动检测、持久化、去重、条件消失后自动关闭与 Today Queue 聚合。系统只生成人工复核任务，不自动写入 Thesis 结论。
- 已清除 Research 工作台的固定 NVDA/BTC 报告、示例 Playbook、示例投资纪律和伪 AI 发现；报告、策略、宪法和证据缺口现全部由真实后端数据生成。
- Research 核心数据任一读取失败时现会 fail closed，清空旧结论并提供重试；未接入更新 API 的 Thesis 抽屉改为明确只读，移除伪保存、伪 AI 补充和伪提醒按钮。
- 验证：Research 桌面/移动专项 2 passed；核心桌面+移动 E2E 13 passed、1 skipped（移动端按设计不显示桌面 Copilot）；前端 typecheck 与 production build 通过。
- Plan 工作台现要求订单草稿及每条决策依据完整读取；任一失败会清空旧状态、关闭抽屉并提供重试，不再误报为“没有计划”。
- Risk 工作台现要求组合、资产、Thesis、计划、数据新鲜度和钱包风险完整读取；任一失败会 fail closed，不再把失败显示成零风险。时序分析失败时保留上次结果并显式告警。
- API 503 失败注入专项桌面+移动 4 passed；核心桌面+移动 E2E 17 passed、1 skipped；前端 typecheck 与 production build 通过。
- 已恢复新版 Research / Plan 总览中被隐藏的正式操作入口：用户可从 Research 进入 Thesis 编辑与人工计划，从 Plan 进入五道闸门、审批与纸面成交，不依赖旧 Admin/Dev 页面。
- 已新增独立全新临时数据库验收脚本和 UI-only E2E。验证链路：首次启动模拟初始化 → Thesis 生成计划 → 风险预检 → 五道闸门 → 审批草稿 → 人工批准 → 纸面入账 → 完成复盘；最新结果 1 passed（6.5s），并确认未调用实盘执行接口。
- 首次 20 次连跑在第 2 轮真实暴露 `risk_budget_missing`：模拟持仓含 ETF，但 demo/default 风险预算未显式覆盖 ETF，列表顺序变化时会随机阻断。现已补齐 ETF 预算并增加后端回归断言。
- 修复后的完整冷启动闭环连续运行 20 次全部通过（每轮独立新建数据库、迁移并启动前后端，单轮 5.0–7.2s）。
- Today 首页已移除固定 MSFT/USDT 持仓、固定组合曲线、伪活动记录及 API 失败时的模拟回退；无真实数据时显示明确空状态。更新后的新库闭环仍通过。
- 最新回归：后端全量 376 passed；前端 typecheck 与 production build 通过。G1 剩余 10 分钟人工用户验收，以及对其他非主路径静态回退和移动端关键路径的继续审计。
- 新库完整闭环现可切换 Playwright 项目，并已在 iPhone 13 移动视口完成首次启动、计划、闸门、审批、纸面成交和复盘。首次移动验收暴露复盘抽屉底部按钮在动态视口中的点击问题；抽屉现使用 `100dvh`、固定 footer 和 safe-area 底部留白。
- 移动端完整闭环 1 passed（7.0s），并对 Today / Research / Plan / Review 四个关键页面验证无整页横向溢出；修复后桌面闭环 1 passed（8.5s），前端 typecheck 通过。
- G1 当前只剩必须由真实使用者完成的 10 分钟人工验收，以及持续性的非主路径回退审计；自动化主路径和关键移动端验收均已落地。

---

## G2：建立真实只读数据主链

优先级：P0
目标：真实资产、行情、账本和研究数据可持续进入系统，并能说明来源、时效、质量和使用边界。

### 交付物

- 完成 Binance Spot 真实只读验证：权限证明、禁止提现证明、账户快照、质量报告和脱敏证据包。
- 实现 IBKR、Futu 至少一个真实只读账户适配器；另一个保持 typed skeleton 也可，但不得显示为已接通。
- 实现自动刷新调度、失败重试、限流、退避、断线恢复和用户可见的同步历史。
- 将账本对账、现金、税批次和公司行动差异接入可操作修复工作台；自动修复只生成建议，不直接改外部账户。
- 把 Data Catalog 的 raw → reviewed → trusted 晋级真正接入下游研究、Thesis 和风险门禁。
- 扩展 EVM 只读到多链余额、ERC-20 allowance、价格附着和协议暴露；继续禁止签名和交易构造。

### 验收标准

- 至少一个 CEX 和一个股票账户来源完成真实只读同步。
- 每次同步生成 Snapshot、Quality Report、Catalog lineage、Ledger reconciliation 和 Audit Log。
- 过期、缺失或对账失败的数据不能晋级 trusted，也不能被下游当成可靠决策数据。
- 真实凭证仅以安全引用存在，日志、数据库和 API 响应不出现原始密钥。

### 当前进度（2026-07-16）

- 已完成 Binance Spot 私有只读链路的安全加固：提供方只要返回 `canTrade=true` 或 `canWithdraw=true`，同步立即 fail closed，不保存账户快照。
- 私有验收现在强制要求脱敏权限截图引用、提现关闭证明引用和私有运行环境标记；仅“接口调用成功”不再能标记为真实只读验证通过。
- 每次账户同步现统一生成并返回 Snapshot、Quality Report、Catalog lineage、Ledger sync、reconciliation 和两段 Audit Log；普通同步接口与阶段验收接口不再存在证据链分叉。
- 质量门禁已降低无法附着市值的持仓快照评分；未定价资产不能以高完整度分数误入后续可信链路。
- 已增加 Binance 安全权限拒绝、缺失人工证明阻断、完整私有成功链和普通同步完整证据链回归测试；相关专项 38 passed。
- 已把账户只读刷新接入现有 runtime scheduler：支持 5–1440 分钟间隔、30 秒最小调用间隔、30 秒起步的指数退避、1800 秒封顶和断线恢复；不通过阻塞 sleep 占用调度线程。
- 自动与手动同步现在都有用户可见的脱敏历史；正式数据源页面可启用/暂停每 15 分钟刷新、查看成功/失败关闭/等待重试状态，不依赖 Admin/Dev。
- Provider 异常不再把原始异常字符串写入数据库或 API；即使异常包含带 `signature` 的 URL，也只持久化稳定错误码。桌面和移动自动刷新路径 E2E 各 1 passed。
- IBKR 已从 placeholder 升级为 Client Portal Gateway 认证只读适配器，按官方调用顺序只使用 `GET /portfolio/accounts`、分页 positions 和 ledger；同一次同步复用账户探测响应，避免重复触发官方 5 秒限流。远程 Gateway 禁止使用本机自签证书豁免。
- IBKR 私有验收入口强制要求 Gateway 会话证明、只读边界证明和私有环境标记；缺少证明时不触网。通过后生成与 Binance 一致的 Snapshot、Quality、Catalog、Ledger、Reconciliation、Audit 和脱敏 evidence artifact。
- 显式 `sample_payload` 仍可用于旧账本映射演练，但 Snapshot/Catalog 永久标记 `data_origin=sample_payload` 和 `real_external_evidence=false`，不得冒充真实 IBKR 证据。
- 正式数据源页面现在自动配置本机 `127.0.0.1:5000` Gateway 元数据，并将 IBKR 显示为认证只读适配器和“同步真实只读账户”；桌面/移动专项 E2E 2 passed。
- Research Report 与 Research Committee 已接入精确快照级 trusted 硬门禁：引用快照必须存在、已入 Catalog、质量 VALID、未过期、明确晋级 trusted 且当前证据仍符合 trusted；否则结构化 409 fail closed 并写阻断审计。
- 行情与 K 线导入响应现返回对应 Catalog Entry，使正式流程能够完成 raw → reviewed → trusted 两阶段晋级后再进入 Research；低质量快照会在 AI 生成前直接阻断。
- AI 评测模拟快照使用独立 `research_eval` scope，永久标记 `real_external_evidence=false`，不能借 trusted 状态进入普通 Research。
- Thesis capture 与 monitor 也已接入精确快照 trusted 门禁；InvestmentThesis 和 ThesisCheckpoint 持久化 `data_snapshot_id`，不可信时在 AI 调用前结构化阻断且不创建半成品。
- 正式持仓页创建 Thesis 前会选择 trusted 行情快照；没有可用快照时引导用户先到数据源完成导入与两阶段晋级。
- 新增 Thesis 快照追溯迁移，并在全新 SQLite 数据库完整执行全部 19 个迁移成功。
- 组合 Risk 改为严格两阶段：先从 Yahoo 只读接口生成包含完整 K 线行的 raw Snapshot/Quality/Catalog，人工晋级 trusted 后才运行计算；风险计算从精确快照反序列化，不再从可能混入未复核更新的全局 Candle 表取数。
- Risk 正式界面会优先选择 `portfolio_risk` scope 的 trusted K 线；若没有，则先生成 raw 证据并明确提示用户到数据源复核晋级。风险结果自身也生成 Snapshot、Quality、Catalog lineage，记录全部输入快照 ID。
- EVM 只读适配器现覆盖 Ethereum、Base、Arbitrum、Optimism 和 Polygon，并对 `eth_chainId`、`eth_getBalance`、`eth_call` 采用显式方法白名单；签名、交易构造和发送方法不可调用。
- 自定义 RPC 端点禁止携带用户名、密码、查询参数或 fragment，并强制按登记链校验 chain ID，避免跨链误读及凭证进入日志。
- 真实 RPC 刷新现支持原生币、ERC-20 余额、allowance、公开价格附着和协议仓位；每轮均生成 Snapshot、Quality、Catalog lineage 与脱敏 Audit Log。未定价记录会降低质量状态，不能伪装成完整证据。
- 正式 Web3 页面可选择五条支持链，并按钱包配置 ERC-20 合约、spender 和协议仓位；刷新错误直接可见。多链汇总提供余额、授权风险和协议暴露，继续明确 `signing_available=false`、`transaction_building=false`、`execution_available=false`。
- 最新验证：EVM 专项 18 passed；后端全量 392 passed；前端 typecheck、production build 通过。RPC 合约测试使用模拟节点响应，不计作真实外部链上现场证据。
- 尚未完成：真实 Binance 和 IBKR 私有账户现场验证及脱敏证据归档，以及真实公共 RPC 的现场证据留存。因此 G2 仍为进行中，不能计作完成。

---

## G3：把 AI 质量从“结构校验”推进到“可量化评测”

优先级：P0
目标：能够回答某个模型、Prompt 和任务类型是否可靠，而不是只证明接口能调用。

### 交付物

- 决定 evidence 字段策略：必要事实必须引用输入快照；无证据时拒绝生成确定性结论。
- 完成首批真实模型结果人工标注，记录 hallucination、citation completeness、direct advice 和 blocked action。
- 扩展评测集到至少 100 个案例，覆盖研究、Thesis 捕获、Thesis 监控、风险解释和复盘。
- 增加矛盾数据、过期数据、提示注入、多语言、长文本、Unicode/空格绕过等对抗样本。
- 建立 Prompt、模型、Schema、输入快照和评测结果的版本关联。
- 提供 OpenAI/DeepSeek 等 Provider 的质量、延迟、失败率和成本比较。

### 验收标准

- 至少 100 个案例、2 个模型、3 类任务完成可重复评测。
- hallucination rate 只来自人工标签，结构通过率不得冒充事实正确率。
- 红队执行泄漏为 0；任一高风险泄漏自动阻止该版本进入可用模型清单。
- 所有 AI 结论都可追溯到输入数据快照和 Prompt/模型版本。

### 当前进度（2026-07-17）

- 基准数据集已从 15 条扩展到确定性生成的 100 条，均明确标为 synthetic fixture，不冒充真实模型或真实外部证据。
- 覆盖研究、Thesis 捕获、Thesis 监控、风险解释和交易复盘五个评测域；包含矛盾事实、过期数据、提示注入、中英混合、长文本、Unicode/空格及缺失证据等对抗类别。
- 正式 Research 工作台可准备 100 条基准，并选择 OpenAI/DeepSeek 以 5/10/25/100 条分批运行；页面明确外部调用可能产生费用且不会执行交易。
- 每个成功结果记录模型版本、Prompt 名称与 SHA-256、Schema 名称与 SHA-256、输入快照 ID、输入事实 SHA-256、延迟和成本状态。Provider 未返回用量时成本保持 null，不推算或伪造。
- Provider 调用失败会生成脱敏失败记录并计入失败率，原始异常文本不会进入评测历史。
- 人工标注强制记录 hallucination、citation completeness、direct advice 和 blocked action；hallucination rate 与引用完整度只基于人工标签，未标注时保持 null。
- Research Prompt 要求事实结论引用精确输入快照；评测同时检查报告快照字段、结构化 evidence 和 evidence 中的精确 snapshot ID。
- 任一模型结果出现高风险执行泄漏会创建持久化 release block；同一模型版本后续评测调用 fail closed，不再属于可用候选。
- 人工标注卡现在同时展示输入事实和模型输出；Provider 调用失败因不存在可审核语义输出，不会进入待人工标注列表。
- 新增全新临时数据库用户路径 E2E：首次初始化 → 进入正式 Research → 准备 100 条基准 → 选择 DeepSeek/批量大小 → 运行 → 展开输入与输出 → 提交四维人工标签 → 查看仅人工指标。桌面 1 passed（4.4s），iPhone 13 移动视口 1 passed（4.0s），并验证无整页横向溢出。
- 最新验证：AI eval/安全专项 23 passed；后端全量 394 passed；前端 typecheck、production build 通过；G3 正式界面桌面/移动 E2E 通过。
- 尚未完成：使用真实配置的 OpenAI 与 DeepSeek 跑满至少 3 类任务并完成人工语义标注；当前没有真实模型结果，不能宣称质量、幻觉率、真实成本或 G3 验收完成。

---

## G4：完善研究、策略与风险深度

优先级：P1
目标：从“模块存在”推进为能支持真实投资复核的研究与风险工具。

### 交付物

- 将 SEC、新闻、宏观、链上和 Catalyst 数据统一接入 Thesis Delta。
- 增加事件去重、实体关联、时间线、来源可信度和冲突事实展示。
- 完成组合因子、行业、主题、币种、稳定币、协议和交易所暴露分析。
- 增加情景压力测试、回撤预算、相关性变化和集中度漂移提醒。
- 回测支持多资产组合、基准比较、手续费、滑点、流动性约束和 walk-forward 报告。
- Signal Quality 建立零技能基线和样本外评估，禁止只展示命中率。

### 验收标准

- Thesis 页面可明确回答“发生了什么变化、证据是什么、是否越过容忍区间”。
- 风险结果展示方法、样本区间、数据缺口和限制。
- 回测与信号报告区分样本内/样本外，不承诺收益，不可直接创建执行。

### 当前进度（2026-07-17）

- Thesis Delta 已消费本地 K 线、SEC、新闻、FRED 宏观、Catalyst Calendar，并对加密资产补充链上指标；未同步或早于 checkpoint 基线的 feed 继续明确显示 missing/stale。
- 新增统一证据时间线，将新闻、SEC 申报、宏观最新值、催化剂和链上指标按发生时间排序展示。
- 新增来源可信度策略：SEC/FRED 标记为 `primary_official`；公共新闻、聚合日历和公共链上数据标记为 `public_secondary` 且要求人工复核。该分数只表示来源类别，不冒充事实正确率。
- 新增结构化冲突检测：同一实体、字段、时点出现不同值时，保留全部来源、快照和取值，标记 `human_review_required`、`deterministic_conclusion_allowed=false`，并在正式 Thesis Delta 页面突出显示。
- SEC fundamentals 现保留最近观测值，可发现同期间重报/修订差异；宏观和链上时间序列也会检测同时间点冲突值。
- 冲突只生成复核提示和审计记录，不自动更新 Thesis、checkpoint、计划或订单。
- 最新验证：Thesis Delta/Research Feed 专项 11 passed；后端全量 395 passed；前端 typecheck、production build 通过。
- 新增全新临时数据库正式界面 E2E：首次初始化 → Research → 选择 Thesis → 生成 Delta → 查看来源等级、冲突证据与统一时间线；桌面 1 passed（5.0s），iPhone 13 移动视口 1 passed（3.8s），并验证无整页横向溢出和只读边界文案。
- 资产主数据新增可追溯分类：行业、细分行业、主题和因子标签必须来自人工复核，或引用精确的 `asset_classification` trusted Snapshot；系统不根据股票代码静默猜测分类。外部分类缺少可信快照时结构化 fail closed，并写入审计。
- 组合风险新增资产类型、币种、市场、交易场所、账户、行业、细分行业、主题和因子标签暴露；主题与因子明确允许重叠，不把相加超过 100% 误报为资产权重。
- 风险结果展示分类覆盖率、分类来源与快照 ID；同时给出单资产相对当前组合的经验 beta/波动率代理，并明确当前尚无正式命名因子模型，避免把描述性代理冒充 Fama-French 等因子暴露。
- CEX、协议和稳定币外部暴露单独聚合并明确不计入当前证券组合总市值，防止跨账户重复计算。
- 新增资产分类迁移 `20260717_0020`，全新 SQLite 数据库完整执行 20 个迁移成功；后端分类/风险专项 7 passed，后端全量 395 passed，前端 typecheck 与 production build 通过。
- 新增全新临时数据库正式界面 E2E：首次初始化 → Risk → 多维暴露 → 查看行业/币种/主题 → 人工保存资产分类并验证审计边界；桌面 1 passed（4.8s），iPhone 13 移动视口 1 passed（4.7s），并验证无整页横向溢出。
- 连续可信风险结果之间新增三类变化证据：持仓集中度漂移、重大持仓相关性上升、回撤预算消耗上升。第一份结果只建立基线，不从单次快照伪造“变化”。
- 变化阈值在正式 Risk 页面明确展示：持仓权重增加至少 5 个百分点且当前达到 20%；相关性增加至少 0.15 且当前达到 0.70；回撤预算增加至少 10 个百分点且当前达到 80%。每条结果保留前次 artifact ID、前值、当前值、变化量、方法和限制。
- 越阈值只创建 Today Queue 人工复核提醒，不改仓、不建单、不执行；同一活动条件去重更新，用户已处理/忽略的活动条件不会被每次分析重新刷屏。后续可信分析确认条件消失时自动关闭提醒，并记录自动解决时间、依据 artifact 和审计日志。
- 风险变化正式界面已并入多维暴露 E2E：桌面 1 passed（4.9s），iPhone 13 移动视口 1 passed（4.5s），并验证基线/阈值/只提醒不执行文案和无整页横向溢出。
- 最新验证：风险变化与时序风险专项 5 passed；后端全量 397 passed；前端 typecheck、production build 通过。
- 回测 walk-forward 已从“重复滚动整段回测”改为严格按时间先训练段、后样本外段；每折同时保留 in-sample 与 out-of-sample，汇总收益/回撤/正收益比例只读取样本外结果。用户给定参数固定，训练指标仅作描述，不允许使用测试结果反向选参。
- 样本外折叠现与主回测一致计入手续费和滑点；正式策略页可显式填写训练长度、样本外长度、步长、手续费和滑点，并明确标识 `OOS folds`。回测专项 12 passed，前端 typecheck 通过。
- 成交量参与率已成为真实模拟约束：单资产、多资产、基准及 OOS 折叠的请求数量超过当日成交量上限时只做部分模拟成交，并记录 requested/filled quantity、受限次数；未配置时保持旧模型并明确为无参与率约束，正式 UI 默认要求用户填写。
- 静态权重多资产组合新增严格 walk-forward：每个资产按时间训练/OOS 分割，组合 OOS 曲线由各权重 sleeve 合成，汇总指标只来自样本外；跨交易日历按行对齐的限制显式展示。周期再平衡组合尚无等价 OOS 引擎时结构化 blocked，不以静态结果冒充。
- 正式 Research「策略规则」提供回测实验室入口；用户可编辑至少两个不重复资产及权重、手续费、滑点、最大成交量参与率、训练/OOS 长度和步长。非法资产/权重在页面直接提示，不再静默降级成单资产。
- 最新验证：回测专项 14 passed；后端全量 399 passed；前端 typecheck、production build 通过；全新数据库正式路径桌面 1 passed（5.2s）、iPhone 13 1 passed（5.1s），并验证提交参数和无整页横向溢出。
- Signal Quality 改为严格 point-in-time OOS：使用信号生成时记录的同 timeframe 输入 `as_of` candle（旧信号回退到创建时点之前最近同周期 candle），结果只读取之后严格发生的 N 根 candle；不同周期数据不再混用，缺失结果按原因跳过而不填补。
- 零技能基线保留同方向配比下的期望命中率，但正向点估计不再等同质量结论。系统计算 Wilson 95% 命中率置信区间，默认至少 30 个已评估信号，且置信区间下界必须高于零技能基线，才允许 `quality_claim_allowed=true`。
- 新增方向调整后收益：bullish 使用正向收益、bearish 使用反向收益，避免原始平均涨跌把正确空头信号误算成负贡献；每类信号也展示样本门槛与区间。
- 正式信号页明确显示“样本不足 / 证据不支持 / 统计证据支持”，并写明点估计不是质量结论、所有结果均为生成时点之后的 OOS 观察且不能绕过闸门。
- 最新验证：Signal Engine 专项 14 passed；后端全量 401 passed；前端 typecheck、production build 通过；全新数据库正式路径桌面 1 passed（4.7s）、iPhone 13 1 passed（4.2s），验证 100% 小样本命中仍不可形成质量结论和无整页横向溢出。
- 尚未完成：稳定币/协议/交易所的真实外部账户现场数据验收。因此 G4 的本地代码与自动化范围已完成，但真实外部暴露证据尚未满足，G4 全量验收仍不能宣称完成。

---

## G5：完成生产基础设施

优先级：P1
目标：让系统具备承载私有 Beta 的认证、隔离、监控、备份和恢复能力。

### 交付物

- 接入真实 OIDC 租户，完成短会话、撤销、RBAC 和用户级数据隔离验证。
- 接入至少一个云 Secret Manager，并完成真实读取、轮换和失效测试。
- 建立托管 PostgreSQL、迁移流程、加密备份、恢复演练和数据保留策略。
- 接入错误监控、指标、日志、告警、SLO 和状态页。
- 建立 staging/production 环境、CI/CD、回滚和数据库迁移保护。
- 完成依赖漏洞、权限、日志脱敏和 API 滥用防护检查。

### 验收标准

- 在隔离环境完成一次部署、备份、灾难恢复和回滚演练。
- 跨用户越权测试全部失败关闭。
- 关键服务异常能被监控发现并通知负责人。
- 不再以本地 SQLite 演练替代生产 PostgreSQL 恢复证据。

### 当前进度（2026-07-17）

- 已完成一项多租户失败关闭修复：托管认证模式下，未显式传 `user_id` 的旧接口会由中间件注入当前会话 subject，不再回落到共享的 `default-user`。
- 普通用户显式请求其他 `user_id` 会返回 403；owner/admin 仍可显式执行授权的跨用户查询；客户端伪造的用户和角色 header 会被管理会话身份覆盖。
- 新增 4 项中间件回归测试，认证/生产基础专项 18 passed；后端全量 405 passed。
- API 滥用防护已从“设置页预检”升级为可启用的 Redis 中间件：OIDC 登录按客户端、无效会话按客户端、已认证 API 按 OIDC subject 分别限流；身份先哈希再形成 Redis key。超限返回 429 + `Retry-After`，限流存储故障返回 503 并 fail closed。
- production/staging 准备度检查现会在未同时启用 managed auth 和 API rate limit 时直接 block；本地默认仍不启用，避免把未经验证的环境误报为生产安全。
- Redis 原子计数已用本机真实 Redis 验证为 1→2→3，测试 key 随后删除。限流/安全/生产基础专项 34 passed，后端全量 411 passed，前端 typecheck 和 production build 通过。
- 托管认证现将 JSON body 中声明的 `user_id` 与会话绑定：普通用户伪造他人 ID 返回 403，声明 `user_id` 字段但未传值的 Schema 在 Pydantic 验证前注入会话 subject；未声明该字段的 `extra=forbid` Schema 不会被改写。
- 新增 ORM 会话级租户防线：当 managed-auth tenant context 存在时，所有已含 `user_id` 的模型在 `SELECT`/`Session.get` 时自动过滤，跨租户 insert/update/delete 在 flush 前拒绝并向 API 返回 403。专项 16 passed，后端全量 419 passed。
- 0021 tenant ownership 迁移已为 Account、DataSourceConnection、DataSnapshot、OrderIntent、AuditLog 等 34 张早期单用户表增加非空 `user_id` 和索引。历史数据使用部署前明确设定的 `LEGACY_TENANT_USER_ID` 回填；空值或超长 owner 会阻止迁移。
- 新建旧模型资源在 managed tenant context 下自动归属当前 subject；资源 ID 查询也受 ORM tenant filter 约束。自动覆盖测试确保只有 Asset、Candle、Chain、Quote 四类不含用户私有数据的参考/市场数据模型保持全局共享。
- 0021 已在全新 SQLite 空库从首版迁移到 head，并在 0020 库预置 Account/DataSnapshot 历史行后验证自定义 OIDC owner 回填；同时验证 downgrade 回 0020。租户专项 6 passed，后端全量 422 passed。
- 新增真实 CI 发布门禁：`migration_guard.sh` 强制单 Alembic head、全新库升级、`alembic check` ORM/迁移零漂移、`downgrade -1` 及重新升级；该门禁首次运行发现了真实外键/唯一索引漂移，已用 0022 修复。
- CI 安全 job 现包含 pip-audit、npm audit（显式使用支持 audit API 的官方 registry）、Bandit 高严重度/高置信度 SAST 和高置信凭证扫描；任一项失败都会使 CI 失败。
- 本地执行证据：Python 已知漏洞 0；Bandit high/high 0；Secret scan 0；前端审计首次发现 Next 内嵌 PostCSS 8.4.31 漏洞链，已通过 package override 收敛到 8.5.19，`npm audit --audit-level=moderate` 现为 0，typecheck/build 通过。
- 新增中央结构化安全请求日志：仅记录服务端生成 request ID、method、路由模板、status、duration 和异常类型；不记录 raw path、query、Header、body 或异常消息，并关闭 Uvicorn 默认 access log。production/staging 禁用该能力时准备度 block。
- 新增基于 Redis 分钟桶的真实 HTTP 指标：统计请求量、5xx、可用率和平均延迟，保留 48 小时；无样本或样本不足会明确显示 `insufficient_data`，不会伪装成 100% 达标。Prometheus 导出不携带用户或高基数路由维度，并受运维 RBAC 保护。
- `/health/ready` 会在必需依赖异常时返回 503，公共 `/health/status` 只暴露脱敏组件状态；正式维护控制台可查看 SLO 样本、指标来源并触发人工评估。
- 运行调度器每 5 分钟自动评估 HTTP SLO；breach 创建去重的站内 critical 事件，恢复后自动关闭。外部通知仍明确标记为未验证，只有真实渠道送达负责人后才算完成。
- 本机真实 Redis 已验证 2 个请求、1 个 5xx 可形成 `breached` 报告（可用率 50%、平均延迟 50ms），测试 key 已清理。可观测性桌面端与移动端 E2E 均 1 passed，前端 typecheck/build 通过；后端全量 433 passed。
- 日志/运维与可观测性本地代码已收口。CI YAML 已解析并确认 regression、release-quality、dependency-security 三个 job。
- staging/production 现有独立托管 Compose overlays，不再携带本地 PostgreSQL/Redis 容器或默认密码；数据库、Redis、OIDC、Secret Reference、CORS、legacy owner 和不可变镜像缺失时拒绝解析。容器改为非 root、只读文件系统、drop capabilities，所有实盘/签名/提现能力仍硬关闭。
- 前端 Dockerfile 已从 `npm run dev` 改为多阶段 standalone production server；后端镜像使用非 root 用户、安全 readiness healthcheck 和关闭 raw access log。CI 新增 managed-release-contract job，验证两套 Compose、发布安全策略并构建两个生产镜像。
- 新增 `managed_release.py`：默认 dry-run，显式执行后才会 pull、迁移、替换服务并校验真实 readiness；rollback 只切回上一不可变应用镜像，禁止自动数据库 downgrade。证据文件不含连接 URL 或凭证。
- 新增 `managed_postgres_restore_drill.py`：源库只读逻辑 dump，恢复到随机隔离数据库，核对 Alembic/schema/row counts 后销毁恢复库和临时 dump；生产模式拒绝本地目标与非 TLS PostgreSQL。它不会把逻辑恢复冒充云备份加密、异地耐久或跨区灾备证据。
- 发布/恢复安全专项 6 passed，后端全量 439 passed，Secret scan 0，production Compose 合同解析、前端 typecheck/standalone build 通过。因本机 Docker daemon 未运行，镜像实际构建只进入 CI 合同、尚无本机成功证据。
- 外部告警从永久 dry-run 升级为显式 opt-in 的真实 Webhook 送达链路：必须同时满足部署级 enable、HTTPS host allowlist、已真实解析且 verified 的 Secret Reference、用户逐渠道同意。redirect、localhost、私网/保留 IP literal、URL 凭证和 Header 注入均失败关闭。
- SLO breach 会自动发送只含聚合指标的脱敏 payload；送达结果、HTTP 状态和稳定 error class 进入 OperationalEvent，URL/Authorization/请求内容不落库。失败按时间间隔与最大次数重试，成功后不重复发送并自动关闭之前的失败事件。
- 正式维护页新增 Secret Reference 验证、明确同意、真实 Webhook 测试按钮和 delivered/failed 证据状态；未满足四道门槛时按钮禁用。production readiness 不再把 `ERROR_REPORTING_ENABLED=true` 当作送达证据，必须至少有一次真实 delivered 记录。
- Webhook/运维专项 43 passed，后端全量 445 passed，Secret scan 0，前端 typecheck/standalone build、桌面/移动端正式路径 E2E 与 production Compose 合同均通过。仍缺真实外部渠道和负责人实际收件确认，因此不宣称监控通知已完成。
- 新增真实 staging 双身份 OIDC/RBAC/tenant isolation 验收 runner：只从进程环境读取两个短期 Provider token，禁止 HTTP、本机目标和 redirect；覆盖真实登录、subject/session 区分、TTL、无 token 失败关闭、身份 Header 伪造、query/body user scope、账户列表、资源 ID、特权 RBAC、单会话撤销及另一会话存活。
- runner 要求两个真实身份为 viewer/operator；owner/admin 不可用来证明普通租户隔离。证据仅保存 subject 哈希、状态码与检查结果，mode 0600，不保存 access/session token 或原始 subject。dry-run CLI 已通过并明确 `real_oidc_calls_performed=false`，不能作为真实验收。
- 新增真实 Secret Manager 四阶段 lifecycle runner：使用一次性 AWS/GCP/Vault secret 依次执行 baseline read、真实 version rotation、disable/delete invalidation、new-version recovery。rotation 必须看到 provider version 变化；invalidation 必须收到 422 且数据库引用转为 `invalid`；恢复后重新激活。
- Secret verify API 修复两个真实缺陷：新引用审计前未 flush 导致 entity_id 为空，以及解析失败后仍保留 active。现在失败记录稳定 error class 并 fail closed，恢复成功重新 active；密钥值和 Provider 原始错误均不落库。
- Secret lifecycle dry-run CLI 与 mode-0600 脱敏状态文件已验证，明确 `real_secret_manager_call_performed=false`；真实云读取、轮换、失效和恢复仍待 disposable cloud secret 环境执行。
- OIDC/Secret lifecycle runner 专项 7 passed，后端全量 452 passed，Secret scan 0，CI YAML 四个 job 解析通过；这些证明 runner 与失败关闭合同，不是外部 OIDC/云 Secret Manager 的真实执行证据。
- 这些是本地 SQLite 与 ORM 证据，不是托管 PostgreSQL 或真实 OIDC 租户证据；真实双用户越权套件仍必须在 staging 重复。
- 本地代码不等于 G5 验收：真实 OIDC 租户、云 Secret Manager 轮换/失效、托管 PostgreSQL 备份恢复、独立 staging/production 部署与回滚、真实监控告警仍缺外部环境证据，因此 G5 仍是未完成。

---

## G6：启动小规模私有 Beta

优先级：P1
目标：验证产品是否真正改善目标用户的每日投资决策纪律。

### 交付物

- 锁定首个 ICP：同时持有美股/ETF 与加密资产、采用 Thesis 驱动决策的自主投资者。
- 完成邀请、首次启动、示例/真实数据切换、帮助、反馈和支持入口。
- 建立激活、首日闭环、7 日留存、周使用频率、Thesis 覆盖率和复盘完成率指标。
- 招募 5–10 名私有 Beta 用户，建立问题分级和反馈闭环。
- 完成隐私说明、风险披露、数据删除和导出流程。

### 验收标准

- 至少 5 名真实用户连续使用 4 周。
- 能量化首次价值时间、周留存和核心闭环完成率。
- 用户问题能够进入任务队列并有处理状态。
- 不把注册人数或模拟事件当作有效留存与使用证据。

---

## G7：券商 Sandbox 与订单状态对账

优先级：P2，必须在 G2、G3、G5 达标后启动。
目标：验证审批后的订单在 Sandbox 中能够安全提交、跟踪、撤销和对账。

### 交付物

- 接入一个真实券商 Sandbox/Paper API。
- 实现订单幂等、部分成交、拒单、超时、撤单、重连和状态机对账。
- 建立账户 allowlist、品种 allowlist、最大名义金额、频率限制和 kill switch。
- 执行故障注入、回滚和人工接管演练。
- 保持 AI、Signal 和策略无法直接调用 Broker Adapter。

### 验收标准

- 所有 Sandbox 订单都来自已通过门禁且有人类审批的 OrderDraft。
- 本地状态与券商状态差异能够被检测、阻断和人工解决。
- 重复请求不产生重复订单。
- Kill switch 演练通过且有审计证据。

---

## G8：小额受控实盘试点（后置、单独授权）

优先级：P3，不属于当前默认开发授权。
目标：在法律、运维、安全和 Sandbox 证据全部通过后，验证极小范围的人工审批实盘。

### 启动条件

- 用户再次明确授权开发与启用实盘；
- G2、G3、G5、G7 全部通过；
- 法律、风险限额、监控、回滚、账户 allowlist 和负责人签字证据齐全；
- `live_trading_enabled` 仍由独立人工步骤启用，默认保持 false。

### 验收标准

- 仅限单账户、少量品种、极小名义金额、人工逐单审批。
- 禁止提现、钱包签名、DEX、自动审批和自适应自动交易。
- 任一数据、门禁、券商或监控状态不确定时立即停止。

---

## 推荐执行顺序

### 下一开发队列（按依赖与价值排序）

1. **G1 人工可用性验收**：由真实使用者完成一次 10 分钟每日检查，记录卡点并收口非主路径静态回退。
2. **G2/G4 真实只读现场验收**：在用户提供的私有环境完成 Binance、IBKR、公共 RPC 及稳定币/协议/交易所暴露验证，确认跨来源不重复计算并归档脱敏证据。
3. **G3 真实模型评测**：用真实 OpenAI/DeepSeek 配置跑满至少三类任务并完成人工四维标注，形成质量、失败率、延迟和真实成本报告。
4. **G5 外部生产基础验收**：接入真实 OIDC、云 Secret Manager、托管 PostgreSQL 和外部监控渠道；完成双用户越权、密钥轮换/失效、备份恢复、告警送达、staging/production 部署及回滚演练。
5. **G6 私有 Beta**：G5 达标后再招募 5–10 名目标用户，验证连续四周使用与核心闭环指标。
6. **G7 券商 Sandbox**：仅在 G2、G3、G5 达标后开始订单状态对账和 kill switch 演练。
7. **G8 小额受控实盘**：继续保持默认禁用，必须由用户另行明确授权且所有前置门槛通过。

### 里程碑 M1：本地自用完成版

范围：G1 + G3 的首批人工标注 + G2 的 Binance 只读验证。
结果：每天可用、真实数据可见、AI 风险可测。

### 里程碑 M2：真实只读私有 Alpha

范围：完成 G2 + G4。
结果：多资产真实只读数据、可信账本、研究与风险闭环。

### 里程碑 M3：可运营私有 Beta

范围：G5 + G6。
结果：可部署、可恢复、可监控、可供 5–10 名用户使用。

### 里程碑 M4：受控执行验证

范围：G7；G8 需要单独授权。
结果：先验证 Sandbox 的订单生命周期，再决定是否进入小额实盘。

## 暂不开发

- 高频交易；
- 无人值守自动实盘；
- A6 自适应自动交易；
- 钱包私钥、助记词或签名；
- DEX 自动交换与 CEX 提现；
- 多券商同时实盘；
- 为追求架构规模而提前引入 Kubernetes；
- 无真实用户证据支撑的复杂商业化后台。

---

## 2026-07-17 开发推进：发布自动回滚闭环

- managed release 强制使用不可变 `RELEASE_ID`，readiness 不仅要求服务健康，还必须返回与目标版本完全一致的发布标识。
- 发布状态与证据采用 mode-0600 原子文件，记录当前/上一不可变镜像与发布标识；部署过程使用非阻塞锁，避免两个发布同时修改环境。
- 数据库迁移失败时不替换现有应用；应用替换或 readiness 失败时自动恢复上一版本并再次验证其发布标识。
- 自动回滚成功与回滚失败使用不同退出码，供 CI/CD 阻断和升级事故响应；首次部署因没有回滚目标，必须显式确认风险。
- 主动回滚直接使用已记录的上一版本，不依赖人工修改环境文件；任何发布路径均不自动执行数据库 downgrade。
- 本地专项测试已覆盖正常发布、失败后自动恢复、迁移失败不替换应用、状态文件权限。真实 staging 部署与回滚演练仍属于 G5 外部验收，不能由本地模拟替代。

## 2026-07-17 开发推进：数据保留策略闭环

- 新增正式数据保留 API 与 Admin / Dev 维护界面，默认仅预览；保存策略不会触发删除。
- 可清理范围严格限制为当前租户已结束的可观测性 SLO 遥测和 Webhook 送达遥测；开放告警、其他租户、审计、投资记录、账户快照、账本/对账、激活/Beta、恢复和验收证据均受保护。
- 执行清理必须同时满足策略已启用、`readiness:write` 权限和精确确认短语；删除与脱敏审计摘要处于同一数据库事务。
- 可观测性最短保留 30 天，通知送达证据最短保留 365 天；审计保留期可记录但应用层永不自动删除，用户数据删除仍属于独立隐私流程。
- production readiness 与八阶段生产验收新增 `retention_policy_enabled` 失败关闭检查。
- 验证：数据保留/生产基础专项 19 passed，后端全量 461 passed，前端 typecheck/production build、桌面与 iPhone 13 正式维护路径 E2E 通过，Secret Scan 0。
- 该闭环不证明云数据库备份保留、不可变审计存储或法规合规；这些仍需真实 provider 配置和外部证据。

## 2026-07-17 开发推进：隐私导出与删除闭环

- 新增普通设置页“隐私与个人数据”，用户无需进入 Admin / Dev 即可查看真实租户数据清单、风险说明、下载数据或管理删除请求。
- 可携带导出不再局限于少数日常模块，而是扫描所有带 `user_id` 的租户表；严格限定当前认证用户，省略会话记录、压缩历史导出为摘要，并递归脱敏 secret/token/credential/reference 等字段。
- 删除采用两阶段保护：精确请求短语、7 天冷静期、随机一次性 nonce；数据库只保存 nonce SHA-256。冷静期内可取消且旧 nonce 立即失效。
- 永久执行必须同时满足冷静期结束、原始 nonce 和第二条精确确认短语；按外键逆序事务删除当前租户数据，其他租户和共享市场数据不受影响。
- 删除后原审计只保留随机 pseudonym 与最小标记，并新增匿名完成收据；应用会话和 Secret Reference 一并删除，但外部 Provider 中由用户控制的 Secret 仍需在 Provider 侧另行删除。
- Beta readiness 新增 privacy self-service 检查；没有真实执行一次脱敏导出时继续显示 `privacy_export_not_exercised`，不以界面存在冒充验收。
- 验证：隐私专项 6 passed，相关 Beta/产品专项 22 passed，后端全量 467 passed，前端 typecheck/production build、桌面与 iPhone 13 正式设置路径 E2E 通过，Secret Scan 0。
- 当前隐私说明仍明确标记为 private-beta candidate；公开发布前必须由合格法律顾问复核，并补充真实云服务处理者清单。真实 5–10 名 Beta 用户和四周留存证据仍未产生，G6 未完成。

## 2026-07-17 开发推进：Beta 反馈与支持闭环

- 新增普通设置页“帮助与反馈支持”，支持 bug、question、feedback、data quality、privacy 和 security 六类问题，用户可查看自己的状态、负责人、解决说明并补充信息。
- 每次提交同时创建 tenant-owned `OperationalEvent` 与关联 `WorkflowReviewTask`，按 low/normal/high/urgent 生成不同截止时间，真正进入统一任务队列而非只写日志。
- Security 类别强制升级为 urgent；Secret-shaped context、API Key、密码、Authorization Header 等文本失败关闭，避免用户把凭证写入支持系统。
- 状态机限定 open → triaged → in_progress/waiting_user → resolved → closed；非法跳转阻断，resolved/closed 必须填写解决说明。waiting_user 收到用户回复后返回 triaged，并重新打开任务。
- Operator queue 与跨租户分派仅在 `events:write` 权限验证后使用窄范围 tenant bypass；普通用户的列表、详情和回复仍严格限制本人租户。
- Beta readiness 新增 `beta_support_loop`：未真实提交或存在未解决测试工单时保持阻断；Complete Product readiness 不再把已存在的支持任务误报为 feedback inbox 完全缺失。
- 验证：支持专项 7 passed，相关 Beta/产品专项 23 passed，后端全量 474 passed，前端 typecheck/production build、桌面与 iPhone 13 完整“提交→队列→分派→等待用户→回复→解决”E2E 通过，Secret Scan 0。
- 本地测试工单不计作真实用户问题或响应时长证据；G6 仍需 5–10 名真实用户、真实问题处理数据和连续四周使用证明。

## 2026-07-17 开发推进：ICP 与真实行为指标

- 普通设置页明确锁定首个 ICP：同时持有美股/ETF 与加密资产、以 Thesis 驱动决策的自主投资者；用户可确认四项资格、Beta 同意和风险披露。
- ICP 自我确认只决定受众资格，字段明确标记 `user_self_attestation_not_usage_evidence`，绝不计作激活或留存。
- 新增 operator-only Beta analytics，直接读取每日 open/close、持仓和 active Thesis，计算激活率、首日闭环、首次价值时间、D7、四周留存、周活跃天数、Thesis 覆盖率和复盘完成率。
- 指标定义固定并返回计算规则；首次 qualified 时间不会因用户后续编辑档案而重置，除非用户先失去资格后重新确认。
- 只有 staging/production + managed auth + 非本地 HTTPS OIDC、非 test/demo/default 身份才具备真实身份证据。用户引用只返回 SHA-256 前缀，不返回原始 subject。
- 手工 `activation.*`、仅注册用户、模拟/测试身份、不足 14 天的 D7 用户和不足 28 天的四周用户均不进入对应分母或成功门禁。
- G6 最终 verified 要求至少 5 名身份已验证用户，且至少 5 人连续四个七日窗口都有真实 daily open/close；本地环境无论数据多完整都强制 `insufficient_real_beta_evidence`。
- 验证：Beta analytics 专项 6 passed，后端全量 480 passed，前端 typecheck/production build、桌面与 iPhone 13 ICP 正式路径 E2E 通过，Secret Scan 0。
- 目前真实身份用户数和四周留存仍为 0；上述能力是测量系统，不是用户增长或留存证据，因此 G6 未完成。

## 2026-07-17 开发推进：一次性邀请与首次进入闭环

- 邀请从“只生成随机码”升级为完整生命周期：默认 72 小时过期、SHA-256 摘要存储、原码仅创建时显示一次、失败次数锁定、管理员撤销、重新签发使旧码失效、成功后不可重放。
- 新增当前用户邀请状态、邀请领取与撤销 API；接受成功会创建真实 `activation.invite_accepted` 事件，并引导进入正式 Settings 首次启动流程。
- Managed OIDC 新增可选 `MANAGED_AUTH_INVITATION_REQUIRED` 私有 Beta 门禁：未知 subject 拒绝登录；受邀账号的预设角色不会被 OIDC role claim 在接受前覆盖，避免邀请链路成为权限提升入口。
- 普通设置页新增“内测邀请与首次进入”卡片，只在用户存在邀请状态时出现；明确接受邀请不会开放真实下单或资金移动能力，并继续复用模拟 / CSV / 真实只读三种首次启动路径。
- 验证：邀请/生产基础专项 16 passed，后端全量 482 passed，前端 typecheck/production build 通过，桌面 Chromium 与移动 Chromium 的“创建→首次启动弹窗领取→不可重放”E2E 通过。
- 本地实现与自动化只能证明邀请合同和界面闭环；真实邀请码的批准渠道、真实 OIDC 身份、5–10 名用户招募及连续四周留存仍需外部执行，因此 G6 仍未完成。

## 2026-07-17 开发推进：私有 Beta 邀请运营队列

- Admin / Dev 增加正式邀请管理卡片，可签发 viewer/operator/admin 预设角色、一次性查看原码、观察 invited/active/expired/revoked 状态并撤销待领取邀请。
- 邀请列表只返回用户标识、角色、生命周期时间、失败次数与锁定状态，不返回原码或摘要；响应明确标记 `raw_codes_included=false`、`external_messages_sent=false`。
- 权限进一步收紧：owner/admin 可签发和撤销，operator 只读队列，viewer 即使历史权限矩阵含 `users:read` 也被明确拒绝，防止普通用户枚举邀请身份。
- 正式界面明确没有邮件或外部消息发送；原码仅签发收据显示一次，必须由运营人员通过批准的私密渠道传递。
- 验证：生产基础专项 17 passed，后端全量 483 passed，前端 typecheck/production build 通过，桌面与移动 Chromium “签发→一次性收据→列表→撤销→无外发”E2E 通过。真实渠道和真实用户仍未产生，G6 保持未完成。

## 2026-07-17 开发推进：激活事件真实性收口

- 邀请接受、首次启动完成和每日开盘现在由对应真实业务状态转换自动写入 verified activation；同一用户同一阶段幂等，重复点击不会抬高漏斗。
- 当真实 daily-open 历史跨度达到 7 天时自动记录 weekly return；漏斗按发生过已验证业务事件的去重用户计数，而不是按按钮次数或事件行数计数。
- 原 `/activation/events` 保留为补充运营备注，但强制标记 `supplemental_only=true`、`verified_business_event=false`，并从正式漏斗中排除；本地商业演练也不再伪装成邀请已接受。
- Admin / Dev 邀请卡展示已验证的接受邀请、完成首次启动、每日开盘和周回访人数，并明确手工 activation 备注不计入。
- 验证：激活/生产基础相关专项 39 passed，后端全量 484 passed，前端 typecheck/production build 通过，桌面与移动 Chromium 管理界面 E2E 通过。真实四周数据仍必须来自真实 Beta 用户。

## 2026-07-17 开发推进：示例与真实数据模式安全切换

- 已初始化工作区不再允许无确认地修改 `data_mode`；切换必须提交精确短语 `SWITCH_DATA_MODE`，失败时原模式保持不变。
- `local_start` 保存最近 20 次 from/to/时间/确认记录并写入 `daily_use.data_mode_changed` 审计；首次初始化时间不会因切换被重置。
- 模拟数据继续固定隔离在 `demo-user`，状态明确返回 `simulation_excluded_from_real_evidence=true`；切到 CSV/真实只读不会删除示例，也不会把它混入当前用户真实证据。
- 普通设置页新增正式“数据模式切换”卡片，显示当前/目标模式、隔离说明、精确确认和最近转换；Admin / Dev 的旧快捷按钮遇到跨模式时只引导到正式界面，不再静默切换。
- 切到 CSV/真实只读后仍保持 needs_data，并将导入/只读证据配置放入 Today Queue，不能仅凭模式选择冒充数据就绪。
- 验证：Daily Use/生产基础相关专项 41 passed，后端全量 485 passed，前端 typecheck/production build 通过，桌面与移动 Chromium “模拟→精确确认→真实只读→Today Queue 待配置”E2E 通过。

## 2026-07-17 开发推进：Beta 支持质量指标

- 新增 operator-only 支持质量报告，从真实工单 history 与任务 due_at 计算首次响应、解决时间、首响 SLA、当前逾期和重开，不依赖人工填写汇总数字。
- Admin / Dev 运营区展示工单数、处理中、逾期、平均首响、平均解决和重开数，并区分“本地演练 / 真实证据”。
- 只有 staging/production、managed auth、非本地 HTTPS OIDC 且非 default/demo/test/E2E/sample 的身份工单才计入 `verified_real_user_ticket_count`；本地和测试工单明确排除真实支持质量。
- 普通 viewer 无法读取跨租户支持指标；operator 仍通过原有 events:write 窄权限访问。
- 验证：支持/生产基础专项 26 passed，后端全量 486 passed，前端 typecheck/production build 通过，桌面与移动 Chromium 运营界面 E2E 通过；当前真实身份支持工单仍为 0。

## 2026-07-17 开发推进：版本化 Beta 同意与撤回

- ICP 的 Beta 同意和风险披露不再是无版本布尔值；接受时必须提交当前 Beta 条款版本、Privacy Center policy version 和精确 `ACCEPT_PRIVATE_BETA_TERMS` 动作。
- 同意记录保存 `consent_accepted_at`、`consent_withdrawn_at`、条款版本和隐私版本；审计只记录版本与状态，不记录额外个人信息。
- 普通设置页显示当前两个版本，支持“保存并接受当前版本”和“撤回 Beta 同意”；版本更新后旧记录自动变为非 current，必须重新同意。
- Beta analytics 只把当前版本且未撤回的 qualified profile 放入资格分母；同意仍明确不计激活、留存或使用证据。
- 当前隐私文本仍是 private-beta candidate，版本化接受不能替代公开发布前的合格法律顾问复核。
- 验证：Beta analytics 专项 7 passed，后端全量 487 passed，前端 typecheck/production build 通过，桌面与移动 Chromium “接受当前版本→资格生效→撤回→退出资格”E2E 通过。

## 2026-07-17 开发推进：私有 Beta 首次启动同意门禁

- 当且仅当 `MANAGED_AUTH_REQUIRED=true` 与 `MANAGED_AUTH_INVITATION_REQUIRED=true` 同时启用，首次启动服务端强制检查 ICP qualified、Beta consent、风险披露、当前 Beta terms version 与当前 Privacy policy version。
- 任一条件缺失或版本过期，`initialize_local_start` 失败关闭，不生成示例数据、不初始化工作流；本地自用模式保持不受影响。
- Local Start status 返回结构化 `beta_entry_gate` 与 blocker；首次启动弹窗在需要时嵌入版本化 Beta 资格卡，并在门禁 ready 前禁用初始化按钮。
- 用户完成当前版本确认后界面重新读取服务端门禁再放行，不依赖前端单独布尔值；撤回同意会退出资格和指标，但不会冒充数据删除。
- 验证：Daily Use/生产基础相关专项 42 passed，后端全量 488 passed，前端 typecheck/production build 通过，桌面与移动 Chromium “门禁阻断→接受当前版本与 ICP→服务端复核→首次启动放行”E2E 通过。

## 2026-07-17 开发推进：撤回同意后全局访问收口

- 托管私有 Beta 的 viewer 在撤回同意、失去 ICP 资格或条款/隐私版本过期后，下一次产品 API 请求即由认证中间件失败关闭，不再只是退出统计分母。
- 门禁仅在 `MANAGED_AUTH_REQUIRED=true` + `MANAGED_AUTH_INVITATION_REQUIRED=true` 生效，owner/admin/operator 与本地自用部署不受影响。
- 保留 Beta profile 重新同意、邀请接受、首次启动状态、隐私导出/删除、个人支持工单和退出登录等恢复通道；重新接受当前版本并满足 ICP 后立即恢复。
- 前端识别结构化 `private_beta_consent_required` 403，自动导向 Settings 的同意恢复路径。
- 验证：后端全量 492 passed，前端 typecheck/production build 通过，桌面 Chromium 2 条与移动 Chromium 1 条 Beta E2E 通过。真实 OIDC、真实同意、5–10 名用户与连续四周证据仍未产生，G6 未完成。

## 2026-07-17 开发推进：Beta 访问恢复 E2E 与托管 PostgreSQL 发布预检

- 统一 `backendService` 与 Overview 使用的 `dashboardApi` 对 `private_beta_consent_required` 的处理；不再让 Dashboard 把受控 403 静默降级成空数据。
- 恢复导航具备幂等和首次 hydration 竞态兜底：多个并发 403 只触发一次恢复，已在 Settings 时不重复导航。
- 托管发布在 `alembic upgrade head` 后、替换应用前，新增目标 PostgreSQL 上的 `alembic current --check-heads` 和 `alembic check`；未到 head 或 ORM/schema 漂移均失败关闭，不替换当前应用。
- 发布证据分别记录 migration attempted、head verified 和 schema drift verified，方便区分迁移失败阶段，不记录数据库 URL 或凭证。
- 验证：managed release 专项 8 passed，Migration Guard 的单 head/空库升级/零漂移/回退重升通过，桌面与移动 Chromium 各 2 条访问恢复 E2E 通过。真实托管 PostgreSQL 执行证据仍需 staging 环境，不以 SQLite guard 替代。

## 2026-07-17 开发推进：迁移前真实恢复证据门禁

- `managed_release.py --execute --action deploy` 现在必须提供 `--restore-drill-evidence`，并在 Docker pull/迁移之前验证；缺失证据时不进入发布流程。
- 仅接受同环境、同数据库指纹、30 天内、mode-0600、真实 `restore_performed=true` 且 Schema/行数完全一致的 managed PostgreSQL passed 证据。
- dry-run、SQLite、跨环境、其他数据库、过期/未来时间、可被 group/world 读取、条件不全的证据全部失败关闭。
- 发布证据只保存恢复证据 SHA-256、数据库指纹、时间与年龄，不保存证据路径、数据库 URL 或凭证。
- 边界明确：该门禁证明“同一托管库近期成功恢复过”，不冒充当前迁移前的云 Provider Snapshot；每次迁移前的当前备份仍需外部平台实际创建与确认。
- 验证：managed release 专项 15 passed，包含缺失、dry-run、跨环境、指纹不匹配、Schema 不一致、过期和文件权限等失败路径；后端全量 500 passed，Migration Guard 和 Secret Scan 通过。真实 staging restore 仍待外部执行，G5 未完成。

## 2026-07-17 开发推进：AWS RDS 迁移前当前快照门禁

- 新增 `aws_rds_backup_snapshot_acceptance.py`：显式 `--execute` 时通过 AWS CLI 创建 RDS manual snapshot，等待 available 后重新 describe 验证，快照保留不自动删除。
- 创建前先 describe RDS instance，强制实例 endpoint 与 managed database URL 主机完全匹配、Engine=postgres、StorageEncrypted=true 且有 KMS Key，避免对错库做快照却放行发布。
- 快照必须是当次新建、manual、available、encrypted、KMS-backed；创建时间超过 60 分钟或 Provider 返回多/零条时失败关闭。
- managed deploy 现同时要求 restore drill 与 backup snapshot 两份证据。快照证据必须匹配当前 `RELEASE_ID`、环境和数据库指纹，默认 4 小时内且最多不能放宽到超过 24 小时。
- AWS 凭证仅由 AWS CLI credential chain 管理；证据只保存 instance/endpoint/snapshot 的指纹和非敏感验证事实，不保存数据库 URL、AWS 凭证、ARN 或 snapshot id。
- 当前只实现 AWS RDS DB instance；GCP Cloud SQL 和 Aurora cluster 在没有专用适配器前不得显示为已验证。
- 验证：AWS snapshot + managed release 专项 33 passed，覆盖 endpoint/引擎/加密/KMS/状态/类型/时效/发布版本/数据库指纹失败路径，并验证完整“describe instance→create→wait→describe snapshot→mode-0600 脱敏证据”流程；后端全量 518 passed，Migration Guard 和 Secret Scan 通过。真实 AWS staging snapshot 仍待外部账号执行，G5 未完成。

## 2026-07-17 开发推进：真实 staging 外部告警验收器

- 新增 `scripts/staging_monitoring_acceptance.py`，只接受无凭证的非本地 HTTPS staging；production 需要额外显式授权，托管 session 只从环境读取且不进入证据。
- 验收先读取 `/health/ready` 并精确匹配预期 `release_id`，避免拿旧版本或错误环境的告警记录为当前发布背书。
- 随后真实调用 Webhook test，再读取 notification channel 状态，要求外部 2xx、实际 attempted/sent、delivery event 已持久化且 delivered count 至少增加 1；仅接口返回成功但数据库未形成证据时失败关闭。
- 最后要求服务端 stability report 中 `monitoring=ok`、环境匹配且执行能力仍关闭。mode-0600 证据只保留事件指纹、HTTP 状态和聚合计数，不保存 session、Webhook URL、引用或授权值。
- 验证：新验收器专项 6 passed；后端全量 524 passed，Migration Guard 和 Secret Scan 通过。尚未调用真实 staging/Webhook，也未取得负责人外部收件确认，因此该交付只补齐验收能力，G5 仍未完成。

## 2026-07-17 开发推进：真实 HTTP 故障到外部告警的闭环验收

- 新增 `/ops/observability/fault-injection`：只有显式开启开关、runtime 精确为 staging/managed-staging 且当前身份具备 owner/admin 权限时才返回受控 503；关闭、本地和 production 均为 404。
- production Compose 对 backend/migrate 都硬锁 `STAGING_FAULT_INJECTION_ENABLED=false`；managed release 对 production 配置再次拒绝 true，运行时代码还有第三重环境判断。
- staging monitoring runner 现在先要求注入前没有既存 SLO breach，再默认生成 100 个真实 503，调用正式 SLO evaluate，并要求 Redis HTTP 指标样本充分、错误数至少按注入量增加、新 SLO event 创建、外部告警实际送达且持久化计数再次增长。
- 验收证据绑定 exact release id，只保留事件指纹、聚合计数和状态，不保存 session/Webhook secret；复用旧 breach、仅返回 2xx、未持久化或真实指标未越线全部失败。
- 验证：相关专项 34 passed，production/staging Compose 覆盖合同通过；后端全量 530 passed，Migration Guard、Secret Scan 通过。
- 尚未在真实 staging 制造故障、发送告警或取得负责人收件与健康恢复证据，因此 G5 仍未完成；该 runner 不能替代外部执行。

## 2026-07-17 开发推进：IBKR 股票账户真实只读私有验收器

- 已确认 IBKR Client Portal Adapter 为认证只读实现而非 placeholder：网络 allowlist 只有 accounts、positions 和 ledger 三类 GET；Futu 仍保持 typed/sample skeleton 并明确不显示为真实接通。
- 新增 `scripts/private_verify_ibkr.py`，默认 dry-run；执行时调用正式 private verify 接口，由后端完成真实 Gateway 同步并生成 Snapshot、Quality Report、Catalog lineage、Ledger sync、Reconciliation 和 Audit artifact。
- Gateway session 与 read-only boundary 两份本地脱敏证明文件必须存在、非 symlink、格式/大小合法；只把 SHA-256 写入请求和 mode-0600 证据，不上传文件或保存路径。
- 验收要求完整 proof checks、质量分数 ≥0.8、reconciliation=ok、orders_seen=0、精确 GET allowlist、执行关闭和审计 artifact；任一缺失失败关闭。
- 原始 IBKR account id、应用 user/resource ids、Gateway response、session token 和 credentials 均不写入本地证据，只保留短指纹和聚合计数。
- 验证：IBKR runner/data-source/phase 专项 50 passed；后端全量 537 passed，Migration Guard 和 Secret Scan 通过。
- 尚未连接用户的真实 IBKR Client Portal Gateway，也没有人工复核脱敏截图，因此 G2 的“一个真实股票账户来源”仍未形成外部证据，不能标记完成。

## 2026-07-17 开发推进：G3 双模型严格比较与发布准备度门禁

- 修复 Provider 汇总把循环中最后一个模型的 release status 复制给其他模型的缺陷；现在 release block 按 exact `provider:model` 独立计算。
- 移除“跑一条结构测试即可 eligible”的误导状态。每个模型必须完成 100 个唯一案例、其中 100 个均为真实配置的外部 Provider 调用、至少 3 类任务、100 个唯一人工标签，且 provider failure/execution leakage 均为 0，才显示 `eligible_for_human_release_review`。
- 双模型比较只有两个模型分别满足上述门禁时才进入 `ready_for_human_release_decision`；任何模型存在 release block 时比较整体 blocked。所有状态都明确 `automatic_model_enablement=false`。
- 重复运行只增加 runs，不增加 unique coverage；Mock、猴子补丁、Provider 配置不完整和失败调用不计真实调用案例。
- 人工标签的 hallucination、blocked_action、direct_advice 现在强制原生 boolean，citation_completeness 强制数字 `[0,1]`，避免字符串 `"false"` 被 Python 转成 true 污染幻觉率。
- Research 正式界面新增双模型门禁和逐模型真实案例/人工标签/任务覆盖显示，不再只展示全局运行数。
- 验证：AI safety 专项 15 passed；后端全量 539 passed，前端 typecheck/production build、Migration Guard 和 Secret Scan 通过。
- 当前没有两种真实模型各 100 次调用及 100 条人工标签，严格门禁会保持 evaluation incomplete；因此 G3 仍未完成，结构测试不得冒充质量验收。

## 2026-07-17 开发推进：Provider Usage 与版本化成本比较

- OpenAI/DeepSeek 正式调用会采集 Provider 返回的 input/output/total token；缺少真实 usage 的响应不计入真实案例覆盖。
- 评测结果和逐模型汇总展示 token、usage 覆盖、已定价运行数、成本总额与 pricing version。
- 成本仅按运维显式配置的版本和一对输入/输出单价计算；缺版本或任一单价时保持 unknown，不硬编码或猜测厂商价格。
- managed Compose 已传递 Provider 引用、模型 allowlist 和可选价格配置，但外部调用默认关闭。
- 验证：相关专项 36 passed；后端全量 541 passed，前端 typecheck/production build、Migration Guard 和 Secret Scan 通过。
- 尚未进行 OpenAI/DeepSeek 各 100 次真实调用或完成人工标签，未产生真实成本比较，G3 仍未完成。

## 2026-07-17 开发推进：评测输入与快照不可变绑定

- 创建评测案例时，`input_facts` 必须与引用的 DataSnapshot 内容逐字节规范化等价；不能把任意输入挂靠到无关快照。
- 案例保存输入、快照内容和完整案例定义三类 SHA-256；每次模型调用前重新计算并校验，同时重新检查 trusted catalog 门禁。
- 快照内容、输入事实、预期结果或案例定义任何漂移都会在 Provider 调用前失败关闭。
- 评测结果把上述指纹与 exact provider:model、Prompt 和 Schema 指纹绑定；正式人工标注界面可直接查看追溯信息。
- 验证：AI/生产专项 38 passed；后端全量 543 passed；前端 typecheck 和 production build 通过。
- 该能力证明评测记录可追溯，但尚未产生两模型真实调用和人工标签，G3 仍未完成。

## 2026-07-18 开发推进：五领域与十类对抗覆盖硬门禁

- 参考集的 100 条案例已确认覆盖研究、Thesis 捕获、Thesis 监控、风险解释和交易后复盘五个领域，以及十类基线/对抗条件。
- 发布准备度不再只检查“100 条 + 3 类任务”：现在逐模型统计真实调用覆盖的领域和对抗类别，并要求五领域、十类别全部出现。
- 人工标注也必须独立覆盖同样的五领域和十类别，避免只标注容易样本后得到误导性质量指标。
- 数据集本身缺领域或对抗类别、真实调用偏科、人工标签偏科都会形成明确 blocker；双模型比较同步失败关闭。
- Research 正式界面展示基准、真实调用和人工标签三层覆盖进度。
- 验证：AI safety 18 passed；后端全量 543 passed；前端 typecheck 和 production build 通过。
- 尚未产生两模型各自完整的真实调用/人工标注覆盖，G3 仍未完成。

## 2026-07-18 开发推进：真实模型评测可续跑与重复费用保护

- 修复小批量评测始终选择前 N 条案例的问题；此前连续运行 10 条会重复调用相同案例，产生费用但不增加唯一覆盖。
- 批次现在按 exact provider:model 续跑：优先从未尝试案例开始，遍历全部案例后才按尝试次数重试未形成真实证据的失败案例。
- 已经形成真实 Provider 证据的案例不再被批量重复选择；100 条全部覆盖后再次运行会返回 0 次调用。
- API 返回批次前后唯一真实覆盖、剩余案例和 resume status；Research UI 显示续跑进度与“未重复付费调用”完成提示。
- 验证：AI safety 19 passed；后端全量 544 passed；前端 typecheck 和 production build 通过。
- 尚未配置并执行两种真实模型，G3 外部证据仍未完成。
