# 2026-11-15 完整 UI 预览快照

用户要求先推送完整版本，包含模拟数据以便查看效果。

- 新版入口：`terminal-ui/index.html`；本机 `http://127.0.0.1:8851/index.html?lay=1#R038`。
- 模拟数据：`src/demo-page-data.js`、`src/demo-strategy-model.js`、`src/demo-workspace.jsx`、`backend/data/demo_csv/`，均随源码提交。页面内“功能演示 · 模拟数据”或顶部“通用策略 / 页面演示”进入。
- 公开构建：`npm ci` 后 `npm run build:public`，产物 `dist/` 以新版终端为首页；旧独立页留在 `legacy/`。构建产物按仓库规则忽略，可由源码复现。
- 验证：65模型脚本0失败、交互审计通过、公开构建通过、源码凭据模式扫描通过。
- 边界：预览版本，完整视觉/业务验收未完成；真实AI凭据稍后配置；实盘保持关闭。没有把本机凭据、业务数据库或私人账户数据作为模拟数据提交。
