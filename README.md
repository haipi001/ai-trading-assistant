# AI 交易助手

> 面向个人投资者的 AI 原生市场工作台：把行情、研究、策略记忆、模拟执行与复盘放进同一个界面。

[在线体验](https://haipi001.github.io/ai-trading-assistant/) · [部署状态](https://github.com/haipi001/ai-trading-assistant/actions/workflows/deploy-pages.yml)

![Frontend](https://img.shields.io/badge/frontend-React%2019-176b5b)
![Build](https://img.shields.io/badge/build-Vite%206-a34d19)
![Deploy](https://img.shields.io/badge/deploy-GitHub%20Pages-222)

## 产品是什么

AI 交易助手服务于需要同时观察 Web3 与股票市场的个人投资者。它不仅展示价格，还帮助用户持续记录：

- 为什么关注一个标的；
- 准备在什么条件下行动；
- 哪些变化会让原判断失效；
- 策略在模拟执行后表现如何；
- 下一次决策应该保留或修正什么。

产品希望建立一条清晰的个人研究闭环：

```text
市场观察 → 研究证据 → 投资假设 → 风险检查 → 策略草稿 → 模拟执行 → 交易复盘
```

## 核心能力

### Web3 与股票统一市场

首页可以在 Web3 与股票市场之间切换，并显示各自的市场概览、条件筛选、排行榜、事件日历、板块热力和财报雷达。行情工作台提供 K 线、深度、资金流、合约数据、自选列表和图表工具。

### AI 辅助研究

AI 智搜可以围绕当前标的整理行情、财报、指标、新闻和宏观上下文，帮助用户提炼触发条件与风险缺口。AI 只辅助分析，不替代人的最终判断。

### 策略记忆与双向关联

「我的策略」包含本地交易笔记、标签系统和双向关系图。笔记可根据共同标签与显式链接自动建立关联，并通过可拖动圆形气泡显示知识网络。

### 模拟策略工作台

产品覆盖套利、DCA、AI 网格、指标策略、CEX/DEX 跟单、主力追踪和游资追踪等工作区。交易相关入口默认停留在本地配置、预览或模拟状态。

### 本地资产与工作区状态

自选、笔记、策略草稿、图表布局、预警、模拟订单和偏好设置保存在浏览器本地，刷新页面后可以继续使用。

## 安全边界

- 不保存私钥、助记词或提现权限凭据。
- 不自动批准或提交真实订单。
- 不执行钱包签名、链上交换或自动提现。
- 当前公开站点以本地模拟数据和浏览器存储为主。
- 前端已预留 `VITE_API_BASE_URL`，但公开环境尚未配置后端服务。

## 当前架构

```text
React 19 + Vite 6
├── 市场与图表工作台
├── AI 智搜与功能面板
├── 策略笔记和标签关系图
├── 本地模拟订单与策略状态
└── 可选 FastAPI 数据接口
```

GitHub Pages 只托管静态前端。仓库内当前不包含可公开部署的 FastAPI 后端、数据库或私有交易所连接配置。

## 本地启动

```bash
npm install
npm run dev
```

默认地址：<http://localhost:5173/>

如需连接兼容后端：

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## 验证

```bash
npm run test:interactions
npm run build
```

交互审计会检查所有按钮和表单控件是否拥有实际处理逻辑，并核对一级页面、顶部频道、工具入口与关键工作流契约。

## 部署

推送到 `main` 后，[GitHub Actions](https://github.com/haipi001/ai-trading-assistant/actions/workflows/deploy-pages.yml) 会自动执行依赖安装、交互审计、生产构建和 GitHub Pages 发布。

公开地址：<https://haipi001.github.io/ai-trading-assistant/>

## 项目状态

当前版本是可交互的前端产品原型，不代表已经接入真实行情、账户、交易所或生产后端。接入真实服务前，需要单独部署 API、数据库与缓存，并配置 HTTPS、CORS、认证、密钥管理、监控和数据保留策略。
