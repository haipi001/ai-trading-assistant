# 新终端 Web3 只读材料与真实 RPC · 2026-11-05

状态：钱包/原生币/指定ERC20的只读数据区已实施；受控场景与公共参考地址的原生币真实读取已验证。完整Web3研究闭环与整体整合尚未完成。

## 产品与数据

terminal-ui的链上、资产及钱包业务页在保留原功能的同时增加只读材料区，沿用全局链/钱包/合约及同一套黑白主题。原交易员列表明确标注示例，不能作为研究证据。

余额按链ID、钱包ID、合约地址及上下文版本绑定。原生币和指定ERC20在同一个观察区块高度读取；ERC20 decimals从同块合约读取，不按同名ticker映射资产。数量为精确十进制字符串，不经过float、不补USD估值。快照展示ID、适配器来源、读取时间、区块及未最终确认限制。

授权和协议来自既有TokenAllowance/ProtocolPosition记录，按身份取最新，最多读取200条并提示截断；显示记录来源、时间与陈旧状态，不把历史重复行相加。当前没有完整授权/协议索引，没有记录不能解释为没有风险或仓位。未明确priced的协议记录不展示零估值。数据库记录的来源标签不等于独立链上验证。

链/钱包/合约/身份变化立即隐藏不匹配材料并取消前端等待；晚到响应还需通过身份及版本校验。读取失败保留上次同对象材料、显示失败并暂停新研究预填。服务端保存失败审计，随后读取缓存仍显示最近失败，直到相同对象成功读取。停止等待不宣称后台RPC已取消。

两项研究动作将当前快照ID/区块、记录ID、来源、时间、上下文版本、覆盖限制与有界摘录预填既有AI面板，供用户审阅发送；不自动调用模型，也不形成审批或执行权限。该摘录仍作为问题材料，尚未接入独立的服务端AI附件合同、引用校验和研究产物评估。

## API与实现

- `GET /api/v2/workspaces/onchain/{wallet_id}?chain_id=1&contract_address=&context_version=0`：只读取当前用户已登记、活跃且链匹配的钱包。返回wallet、chain_id、contract_address、context_version、snapshot、last_read_error、recorded_allowances/protocols、coverage、limitations及execution_available/signing_available=false。GET不调用RPC。
- `POST /api/v2/workspaces/onchain/{wallet_id}/refresh`：body同三个选择字段，拒绝额外字段和自定义RPC/签名指令；使用既有注册表公共HTTPS节点。成功写已有DataSnapshot（新type terminal_onchain_readonly，usable_for_trading=false）及terminal.onchain.read审计；失败不写部分快照，写terminal.onchain.read_failed审计并返回502 onchain_rpc_unavailable。未拥有/停用钱包404，未知链或链不匹配422，会话沿用既有认证/read权限。
- 缓存须同时具有对应读取审计证明；普通存储记录不能只伪造snapshot_type就被呈现为该RPC读取产物。10分钟以上或未来时间异常标陈旧。JSON字段与既有表复用，无迁移。
- 复用EvmRpcReadOnlyAdapter，新增eth_blockNumber及固定高度读取方法；允许方法仍全部只读，不提供签名、构造交易、广播或撤销授权。
- 主要代码：backend/app/api/terminal_onchain.py、backend/app/adapters/evm_rpc_readonly.py、src/terminal-onchain.js/.jsx/.css、src/main.jsx。main注册API并在嵌入页挂接，独立旧版保留。

## 验证证据

1. 41项Node整合测试通过（3项链上材料合同/身份/精度/覆盖/摘录检查）；55组前端模型检查通过；新终端及旧版构建通过。仍存在大bundle提示。
2. 隔离SQLite/TestClient下152项相关后端测试通过，1条Starlette依赖弃用提示。覆盖链与钱包归属、托管身份、固定高度、末位精度、decimals=0、错误链、无效RPC值、超时/失败不写部分结果、缓存失败状态恢复、来源证明和记录去重。
3. 原生浏览器受控fixture：ETH链1、合约0xaaaa…余额1.000000000000000001 / 1.234567；展示陈旧且标为controlled_fixture的授权/协议。专属AI按钮预填1587字符，含快照ID与context_version=7，未发送模型请求。黑白主题检查与截图已保存。
4. 受控RPC失败后原快照保留并标更新失败，准备研究按钮禁用；换链8453撤销不兼容钱包，旧余额消失；选Base后得到独立快照，无ETH授权/协议记录。数据库2个快照、2条读取审计及1条失败审计，订单意图/成交均0。后加的“缓存读取保留失败”路径通过API回归验证，未再做浏览器故障重放。
5. 真实外部探针：固定公共参考地址0x000…dEaD、Ethereum原生币，经既有公共节点读取成功，区块26348765，证据为terminal-ui/evidence/onchain-public-read-probe-20261105.json。
6. 原生浏览器→真实后端路由→公共RPC→临时SQLite→页面展示：同一固定公共参考地址，区块26348783、快照cc2e573e-9e13-42b4-92e7-6e18fc89b2ba。该路径使用真实RPC运输，其他fixture地址仍受控；仅验证原生币，不等于真实ERC20/所有链/用户账户完整验收。数据库1快照/1读取审计，订单意图/成交0。摘要见terminal-ui/evidence/onchain-browser-evidence-20261105.json。
7. 原测试前AAPL黑色单屏偏好已原生导入恢复。临时fixture进程65238与67021均已正常停止，8001无监听；静态8850保留。浏览器reload偶见HTML脚本未启动中间态，同浏览器新页可正常启动，未确定根因且未据此重启静态服务。

截图：terminal-ui/evidence/onchain-public-read-{light,dark}-20261105.png（真实公共地址原生币）、onchain-{dark,light,failure}-controlled-20261105.png（受控场景）。最后构建补齐缓存失败显示；图片仍证明所列读取/主题场景，不代替所有最终动态路径验证。

## 未完成

完整授权/协议实时索引、更多ERC20及多链真实读取、完整AI附件及引用/产物/预算/任务闭环、Web3全链故障验收，及股票/CEX研究至Paper、全部旧控件迁移验收。目标active；旧版和完整备份保留，Live关闭，未提交推送部署。
