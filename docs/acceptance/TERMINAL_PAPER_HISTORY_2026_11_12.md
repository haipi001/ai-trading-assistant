# 交易历史页读取自有Paper账本

新增GET /api/v2/workspaces/research/paper-trades，显式owned账户+市场校验，Execution/OrderDraft/OrderIntent逐层user_id匹配，Paper模式、股票/ETF或CEX资产类型且无链/合约混用。最多100条、has_more、no-store；Decimal按字符串返回，记录时间UTC，不生成任何交易/报告。包含资产记录币种，不做换汇或收益汇总。

实际交易历史面板默认显示PaperTradeHistory：显式读取当前已校验账户，来源/范围/时间/失败/空状态可见；用户、上下文、请求序号变化后丢弃旧回复，下载时再次检查当前身份范围。CSV导出真实当前返回行、保留数字字符串并防公式注入。旧固定界面示例保留在显式预览下，网络失败绝不退回示例。

验证：2相关后端测试（stocks/CEX受控Paper流程、跨用户404、错市场422、只读未增加业务记录、实际API DTO进入前端解析）；外部129/镜像133终端测试及本地构建通过。8001重载PID16898，实际本地现有Paper账户HTTP200读取4条记录，has_more false，execution_available false。该账户记录不代表真实券商/交易所成交；未浏览器验收、未真实账户连接/模型调用。当前仅最近100条Paper，暂无历史分页、实盘fills或资金费/策略执行的完整数据适配，整体目标未完成。

## 历史成交到人工复盘与AI材料

每行新增查看成交复盘，从原review-context接口读取，校验execution/draft/account/asset/journal/review关系。复用原PaperReviewEditor及PaperReviewMaterialPreview；保存人工复盘后以updated_at重挂材料预览，旧冻结材料不继续展示。只读加载与用户/上下文/最新请求绑定，未自动修改复盘或调用模型。AI附件仍要求原标的/场所匹配及显式选择。

实际本地首条记录review-context返回409（日志/复盘缺失），因此补review_available只读元数据：批量核对自有review+journal关联，无记录不补造。列表明确记录不完整并禁用材料入口；若加载时变化返回409，给出具体缺失状态，成交记录保持原样。

3相关后端测试、仓库134终端测试与本地构建通过，包含实际API review-context DTO由前端关系校验、缺失owned review明确false和409。8001重载PID17461。已确认实际数据存在缺失，不等于历史复盘全部可用；未浏览器/真实模型验收，整体目标继续未完成。

## Pagination increment

The owned ledger endpoint accepts `after` as an execution anchor. The anchor must be found through the same explicit user/account/market/Paper filters; unavailable anchors return 422. Pages are ordered by descending creation time and ID, with a 100-row limit and `next_cursor`. No offset or client-supplied timestamp controls the query. Deleted/unavailable anchors require a fresh read. This is a live ledger read, not a frozen full-account snapshot.

The existing panel appends explicitly requested earlier pages, retains decimal strings, rejects repeated IDs, and exports only loaded records. Pending and late results retain the existing user/context/abort checks. Refresh starts over; an earlier-page failure preserves the loaded records. Existing review links remain available after appending.

Validation: 105 controlled SQLite ledger records traverse 100+5 without duplicate IDs; unknown cursor and foreign-user requests reject. These extra rows are test fixtures, not real fills or account-level accounting proof. Focused history/ownership tests: 8 passed. External terminal tests: 131 passed; repository mirror: 135 passed. Terminal production build passed with existing chunk-size warning. Browser acceptance, real provider/account acceptance and historic review-owner repair remain unverified/unresolved.

### Pagination boundary follow-up

History tests now cover both distinct timestamps and 104 equal timestamps: insert a newer owned record between page requests, traverse the original 105 rows without duplicates or shifts, then explicitly refresh to observe the newer record. A foreign-owner execution anchor returns the same unavailable-cursor response as an unknown anchor. Five history tests pass. This is controlled test coverage; it does not prove a frozen snapshot or browser rendering. The panel explains the live-list behavior and distinguishes retryable older-page failures from an unavailable cursor requiring refresh, retaining already loaded records in both cases. JSX parses and the terminal production build passes.
