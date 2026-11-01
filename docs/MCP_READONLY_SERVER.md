# MCP 只读工具服务（Phase 29）

把终端的**只读**能力暴露为 MCP 工具（stdio），供外部 Agent（Claude Desktop / Claude Code / 任意 MCP 客户端）"查看"你的账本。

## 安全边界（靠结构保证，不靠口头承诺）

- 服务器**不暴露任何**创建、修改、审批、执行、晋升、签名、转账能力——想绕过决策门也没有可调用的东西。
- 每个工具结果都带 `execution_available: false` 和 `review_only: true`。
- 回归测试（`tests/test_mcp_readonly.py`）钉死三层保证：
  1. 工具名不含执行类词汇（create/approve/execute/order/trade/buy/sell/promote/sign/transfer/withdraw）；
  2. 服务器源码不引用执行/审批服务模块，不出现任何写操作调用；
  3. 功能结果必须带 review-only 标记。

## 工具列表（8 个，全部只读）

| 工具 | 说明 |
|---|---|
| `portfolio_snapshot` | 当前组合总值、现金、配置分布 |
| `list_theses` | 投资论点列表（理由/驱动/失效条件/容忍度/信心） |
| `thesis_delta` | 自上次复查以来世界变了什么（价格 vs 容忍度、新 SEC/新闻/宏观/催化剂；feed 缺失如实报告） |
| `portfolio_risk_latest` | 最新时序风险分析（波动/VaR/回撤预算/相关性/压测）；没跑过返回 `not_run` |
| `signal_quality_report` | 信号质量 vs 零技能基线（真实前向收益） |
| `data_trust_report` | 本地数据对给定决策范围是否新鲜可信（fail-closed） |
| `plan_pipeline_status` | 计划管道各草稿的风险/行为/审批/执行状态（只能看，推不动） |
| `list_backtest_results` | 最近回测运行的指标与基准对比 |

## 安装与运行

```bash
cd backend
.venv/bin/python3 -m pip install -e '.[mcp]'   # 或: pip install "mcp>=1.0.0"
.venv/bin/python3 -m app.mcp_readonly.server    # stdio 模式
```

## 注册到 Claude Code

```bash
claude mcp add trading-os-readonly -- \
  /绝对路径/backend/.venv/bin/python3 -m app.mcp_readonly.server
```

（需在 `backend` 目录作为 cwd，或给 python 加 `PYTHONPATH=/绝对路径/backend`；数据库连接沿用 backend/.env 的 `DATABASE_URL`。）

## 注册到 Claude Desktop

`claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "trading-os-readonly": {
      "command": "/绝对路径/backend/.venv/bin/python3",
      "args": ["-m", "app.mcp_readonly.server"],
      "cwd": "/绝对路径/backend"
    }
  }
}
```

## 验证记录

- 4 个安全/功能回归测试通过（全套 374 passed）。
- 通过真实 stdio MCP 客户端对真实 Postgres 验证 8/8 工具：组合快照返回真实总值；论点列表返回真实 Thesis；风险返回 VALID/年化波动 39.98%；数据信任如实返回 `blocked`（fail-closed）；thesis_delta 正确亮 `no_local_candles`。
