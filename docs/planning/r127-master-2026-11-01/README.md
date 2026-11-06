# AI Trading OS — r127 原 UI 保留式开发总工程包

版本：2026-11-01 · 计划基线 commit `9e774c232992bda309fdd22099114b5303a74f10` · 交付形态：**规划、API 契约、任务、验收用例及 Codex 提示词**；**没有修改仓库、没有部署、没有开启实盘**。

## 不可改变的最高原则

> **PRESERVE THE TERMINAL · UPGRADE THE INTELLIGENCE · COMPLETE THE EXECUTION**
>
> 保留现有 r127 全部页面、导航、图表、策略及操作；围绕同一 UI 增强 Agent 实时参与、真实交易、后台工作流与专业用户体验。不准用简陋概念图替换现有 UI，不准为了重构删功能。

目标产品：**AI Trading OS — Agent-Native Professional Trading Terminal**（“Agent 的彭博”是长期愿景，不是对已有市场数据覆盖和基础设施能力的实证声称）。专业交易平台是产品本体，AI Agent 是贯穿各工作区的持续协作与行动层。支持股票/ETF、CEX 加密资产、Web3 研究和阶段性的受控链上动作。可在没有 AI 的情况下完整手动交易；有 AI 时提高研究、交易管理和风险处置效率。

## 文件导航（顺序即推荐阅读顺序）

| 文件 | 内容 |
|---|---|
| `docs/00_PRODUCT_CHARTER.md` | 最终定位、产品原则、模式边界与取舍 |
| `docs/01_REPOSITORY_BASELINE.md` | 已验证代码版本、真实实现、风险、仓库路径与哪些未知 |
| `docs/02_UI_PRESERVATION_AND_NAV.md` | r127 导航/页面/UI 不变量、五张截图验收锚点与兼容要求 |
| `docs/03_UX_AGENT_COCKPIT.md` | Ace Agent、图表联动、策略、订单、用户旅程、交互状态 |
| `docs/04_ARCHITECTURE.md` | 单体优先架构、后端任务、状态、推送、数据源、可扩展性 |
| `docs/05_MULTI_AGENT.md` | Agent 角色/工具、事件驱动、资源预算、审计、AI Evals |
| `docs/06_LIVE_TRADING.md` | CEX/股票真实交易、状态机、风险、交易所对账、故障演练 |
| `docs/07_DATA_AND_MARKETS.md` | 行情、新闻、标准化、可信快照、股票与链上数据 |
| `docs/08_API_AND_EVENTS.md` | 现有 API 与拟新增 API/事件/WebSocket 数据契约 |
| `docs/09_ROADMAP.md` | T0–T7 里程碑、依赖、版本门禁与粗略人周 |
| `docs/10_ACCEPTANCE.md` | 5 屏基线、功能零丢失、操作闭环、CI、灰度、实盘验收 |
| `docs/11_OPEN_SOURCE_MAP.md` | CCXT/ib_async/LangGraph 等项目的复用与许可证边界 |
| `docs/12_CODEX_MASTER_PROMPT.md` | 可直接提供给 Codex 的完整主提示词 |
| `docs/13_FIRST_4_SPRINTS.md` | 第一个月可立即执行的任务拆分与 PR 顺序 |
| `docs/14_DECISION_LOG.md` | 历史决策与这次修改的定位差异 |
| `docs/15_DEPLOYMENT_AND_RUNBOOK.md` | 环境、部署、恢复、紧急停止、授权、审计 |
| `tasks/development_tasks.csv` | 可导入任务系统的开发任务：ID、前置、UI、API、风险与验收 |
| `tasks/ui_coverage.csv` | 现有页面/频道/策略类别到功能、Agent 与验收的逐项矩阵 |
| `visual-baseline/*.png` | 用户提供的五张**当前真实 UI 截图**，用于后续视觉保真和浏览器比对，不是 AI 生成设计图 |
| `tasks/api_matrix.csv` | 现有接口与新接口的契约/权限/结果映射 |
| `schemas/*.json` | Agent 上下文、行动卡、交易提案、订单事件的草案 JSON Schema |
| `examples/acceptance_scenarios.md` | 用户可走通的端到端故事、测试数据与失败条件 |

## 第一批不能跳过的事实与阻塞

1. r127 源码位于 `src/`；`src/main.jsx` 包含 `NAV`（首页/行情/快讯/要闻/策略/链上/资产/授权/数据/更多）和各栏目 `META`；正式本地启动端口记录为 `3002`。**旧 Next.js/其他 UI 副本不作为替代**。
2. FastAPI 已合并至 `backend/`，但是 `backend/app/services/live_execution.py` 仍显式包含 `real_live_execution_not_implemented`。禁止删除此保护以假装完成实盘。
3. `backend/render.yaml` 当前 `MANAGED_AUTH_REQUIRED=false`；生产部署需要先验证完整身份授权，并排除风控/交易权限绕过。
4. 最新 Github Actions 前后端回归 CI 失败：pytest 收集 `tests/test_mcp_readonly.py` 时没有安装可选包 `mcp`；修复 `backend[dev,mcp]` 只是首步，还需要执行整个回归测试链。
5. 已有公开行情/资讯/自带 Key AI/只读账户连接与后端模拟执行的代码；**不能因截图的暂时不可用而称它们全部没开发**，也不能将源码存在或夹具测试误写成实盘验收通过。

## 三种使用情境必须严格区分

- **DEMO**：生成/导入的演示数据，显著标记，不能被 AI 当作实际行情证明。
- **PAPER**：接入真实行情但模拟成交；持仓、订单与真实账户完全隔离。
- **LIVE**：真实券商/交易所订单；仅在生产认证、用户明确批准、适配器、账户风控与紧急停机全部通过后解锁。每个账号的开关单独授权，默认关闭。**LLM 无任何直接调用下单 API 的权限**。

## 给 Codex 的入口

让 Codex 首先阅读 `docs/12_CODEX_MASTER_PROMPT.md`，依序执行 `docs/13_FIRST_4_SPRINTS.md` 的 P0/T0。每个 PR 要更新 UI 功能覆盖矩阵、API 文档、测试及 `VERSION.md`。在未经授权的情况下不修改生产设置、开启交易或调用真实买卖接口。

## 关于估算

所有工期以有经验开发者为参考，附带明确前置与测试门禁；并非保证可在期限内实盘上线。券商合规/账户 API 授权、数据许可和稳定性测试可能大幅增加工作量。
