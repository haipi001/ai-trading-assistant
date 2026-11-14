# AI Trading Assistant Backend

FastAPI backend maintained alongside the React frontend in the AI Trading Assistant monorepo.

## Safety defaults

- Live trading disabled.
- Live execution disabled and dry-run only.
- Automation restricted to read-only.
- No credentials committed to the repository.
- CORS restricted to the published frontend and local development.

## Local run

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

## Render deployment

`backend/render.yaml` defines the API, Postgres database, and Key Value cache. Select this Blueprint path from the unified repository; its service root is `backend/`. Secrets belong in the deployment platform, never in Git.

### 统一连接与订阅设置

设置默认进入“连接与订阅”，集中访问自定义 RSS/JSON、内置资讯、AI 凭证和后端连接。

- `GET /subscriptions`：当前用户的订阅清单，仅返回凭证是否配置；要求 `readiness:read`。
- `PUT /subscriptions/{id}`：保存名称、`url`、`kind`（rss/json）、`auth`（none/bearer/header）、`header_name`、字符串对象 `params`、`enabled`、`refresh_seconds`；可提交 `api_key` 替换或 `clear_key:true` 清除凭证。要求 `secrets:write`。
- `POST /subscriptions/{id}/test`：手动 GET 已保存来源，检查 RSS 2.0 / JSON 映射并返回规范化消息或报价及条目数；要求 `secrets:write`。记录最近状态和审计事件。

只接受公网 HTTPS 标准443端口；DNS解析后固定连接已验证公网IP，验证TLS域名，拒绝重定向。响应最多2MB，不返回来源原始错误或原始内容。凭证存于后端本机0600文件，不进入配置数据库或浏览器存储。URL不允许查询串，查询参数独立填写，凭证放专用字段。无需数据库迁移，使用现有按用户隔离的 LocalUserConfig。

启用的自定义 RSS 现已并入资讯列表、快讯与资讯侧栏，可在设置选择文章或快讯分类；同一原文URL去重。JSON接口报价在行情图表页“订阅行情”独立展示，配置 `mapping` 中的 root / symbol / price / change / volume / timestamp 字段路径、timestamp_unit（iso/s/ms）、currency、market、venue及可选固定symbol_value。路径以点分隔，根路径指向对象或数组。涨跌幅单位为百分数；未知时间、涨跌幅或成交量保留为空，不生成示例值。

`GET /subscriptions/feed/news` 和 `/subscriptions/feed/quotes` 返回当前用户启用来源及规范化缓存；`POST /subscriptions/{id}/refresh` 使用 readiness:read 权限读取该用户启用来源。服务端按来源配置间隔节流，并用用户/订阅锁合并多面板请求；配置在请求中变化时丢弃旧响应。失败保留上次成功内容、成功时间及独立失败状态。配置列表只返回摘要，不回传缓存正文。

页面可见时自动轮询：RSS最短60秒，JSON最短15秒；页面隐藏/卸载后停止发起新请求，恢复可见后检查到期来源。没有关闭应用后仍运行的后台调度，也没有WebSocket逐笔推送。订阅报价独立显示，不替换K线、不进入订单价格或AI证据。AI服务沿用原有能力，内置资讯继续由原有服务负责。
