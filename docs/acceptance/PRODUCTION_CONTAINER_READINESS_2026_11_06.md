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
