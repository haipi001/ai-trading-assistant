# r127：托管交易操作者身份绑定

整体开发目标及T0仍在进行。本轮未改UI、未迁移数据库、未修改运行中的生产配置、未部署推送、未调用真实模型或券商。

## 实现

托管会话中，typed JSON请求的approver_id、engaged_by、disengaged_by由当前已验证会话主体填入。请求若显式指定其他主体，返回403 actor_identity_mismatch；owner/admin也不能冒充他人审批或停机。user_id仍表示资源归属，管理员已有显式跨用户管理能力继续保留，但不会改变实际交易操作者。

该绑定发生在模型验证与业务服务之前，覆盖已声明这些字段的审批、拒绝、Paper/Live骨架、Sandbox和Kill-switch接口。未声明这些字段的模型不注入未知字段；严格请求模型保持兼容。本地非托管模拟模式保持原行为，不能部署成托管身份认证替代。

实际路由测试发现当前FastAPI使用_IncludedRouter包装层，旧代码只检查顶层APIRoute，导致部分业务接口的用户身份注入未命中。现使用可用的iter_route_contexts取得有效路由上下文并匹配请求，再读取原始APIRoute模型；较早版本无该接口时保留直接APIRoute路径。没有用绕过请求模型或全局字符串替换实现绑定。

## 验证

新增13项用例：owner/admin在6类真实业务路由伪造审批人/停机人全部拒绝；operator省略engaged_by后，实际停机记录持久化当前会话主体。

包含既有中间件用例的专项61 passed、1依赖弃用warning、3.19秒。完整回归结果见同名RESULTS JSON。测试使用当前源码、已有Python3.13环境、内存SQLite及测试会话认证替身，不代表实际OIDC服务验证。

## 尚需完成

完整跨用户/跨账户业务审计、管理员跨用户管理授权边界、后台任务/服务调用的显式actor合同、所有非typed-dict入口的审计身份、不可抵赖审计、前端身份/权限可见状态以及真实OIDC端到端仍待完成。此变更不把角色权限或API身份绑定等同于账号交易授权，也不解除实盘门禁。

最终完整后端762 passed、1条Starlette/httpx依赖弃用warning、47.62秒、退出0。secret scan、diff --check及原UI静态守卫通过。
