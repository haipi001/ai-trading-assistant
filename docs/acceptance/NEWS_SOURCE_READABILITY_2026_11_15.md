# 全市场资讯读取验收 — 2026-11-15

## 已实现

- 默认聚合加入东方财富财经快讯、A股公告/财报目录、香港电台财经、CNBC Finance；旧来源配置首次升级补入股票来源，保存后尊重用户选择。
- 新版资讯页提供全部市场、中国财经、香港财经、美国财经和加密资产筛选；各来源独立状态、错误、缓存与时效仍保留。
- 每路最多100条；现有10路最多1000条。前端容量1200条；不再跨来源截断。同链接不同来源、不同消息类型分别保留。
- 来源若提供RSS content:encoded优先读取，保留最多20000字符；只显示来源提供的内容，不补写缺失全文。东方财富时间明确按Asia/Shanghai转UTC。
- API路径保持 `/news-feed/settings`、`/news-feed/latest`、`/news-feed/refresh`；sources目录增加eastmoney、rthk、cnbc、eastmoney_announcements，返回文章及source_status新增market。历史provider标识chinese_aggregate保留兼容，界面显示全市场聚合。
- 自定义RSS、NewsAPI、Nasdaq和Cointelegraph原适配保留；没有启用交易或新增凭证。

## 真实网络证据

见 news-source-live-20261115.json：PANews快讯100/文章100、Odaily快讯10/文章10、东方财富快讯100、香港电台财经20、CNBC财经30、东方财富公告100，均经实际适配器读取。

律动两路连接失败并如实显示，Nasdaq此前实测访问拒绝；NewsAPI需要用户已有Key及账户权限。未接入不明代理或伪造成功。港股财经消息不是港交所公告全文。东方财富公告含财报类目录，不等同结构化财务报表；SEC研究适配独立保留。独立券商研报、付费全文、全部历史分页尚未完成，不应宣称“所有数据”已齐全。

## 验证

后端news_feed及research_feeds共42项测试通过；前端资讯模型、读取器、订阅合并三组检查通过；新版终端构建通过。构建仍有既有大包提示。只推送本任务文件，其他工作区修改不纳入提交。

## 来源

- 香港电台官方RSS目录：https://news.rthk.hk/rthk/ch/rss.feed
- CNBC：https://www.cnbc.com/rss-feeds/
- 东方财富：https://finance.eastmoney.com/ 、https://data.eastmoney.com/notices/
- 律动官方RSS：https://github.com/BlockBeatsOfficial/RSS-v2

## 显示层复验

2026-11-15 使用真实联网来源、隔离本地账户和真实React组件进行DOM显示验收：A股快讯100条、香港财经20条、美股财经30条、A股公告100条，市场切换与列表可显示。不是浏览器截图验收（CUA连接超时）。修复东方财富JSON源Accept头错误导致406的问题；后端43项测试通过。生产Render API连接超时，因此静态站点发布不等于线上动态数据链路验收通过。
