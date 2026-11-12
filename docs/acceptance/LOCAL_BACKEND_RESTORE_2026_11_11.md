# 本地产品后端恢复核验

2026-11-11。使用现有 PostgreSQL，不创建替代数据库，不 seed。

- 备份：交易系统/backups/backend-before-schema-20261111-234754.dump，3129199 bytes，权限0600，pg_restore --list成功；未做恢复演练。
- Alembic从20260717_0022顺序升级到20261106_0027，事务成功。
- 原产品启动脚本启动8001，PID89455；scheduler由脚本禁用，Live与外部模型调用配置关闭，A0_READ_ONLY。
- /health、/health/status、/openapi.json HTTP200。
- /api/v2/workspaces/session/context HTTP200。
- /daily-use/workspace-status HTTP200。
- /api/v2/workspaces/session/options HTTP413：workspace identity list exceeds selection limit。该接口当前一次最多500个自有账户/活跃钱包；下一步需做账户选择分页/搜索，不能删旧记录或静默截断。
- 前端8850仍监听。未执行浏览器联调、真实账户访问、模型调用或交易。恢复服务不等于可交付。

## 账户分页修复

后端账户与钱包按ID排序，每页500条，返回next_offset；前端逐页校验所有权、重复ID与单调游标，全部加载成功才发布选择列表。用户切换/刷新使旧请求失效；失败不恢复旧校验。保留所有历史记录。

当前实际本地HTTP核验：2页，共864账户、0钱包，接口200，原413已消除。后台PID89637。后端工作区测试14通过（含503账户边界与负offset）；前端103通过。尚无浏览器视觉验收；账户选择仍为原select，尚未加入名称搜索；并发增删身份时需重新刷新，未提供跨页数据库快照。

## 账户名称搜索

顶部新增搜索账户/钱包，支持名称、ID、模式，候选先按兼容市场与链过滤。过滤保留当前选项，不能因搜索自动切换账户。切换市场、链或用户清除搜索条件。外部terminal-ui与仓库副本同步。前端104测试通过（含保留选择、大小写、越市场选择不注入）；语法检查通过。CUA getState 10秒超时并完成工具收尾，未获得浏览器操作/视觉证据。
