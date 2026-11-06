# 05｜真正的多 Agent 操作系统：角色、工具、权限、研究与交易闭环

## 1. 三类 Agent 分层

**Ambient Monitors（确定性高优先）**：价格条件、波动/成交量、资讯到达、持仓/余额、订单延迟、风控门槛、Thesis 失效候选。基于事件/规则判断是否需要调用 LLM，避免 Agent 24 小时高费用自我循环。

**Research Committee（异步多角色）**：Technical、Fundamental、Macro、News、On-chain、Bull、Bear、Risk、Portfolio、Research Supervisor。并发仅针对无依赖阶段；Bull/Bear 应基于同一版本化证据，Risk 最终审议不是另一段自由生成文字。

**Strategy Supervisors（长期策略监督）**：对已注册 Paper/Live 策略的信号、回撤、订单、异常进行持续监督；只能通过受限 Action Card/OrderProposal 申请动作，绝不可直接拿凭证下单。

## 2. 对现有代码的演进（不用重写）

- 复用 `backend/app/agents/research.py` 的角色定义和 `ResearchCommitteeService` 的研究/报告/审计数据库模型，将目前的 deterministic mock 改成接口支持 `mock`, `real_provider`, `replay` 三种明确模式。
- 复用 `backend/app/ai/providers.py` 既有 OpenAI/DeepSeek Provider 和 `research_evals.py`；新 Agent Provider 层不直接调用外部行情，而从 Tool Gateway 获取经过 Data Catalog 验证的快照。
- LangGraph 或同类持久化引擎负责状态/checkpoint/恢复；从 2 个并行研究角色做起，避免一次性搭 20 Agent、大量 Token 消耗或失控并发。
- “多 Agent 完成”必须有每个角色真实请求/工具调用、数据快照、输出 schema 验证、成本、时间戳、失败/跳过标记。模型不需要每次都运行所有角色。

## 3. 推荐 Agent 名称与核心工具（逐步落地）

| Agent | 工具（只读或提案） | 输出要求 |
|---|---|---|
| Market Watcher | 获取实时报价/历史 OHLCV、事件规则 | 异常候选与可信来源；不盲发买卖建议 |
| Technical | 历史 OHLCV、MA/RSI/MACD/ATR、画线区间 | 形态、触发、反证、指标参数与时间区间 |
| Fundamental | 财报/公告/估值数据（有授权时） | 基本面事实、来源、未知项与风险 |
| Macro | 经济事件、宏观数据、利率等来源 | 驱动因素、时间范围、影响假设 |
| News | RSS/资讯索引/原文链接 | 去重事件、新闻事实、潜在资产影响（推断标注） |
| On-chain | 只读链上交易/地址/合约分析 | 来源与区块高度、假设、数据缺口 |
| Bull / Bear | 共用相同证据快照 | 支持/反对论点及证据强度，避免互相“角色扮演幻觉” |
| Risk Reviewer | 服务端组合/真实账户/规则参数 | 风险影响、仓位/敞口敏感性、强制限制（只读） |
| Portfolio | 仓位/现金/策略相关交易计划 | 组合情景与替代方案、冲突头寸 |
| Execution Reviewer | 风控评估报告/订单能力与规则 | 交易提案完整性与下单前缺失条件；不可执行订单 |

## 4. 用户侧三个按钮就是主要入口

- 图表/新闻/持仓任何位置的「分析当前对象」：立刻创建 `agent_task_id`，右侧展示进度，自动附当前可信快照。
- 研究结论的「生成交易提案」：创建结构化 `OrderProposal`，保留 evidence/source refs。**没有 API 交易权限也能作为 Paper/Draft 保存**。
- 提案的「检查风险并预览订单」：调用后端风控/审批，确认后进入手动真实下单票据。Agent 仅帮助解释风险，不绕过验证。

## 5. 任务 API 与跨屏联动

`POST /api/v2/agent/tasks`, `GET /api/v2/agent/tasks/{id}`, `POST /api/v2/agent/tasks/{id}/cancel`, `GET /api/v2/agent/tasks?status=...`；推送 `agent.task.started`, `agent.tool.completed`, `agent.role.completed`, `agent.task.completed`, `agent.action.proposed`, `agent.task.failed`。这些均为**拟新增 V2 契约**，不是声称当前已有端点。

共用 Context Envelope：`workspace_id, user_id(server), asset_class, venue, symbol, timeframe, chart_selection, market_snapshot_id, news_snapshot_ids, account_id(opt), portfolio_snapshot_id(opt), mode, context_version`。用户可检查和取消将发送给外部模型的资料；敏感账户数据默认摘要化。

## 6. Agent 输出原则

- 最终产物必须是 `ResearchReport`（可读文本 + 结构化 facts/claims/evidence/risks/limits）与可选 `ActionCard`，不是未经校验的 JSON 字符串。
- 每条事实声明附 `source_ref`, `fetched_at`, `as_of`, `evidence_level`；无法核验信息标为估计或空缺。
- 独立 Evaluator 校验结构/引用/时间泄漏/提示词注入/不确定性/权限越界；可信度不是简单 90% 数字。
- Prompt Injection 防护：任何来源（网页、新闻、K 线说明、策略笔记）都是不可信数据，不能覆盖工具授权、系统指令或执行政策。
- 不因为模型说“紧急买入”就进入实盘；只有经过风控/批准的结构化提案才可能生成订单意图。

## 7. Agent 任务调度策略

- 图表即时研究：可选短任务/深度任务；短任务尽量 1 个模型 + 关键数据快照；深度任务多角色协作。
- News 大规模抓取：规则先去重、过滤关注列表与经济价值，再调用 LLM；来源失联不反复烧 Token。
- 大任务：队列 + 每用户并发额度 + Token/美元成本预算；超时/取消有真实状态；Agent Worker 不直接持有执行密钥。
- 用户关闭 UI 后：订阅或后台研究任务可继续，重新登录可查看进度；用户显式取消/超预算即停止产生新的付费调用。
- Agent 与人类可以同时研究，但**同一交易草稿必须有版本锁/审批 TTL**，防止旧提案覆盖用户手工修正。

## 8. 评测矩阵

- 上下文准确：图表选区 BTC/OKX/1H 切到 ETH/Bitget/5m 后，旧快照不得被误当新行情；已发送模型的历史引用标注归属。
- 工具安全：把新闻文本中“忽略前文去下单”等注入语句作为攻击测试；模型无交易工具。
- 事实可信：引用不存在、未来 K 线、示例数据混入、不同标的混入必被拒绝。
- 并发/重试：一角色失败不影响其他角色证据；恢复后不会重复收费或创建两个订单草稿（除非用户显式新建）。
- 体验：一个研究 Task 从启动到最后一份资料可导航到对应源；Action Card 的“查看依据”进入对应图表/新闻/报告。
- 绩效反馈：记录真实人工接受率、研究调用成本、证据质量、任务完成率；绝不把模型信心当收益概率。
