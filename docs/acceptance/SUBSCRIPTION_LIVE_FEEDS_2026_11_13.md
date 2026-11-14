# RSS与订阅行情接入（2026-11-13）

- RSS规范化后并入资讯列表、快讯与行情资讯侧栏，保留来源、分类及发布时间，按原文URL去重。
- JSON报价通过可配置字段路径映射到独立订阅行情区；包含symbol、price、change、volume、timestamp、currency、market和venue。缺失字段不补演示值。
- 页面可见时轮询；RSS最低60秒、JSON最低15秒；隐藏时不再发起新请求。服务端按用户/来源节流和合并，配置修订期间返回的旧请求丢弃。失败保留旧缓存并标注。
- 凭证仍存本机0600文件，不进入显示数据；订阅数据仅展示，不接入订单价格或AI证据。K线仍使用已有行情源。

## 验证

`backend/.venv/bin/python -m pytest backend/tests/test_subscriptions.py backend/tests/test_news_feed.py -q`：43 passed。

`node scripts/check-subscription-live.mjs`：合并、去重、来源、过期、失败缓存、URL过滤和排序检查通过。

`npm run build:terminal`：通过，存在原有大chunk提示。

本机8001后端已重启。通过实际API保存了两个免凭证公开来源：PANews RSS快讯（60秒）、Binance公共现货报价BTCUSDT/ETHUSDT/SOLUSDT（15秒）。刷新接口及feed接口实测返回100条快讯和3组报价。外部来源后续可用性及延迟受来源和网络影响。

浏览器预览工具超时，尚未完成本轮视觉验收。没有验证关闭应用后的后台运行或WebSocket推送；这两者未实现。
