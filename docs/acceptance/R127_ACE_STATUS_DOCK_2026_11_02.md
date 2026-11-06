# r127 Ace 状态工作区增量验收 · 2026-11-02

整体113任务目标继续 active。本增量保留原行情右栏、研究对话/设置与演示策略工具，接入 Chat / Team / Tasks / Actions 四视图。

## 实现与边界

- GET /api/v2/agent/tasks 读取当前用户既有 AgentRun/ScheduledJob；Team 仅展示存档角色状态，不声称驻留团队或后台执行。返回受限DTO，不暴露原始输入输出、错误正文、调度目标或密钥配置。
- GET /api/v2/agent/actions 只在草稿、意图、账户均属于当前用户时生成订单通知，显示存档门禁/阻止原因和真实绑定证据。历史报告通过草稿绑定的 RESEARCH_GATE 查找，不能误取最新其他门禁。读取不重跑风控，不生成审批或成交。
- PATCH 通知个人状态支持 OPEN / ACKNOWLEDGED / DISMISSED，绑定源摘要和乐观版本，冲突409，数据变化重新打开。迁移0026持久化个人状态与审计。只读用户可管理自己的通知，但原交易审批仍受角色权限约束。
- 审查按钮只导航到支持映射的原 Paper 限价票据，恢复精确账户、资产、草稿、数量和价格；不支持的模式/市场/平台拒绝猜测。恢复历史报告方式时使用精确绑定研究门，手动凭据仍使用手动方式。
- 原研究设置/输入/发送入口保留，不自动发送。原演示Agent/Chat与策略卡收进可展开的演示工具，数值标记为非经验证胜率。没有替换原研究能力或删掉控件。
- 状态视图每15秒读取一次；切换会话清除数据并阻止迟到响应覆盖，变更请求避免被旧GET覆盖；失败清空旧卡并显示不可用。

这是既有记录适配器，不是完整官方 AgentActionCard schema，也没有实现原生AgentTask队列、取消、SSE、预算执行、多角色持续引擎或跨来源通知。默认40条，接口最多100条并返回has_more；UI分页待做。存档通过不能代替下一次真实审批/执行的复核。

## 自动验证

- 后端完整906 passed，79.39秒；11项新增Ace接口测试覆盖私有状态/归属、只读角色、伪造命名空间、版本/源变化冲突、通知不审批、阻止原因和精确报告绑定。1个既有Starlette/httpx弃用警告。
- 55个前端模型脚本全部通过；原UI保留守卫845控件、三项导航契约通过。交互审计622按钮/622处理器，254控件/254处理器，301列表key；10导航、59频道保留。
- Vite构建3.40秒通过；存在大chunk提示，未做性能SLO认证。
- SQLite单head0026、新建/模型一致性/降级/再升级检查通过。实际用户数据库未升级，PostgreSQL与真实OIDC未验证。

## 隔离浏览器与数据库核对

本地Vite3002配合临时SQLite/后端8001。初次夹具default actor与seed账户不一致，严格归属接口正确隐藏记录；只将测试服务BETA_DEFAULT_USER_ID对齐seed实际default-user，未改写账户/订单所有权。

Tasks/Team中的失败角色是明确标记的测试夹具，没有调用模型。四视图、原研究设置/输入/发送、原演示控件均在浏览器观察。AAPL通知确认后刷新仍为ACKNOWLEDGED，订单保持pending / not_executable；SQL核对目标Approval=0、Execution=0，总Execution=1为已有seed成交，SQLite integrity=ok。

审查跳转在原票据恢复AAPL/NASDAQ/USD，数量2、限价225.12、原研究报告与同一pending草稿，执行按钮禁用。未点击批准或执行。后端正常关闭后刷新显示不可用并移除旧卡，未伪装成空列表或完成。临时页关闭，行情恢复SOL/币安1h和原订单表侧栏；Vite保留。

证据截图：

- [通知确认仍待审批](../../output/r127-ace-status-20261102/acknowledged-not-approved.png)
- [原票据恢复](../../output/r127-ace-status-20261102/paper-review-handoff.png)
- [后端离线](../../output/r127-ace-status-20261102/offline-state.png)

[结果、SQL事实与实现SHA256](R127_ACE_STATUS_DOCK_RESULTS_2026_11_02.json)。没有真实下单、付费模型调用、发布或Git同步。本增量不能认定整体规划完成。
