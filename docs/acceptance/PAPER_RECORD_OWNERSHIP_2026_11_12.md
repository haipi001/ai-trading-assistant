# Paper账本归属与事务边界

只读排查本地抽样账户：4笔Paper execution均存在PostTradeReview，但review.user_id与execution所属用户不一致。无原始记录迁移、无重新归属、无补造日志或人工复盘。本报告仅保存聚合数量，不含账户/用户标识和笔记。旧数据继续按不可访问/不完整处理。

代码修正：Paper执行前要求Account/OrderIntent/OrderDraft同owner；新Execution、Journal、Review、Position、TaxLot、Realization、CorporateAction显式绑定account.user_id，审计沿当前操作owner，不依赖请求tenant或数据库默认值。幂等旧回执只接受同owner的review/journal，拒绝归属不一致并保持一个fill。

事务修正：内层ledger writer不提交；外层在完整writer返回后统一commit，随后refresh返回对象，避免refresh前释放锁导致并发writer重叠。commit后的响应丢失仍按未知结果处理，用原key恢复已提交回执，不声称rollback撤销已提交成交。

针对性34测试通过：显式owner写入、跨owner链拒绝、幂等/并发/响应丢失、关联回执owner拒绝及不产生第二笔fill。非默认owner writer测试在受控SQLite中规范fixture owner并stub policy gate，仅证明writer归属；不证明真实登录/非默认owner完整风控闭环。已有真实API受控gate/Paper tests另覆盖门禁。完整基线1054通过，最后回执owner补强后的完整回归进行中，尚未将其当作最终验证。

最终版本验证：完整后端1056 passed in106.94s（/tmp/paper-owner-final-full-backend.log）；针对性34通过，终端134通过，diff check通过。已重载本地后端PID18269，health200。未对真实数据库执行Paper成交或迁移历史owner。完整回归为受控测试，不证明真实券商/付费模型/浏览器闭环；4条旧复盘归属问题保持不可访问，需要后续明确归属依据与迁移核验。
