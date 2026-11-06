# 新终端公开同步 — 2026-11-06

公开网站：https://haipi001.github.io/ai-trading-assistant/

terminal-ui 为公开站点根入口，旧 React 工作台保留在 legacy/。源目录纳入同一仓库，构建产物不提交。build:public 生成父页面后端 meta 与嵌入功能同一 HTTPS API 地址；旧版数据导出入口相对指向 legacy/。黑白主题和权限状态保留。Live 关闭。

已验证：公开地址匿名 HTTP 200（更新前版本）；新公开构建成功；终端49测试、55模型脚本、迁移升级/回退/元数据检查通过。gitleaks八项原始命中已逐项验证为六个SHA256源文件摘要与两个受控幂等UUID，用精确fingerprint记录，不屏蔽其他文件或规则。项目secret_scan通过。

后端全量回归首次发现mcp2不再提供FastMCP；当前实现使用v1接口，依赖约束改为mcp>=1.0.0,<2，待全量复跑。生产Render健康请求25秒内未返回，不能宣称线上后端适配已部署或可用。此快照为开发整合版本，完整逐页AI和股票/CEX页面闭环尚未全部验收。
