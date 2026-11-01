# MVP P0 Demo

## 最短启动

1. 启动后端

```bash
cd /Users/lizekai/Documents/交易系统/ai-trading-os/backend
./.venv/bin/uvicorn app.main:app --reload
```

2. 启动前端

```bash
cd /Users/lizekai/Documents/交易系统/ai-trading-os
./scripts/dev_frontend.sh
```

如果 `3000` 端口已经被另一个前端进程占用，脚本会直接退出，避免把正在运行的 `.next` 目录删掉后导致页面变成 `500`。

3. 打开演示地址

- Frontend: `http://localhost:3000`
- Backend docs: `http://localhost:8000/docs`

4. 点击顶栏 `一键 Demo Seed`

也可以直接调用：

```bash
curl -X POST http://localhost:8000/demo/seed
```

## 官方 Demo Flow

固定流程：

1. `data_sources`
   - 展示默认只读连接、真实数据更新时间、以及故意保留的数据质量不足样例。
2. `holdings`
   - 展示默认账户持仓。
   - 明确看到至少一个 `thesis missing` 的阻断样例。
3. `investment_logic`
   - 展示 AAPL 默认 thesis。
4. `decision_gates`
   - 展示 happy path 的通过链路。
   - 同时展示被阻断的 gate 样例。
5. `order_drafts`
   - 选中 pending draft。
   - 先 `Approve`，再 `Paper Fill`。
   - 同页可看到 rejected sample。
6. `trade_journal`
   - 完成 post-trade review。
   - 查看默认 review sample。
7. `monthly_review`
   - 生成当期 monthly review。
   - 查看已存在的 sample review。

## Demo Checklist

- 顶栏 `数据更新时间` 已显示真实时间戳。
- 顶栏 `自动化模式` 来自 `/demo/status`，不是写死文案。
- 顶栏 `全局风险状态` 来自真实 blocker/warning 统计。
- 顶栏 `当前 Workflow` 来自真实 workflow/demo 状态。
- Overview 顶部能看到 `Official Demo Flow`。
- Data Sources 页存在可解释的 `Data Quality Blockers`。
- Holdings 页存在 `Thesis Coverage Blockers`。
- Workflow 页存在 `Blocked Demo Samples`。
- Execution 页同时存在：
  - 1 个 pending approval sample
  - 1 个 rejected sample
  - 1 个 paper-filled / review sample
- Journal 页可以完成 review，随后 Monthly Review 页能生成新 review。

## 验证命令

前端：

```bash
cd /Users/lizekai/Documents/交易系统/ai-trading-os/frontend
./node_modules/.bin/tsc --noEmit
PATH=$PWD/.tools/bin:$PATH ./node_modules/.bin/next build
```

后端：

```bash
cd /Users/lizekai/Documents/交易系统/ai-trading-os/backend
./.venv/bin/pytest
```

最小 smoke：

```bash
cd /Users/lizekai/Documents/交易系统/ai-trading-os
python3 scripts/demo_smoke.py
```

前端 smoke：

```bash
cd /Users/lizekai/Documents/交易系统/ai-trading-os/frontend
npm run smoke:e2e
```

要求本地前端运行在 `127.0.0.1:3000`，后端运行在 `127.0.0.1:8000`。
