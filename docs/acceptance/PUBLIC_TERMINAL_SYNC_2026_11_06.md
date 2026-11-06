# 新终端公开同步 — 2026-11-06

公开网站：https://haipi001.github.io/ai-trading-assistant/

terminal-ui 为公开站点根入口，旧 React 工作台保留在 legacy/。源目录纳入同一仓库，构建产物不提交。build:public 生成父页面后端 meta 与嵌入功能同一 HTTPS API 地址；旧版数据导出入口相对指向 legacy/。黑白主题和权限状态保留。Live 关闭。

已验证：公开地址匿名 HTTP 200（更新前版本）；新公开构建成功；终端49测试、55模型脚本、迁移升级/回退/元数据检查通过。gitleaks八项原始命中已逐项验证为六个SHA256源文件摘要与两个受控幂等UUID，用精确fingerprint记录，不屏蔽其他文件或规则。项目secret_scan通过。

后端全量回归首次发现mcp2不再提供FastMCP；当前实现使用v1接口，依赖约束改为mcp>=1.0.0,<2，全量复跑938 passed（90.67秒）。生产Render健康请求25秒内未返回，不能宣称线上后端适配已部署或可用。此快照为开发整合版本，完整逐页AI和股票/CEX页面闭环尚未全部验收。

公开构建本机HTTP验证：入口meta为生产HTTPS API、主页公开链接存在、父页面API模块/嵌入入口/嵌入assets/legacy入口均HTTP200。CUA浏览器两次连接超时，尚无本次公开构建视觉验收截图。共享fixture改为显式user_id参数，Stage5-11测试保留human-user，Paper测试保留成交所有者；初始937passed/1failed已修复并全量938passed。

CEX模拟验收环境修复：复用mock导入的唯一BTC/GLOBAL/CEX/USD身份，独立CEX Paper账户与风险预算；不伪装成Binance行情。通过真实数据目录晋级及报告评估生成研究材料，五门禁->独立审批->Paper成交->日志/待复盘HTTP验证通过，证据CEX_RESEARCH_PAPER_HTTP_2026_11_06.json。受控来源，不代表外部行情、真实账户或页面闭环验收。
