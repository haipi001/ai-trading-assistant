# terminal-ui 工作区适配 · 2026-11-04

状态：增量实现与受控验证；完整迁移和真实用户E2E未完成。

新终端仍使用 terminal-ui/index.html、app.js、workspace.js 和 8850 启动方式。旧 React App 增加嵌入入口：隐藏旧顶栏与主导航，复用业务组件、图表、脚本、策略与覆盖层，由新终端命令/目录/分屏承载。功能包由 `npm run build:terminal` 生成到相邻 terminal-ui/features；旧版入口保留并独立构建通过。

## 接口兼容

`GET/PUT /api/v2/workspaces/{workspace_id}` 路径、权限及乐观版本控制保持。

context 新增可选字段：market(stocks/cex/onchain)、chain_id(正整数字符串)、contract_address(EVM 0x地址)、wallet_id、context_version。链上身份必须属于onchain市场且asset_class=onchain，不能用链上偏好声明LIVE。

layout 新增 panel_count(1/2/4)、focused_panel、panels(最多4项)。每个panel包含 panel_id、function_code、locked、context。拒绝重复/越界panel_id及focus；对全局和每个面板的账户/钱包分别校验用户归属。偏好保存不授予执行权限，响应 execution_authorized=false。复用已有JSON存储列，无新增数据库列。

默认CORS新增 localhost:8850 和127.0.0.1:8850；不使用通配符，不关闭认证。

## 运行边界

- 新终端业务面板共用父页面的内存会话客户端；不向子面板提供Bearer凭据读取接口。旧版独立启动时继续使用原会话逻辑。
- 会话取消、401与并发登录保持新会话不被旧响应覆盖；会话标识用于Paper/Ace请求过期检查。
- 分屏支持当前会话内锁定研究上下文。锁定快照与面板布局已接入本机/服务端保存恢复UI；完整故障与多屏恢复验收继续。
- 新终端内图表禁用断线自动演示K线回退；旧版默认演示行为保留。公开CEX行情可直接使用已有适配器，股票行情未连通时显示不可用。
- AI动作打开已有研究面板并预填问题，不自动发送模型请求。真实模型、任务队列和端到端研究交易闭环尚未验证。

## 已有证据

- Node整合测试12项通过：市场隔离、合约校验、恢复只读、认证/401、登录竞态、同源会话桥接。
- 原前端55组模型检查通过；新功能包与旧版生产构建通过，构建仍有大bundle提示。
- 隔离SQLite/TestClient下，工作区/配置/权限/认证/手动订单/Paper原子执行/Ace相关117测试通过，1条依赖弃用提示。
- 浏览器实际打开旧图表、脚本编辑器和公开盘口；四分屏放入业务图表，锁定BTC后切全局股票，锁定面板仍保持BTC。

这些证据不能证明949个静态控件已全部迁移验收、真实账户/模型可用、Web3交易或完整Paper闭环通过。

## 工作区持久化后续增量

新增 GET `/api/v2/workspaces/session/context`：沿用read权限和认证中间件，返回user_id/role/auth_mode/execution_authorized=false，不返回凭据。前端仅在服务端明确local模式时使用本地命名空间；managed模式仍需登录。

WorkspaceLayout增加market_contexts（最多3个、市场唯一、所有账户与钱包逐个校验归属）、split_columns/split_rows（0.2–0.8）；WorkspacePanel增加terminal_symbol用于保留原终端分析标的。仍使用已有JSON列，无数据库列迁移。

`terminal-ui/integration/workspace-state.mjs` 负责受限序列化和版本转换，文件上限512KB，未知函数、重复面板锁、无效链/周期等拒绝。`workspace-controls.mjs` 提供自动保存、恢复前备份、导入导出、服务端乐观版本保存与读取。恢复不恢复凭据或执行权限；读取期间本机变化/身份变化拒绝覆盖；409后要求先读取。

受控浏览器证明：MSFT/30分图表选择回传全局；锁定后全局CEX独立，刷新仍恢复。临时SQLite原生HTTP保存/读取版本1成功并写入审计；独立请求更新版本2/SOL后，旧页面409且未覆盖，重复保存也被要求先读取。fixture仅工作区路由，已停止；不计真实业务E2E。


## 2026-11-05 各市场完整布局

layout新增可选market_workspaces，最多3个唯一市场，每项4个面板槽、焦点/比例/主功能及最多300个锁；隐藏身份也逐项校验，JSON存储不增加列。旧文件兼容、只读恢复、CAS与审计保持。详见[各市场布局验收](TERMINAL_MARKET_LAYOUTS_2026_11_05.md)。
