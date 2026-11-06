# 真实容器部署检查 — 2026-11-06

状态：进行中，不表示Render生产可用。

线上诊断：现有API请求已完成HTTPS TLS握手并发出GET，但10秒未收到HTTP响应。GitHub部署记录只有Pages，不能据此推断Render是否已部署。Render集成已发现并提供添加/连接入口；查询尚未成功返回服务/工作区，不能声称已连接或有云端服务日志。

本机Docker此前未运行，使用已安装Docker Desktop CLI启动后确认engine29.2.1。新增scripts/smoke-production-container.py，构建实际backend/Dockerfile，使用隔离网络、随机本机API端口、临时PostgreSQL16/Redis7和临时凭据文件。生产模式+managed_auth=true，Live和外部模型关闭。通过真实alembic启动路径检查健康、身份伪造拒绝、GitHub站点CORS、数据库停止时503和重启恢复、零订单与成交。结束后清理容器和网络。

运行方式：`python3 scripts/smoke-production-container.py --output /tmp/terminal-production-smoke.json`。镜像可缓存，后续`--skip-build`仅用于明确复用同一已验证镜像，不代表验证了新源码。

本轮已通过Python编译检查。镜像构建与PostgreSQL/Redis下载仍在进行；尚无运行成功证明，不计为生产/端到端验收通过。没有修改线上服务、实际账户或实盘权限。

真实PostgreSQL16检查发现旧user_accounts同时持有唯一索引和旧唯一约束，alembic check报告模型差异。新增0027迁移，仅PostgreSQL生效，先验证ix_user_accounts_user_id唯一索引列精确匹配，再移除默认命名的旧冗余约束；无法证明唯一索引存在时直接失败。downgrade恢复旧约束。未修改历史迁移，未放宽用户唯一性。

新增迁移已在临时PostgreSQL16实际执行upgrade/check/downgrade -1/upgrade/check通过，实际插入重复user_id仍被ix_user_accounts_user_id拒绝；临时数据库容器已删除。SQLite fresh升级、元数据、回退/重升也通过。证据POSTGRES_PARITY_0027_2026_11_06.json。本轮仍未取得云端Render日志，不能将此差异认定为线上超时原因。

当前主容器构建在新增0027之前已开始；其镜像及内存脚本仍属此前基线，后续必须用修复后的源重新构建再验收，不能将两份不同版本证据合并宣称同一生产镜像通过。

补充真实PostgreSQL负向验证：在0026状态删除唯一索引，升级0027被明确拒绝，旧唯一约束仍保留；恢复唯一索引后升级和模型一致性检查通过。证据POSTGRES_IDENTITY_GUARD_2026_11_06.json。21项租户隔离、工作区和Paper复盘回归通过。CI新增隔离PostgreSQL16迁移任务，避免今后仅依赖SQLite迁移检查；该新增CI任务尚未在云端运行。

本机基线构建会话83543最终exit1：files.pythonhosted.org包下载ReadTimeout，尚未启动应用；旧证据checks为空，不计通过。实际原进程已停止后才准备新构建，未因观察超时重启。Dockerfile增加PIP_DEFAULT_TIMEOUT=120/PIP_RETRIES=5，仅提高下载容错，不跳过TLS或依赖检查。

新CI production-container任务使用干净checkout构建实际镜像，production模式连接隔离PostgreSQL16/Redis7，验证non-root、真实迁移及alembic check、无会话/伪造身份拒绝、公开站点CORS、Live/外部模型关闭、数据库故障503/恢复、零订单。脚本记录Git SHA、后端源码摘要、镜像ID，并在失败时保留经临时凭据精确脱敏的应用日志，再清理容器网络。该任务尚待首次云端实际结果；不能据脚本存在宣称通过。

CI eb7c4fd实际新镜像已通过非root、PostgreSQL完整迁移与ready、容器内alembic check、匿名/伪造用户401。随后验收驱动在CORS OPTIONS标准纯文本OK响应上抛JSONDecodeError，失败是驱动无条件JSON解析造成，不能算整套通过。已按响应Content-Type解析：JSON仍严格校验，纯文本按UTF8读取，不放宽CORS状态/来源断言。下一次CI继续验证完整流程。

0330b0b实际完整容器CI已通过：九项检查全部passed，源码摘要和镜像ID冻结于PRODUCTION_CONTAINER_0330B0B_2026_11_06.json。该版本已同步main，证明镜像运行路径，不是Render或真实身份提供商验收。

继续补正向认证：在同一隔离Docker网络中使用明确标注的受控userinfo服务，不patch后端认证代码。以两个viewer测试身份实际HTTP登录，检查服务器签发会话、工作区各自持久化、伪造用户头不串租户、过时版本409、退出后令牌401、另一会话仍有效及篡改令牌拒绝。访问令牌和会话令牌仅临时内存/0600临时文件，日志额外精确脱敏并自动清理。尚待新CI实测；不代表真实OIDC/TLS提供商、真实账户或产品全流程验收。
