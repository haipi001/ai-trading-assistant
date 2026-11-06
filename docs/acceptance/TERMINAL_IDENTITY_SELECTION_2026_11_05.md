# 新终端全局账户与钱包适配 · 2026-11-05

状态：只读选项、身份联动和受控浏览器验收通过；不代表真实券商、钱包RPC或全链业务验收完成。

## 后端接口

新增GET /api/v2/workspaces/session/options，沿用read权限和当前认证actor，只查询其Account和活跃Wallet。返回user_id、execution_authorized=false、source=owned_workspace_identities、accounts和wallets；无凭据、余额或签名能力。任一列表超过500则413，避免把截断列表当完整归属清单。

账户返回id/label/account_type/broker/base_currency/mode/markets/paper_eligible。brokerage、broker映射stocks；exchange、exchange_account、crypto_exchange映射cex；未知类型markets为空，不猜测。paper_eligible只表明已有账户的Paper元数据兼容，不授予服务端审批/执行权限。

钱包返回id/label/chain/chain_id；chain_id来自现有只读链注册表的离线解析，未知链为null，不访问RPC。工作区保存继续逐项校验所有全局、分屏和市场记忆中的归属，并新增账户市场、钱包活跃状态和链匹配校验；无数据库列迁移。

## 前端实现

integration/identity-catalog.mjs验证白名单元数据、按市场/链筛选、处理并发与过期响应；identity-service.mjs共用内存会话；identity-controls.mjs提供全局账户、钱包、刷新和错误状态。

- 不自动选择账户或沿用其他市场账户；市场最近选择可恢复，但始终只读。切账户/钱包撤销Paper，保持原账户本机未提交草稿。
- 初始加载/刷新失败/会话变化不复用旧校验标记；未校验选择仍可清除，Paper禁用。已恢复的偏好ID须经当前用户列表校验。
- 分屏锁定对象的身份也经当前列表核对，权限不能越过全局市场/账户/钱包；登录变化清空全局各市场与锁定面板的账户/钱包。
- Paper票据使用同一拥有者选项接口，双向联动全局账户；同名资产还需匹配市场、场所和计价币，不能用BTC/USD替代BTC/USDT。
- 变更请求检查已验证的选定Paper账户，订单意图中账户不一致则本地拒绝；读取/恢复其他账户草稿不能进入当前票据。服务端原门禁、权限、审批和幂等执行仍是权威。
- 非行情子页也携带全局场所、周期和已验证用户身份供AI历史隔离；AI抽屉显示账户/钱包名称及短标识。

## 证据

临时后端：terminal-ui/scripts/serve-paper-fixture.py；独立数据库/tmp/terminal-identities-browser-20261105-a.sqlite，3个模拟账户与2个受控登记钱包，无真实连接/模型/RPC。测试后端已停止，8001无监听。

浏览器：股票仅显示两个brokerage账户；账户A暂存数量7、限价225.12和受控理由→切B后只读且表单空→票据内切A同步全局并恢复原表单；切CEX仅提供exchange_account且不继承股票账户；切回股票恢复A并保持只读。Ethereum仅提供ETH钱包；改链8453后清空ETH钱包并仅显示Base钱包；Web3的Paper始终禁用。AI抽屉显示同一链/钱包上下文。

后端停止后点刷新账户：旧选项变待校验、只读、Paper禁用；随后清除测试选择。此轮数据库order_intents/order_drafts/executions均0，未新增模拟交易。跨刷新恢复未提交表单仍未实现，父页面内存缓冲不等于持久化草稿。

32项Node整合测试、55组原前端模型检查通过；工作区/配置/认证/交易权限/手动证据/Paper原子执行/Ace相关120后端测试通过，1条Starlette依赖弃用提示；新旧构建通过，仍有大bundle提示。

未证明真实账户连接、真实钱包数据、CEX研究到Paper、股票完整研究链或所有949控件及视觉行为通过；也没有因前端PAPER模式开启Live、签名或自动执行。下一步继续每市场布局记忆、受控研究链与Web3只读数据接入。
