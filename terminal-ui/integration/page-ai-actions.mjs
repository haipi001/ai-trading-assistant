// Descriptive UI contracts, never authorization, execution permission or evidence.
const freeze=value=>{if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
export const PAGE_AI_VERSION=1;
export const PAGE_AI_ARTIFACT_LABELS=freeze({raw_chart_review:'原始K线研究回复',source_timeline:'来源时间线与冲突说明',wallet_evidence_review:'钱包证据审阅',editable_filter_draft:'可编辑筛选条件草稿',liquidity_review:'流动性审阅',flow_review:'资金流口径审阅',scenario_review:'情景风险审阅',valuation_review:'估值证据审阅',exposure_review:'持仓暴露审阅',thesis_review:'Thesis与复盘对照',gate_explanation:'门禁解释',order_review:'订单参数审阅',parameter_review_draft:'策略参数审阅草稿',connection_diagnosis:'脱敏连接诊断',event_review:'事件时间线',reserve_review:'储备口径审阅',workspace_advice:'工作区建议',field_explanation:'字段说明',monitoring_rule_draft:'监控规则草稿',data_gap_checklist:'数据缺口清单'});
export const PAGE_AI_SOURCES=freeze({
 market_ohlcv:{label:'主图原始 OHLCV',adapter:'implemented',reads:['symbol','venue','quote_currency','timeframe','kind','bars','statistics','observed_at','captured_at'],note:'仅原始主图数据，不含画线、指标或其它窗口；客户端来源未经独立验证。'},
 cached_news:{label:'服务端缓存资讯',adapter:'implemented',reads:['provider','articles','fetched_at','stale','source_failures'],note:'缓存未按当前子栏目或持仓自动过滤，需核对相关性和来源冲突。'},
 onchain_snapshot:{label:'已选择的链上只读快照',adapter:'implemented',reads:['wallet_public_address','chain_id','contract_address','block_number','balances','selected_allowances','selected_protocols'],note:'需先在链上页面读取并显式选择附件；不含全网索引或签名权限。'},
 asset_universe:{label:'带来源与时点的候选资产集合',adapter:'missing',reads:['instrument_identity','prices','as_of','source','screening_fields']},
 market_depth:{label:'当前场所深度与成交快照',adapter:'missing',reads:['instrument_identity','venue','bids','asks','trades','as_of']},
 fund_flows:{label:'资金流口径与原始样本',adapter:'missing',reads:['instrument_identity','venue','flows','classification_method','as_of']},
 derivatives:{label:'衍生品与期权风险材料',adapter:'missing',reads:['contract_identity','funding','open_interest','expiry','strike','as_of']},
 fundamentals:{label:'财务、估值或代币供给材料',adapter:'missing',reads:['instrument_identity','statements','valuation_basis','token_supply','source','as_of']},
 portfolio:{label:'所选账户的应用账本持仓（未实时拉取）',adapter:'implemented',reads:['account_identity','positions','recorded_values','currency','record_updated_at','unknown_valuation','sample_scope'],note:'仅所选账户账本记录，估值时效未知；最多20条，不提供实时余额、跨账户总额或汇率换算。'},
 account_distribution:{label:'多账户归属与一致估值范围',adapter:'missing',reads:['owned_accounts','positions_by_account','valuation_currency','valuation_times','duplicate_transfers']},
 journal:{label:'账户绑定的流水与复盘记录',adapter:'missing',reads:['account_identity','ledger_entries','thesis','fees','journal','as_of']},
 gates:{label:'服务端门禁结果及有效期',adapter:'missing',reads:['account_identity','decision_id','status','reasons','valid_until']},
 order:{label:'原账户订单草稿与服务端状态',adapter:'missing',reads:['account_identity','draft_id','parameters','fees','risk','approval_status','as_of']},
 strategy:{label:'所选策略的参数与触发规则',adapter:'missing',reads:['strategy_id','parameters','trigger','invalidation','constraints']},
 script_backtest:{label:'脚本差异、版本与回测假设',adapter:'missing',reads:['script_version','source_diff','data_range','fees','slippage','validation_results']},
 connections:{label:'脱敏连接及权限状态',adapter:'missing',reads:['connection_id','status','permissions','last_verified_at','redacted_error']},
 economic_events:{label:'带来源的经济事件日历',adapter:'missing',reads:['event','time','source','revision','uncertainty']},
 reserves:{label:'储备证明及负债口径',adapter:'missing',reads:['asset_identity','reserves','liabilities','method','source','as_of']},
 preferences:{label:'布局与导航偏好快照',adapter:'missing',reads:['layout','navigation','shortcuts']},
 documentation:{label:'当前版本字段与命令文档',adapter:'missing',reads:['version','fields','commands','source']},
 monitoring:{label:'提醒规则与真实任务状态',adapter:'missing',reads:['rule','snapshot','budget','status','failure','cancel_resume_support']}
});
const families={
 chart:{sources:['market_ohlcv'],artifact:'raw_chart_review',label:'分析原始K线区间与数据限制',risk:'核对周期、样本范围与回放截止；不得声称读取了指标、画线或其它窗口。'},
 news:{sources:['cached_news'],artifact:'source_timeline',label:'整理报道时间线与来源冲突',risk:'只使用实际缓存中的相关报道，区分发布时间与获取时间，不把缺失报道当作没有事件。'},
 wallet:{sources:['onchain_snapshot'],artifact:'wallet_evidence_review',label:'解释所选钱包余额、授权与协议证据',risk:'区分节点观察、历史记录与未知项；不得推断完整持仓、安全性、最终性或可交易性。'},
 universe:{sources:['asset_universe'],artifact:'editable_filter_draft',label:'分析候选集合并提出可编辑筛选条件',risk:'必须说明候选范围与数据口径，不将本地自选或演示排行当作全市场排名。'},
 depth:{sources:['market_depth'],artifact:'liquidity_review',label:'检查深度、价差与流动性',risk:'核对场所与时点，不从OHLCV推导订单簿或执行保证。'},
 flows:{sources:['fund_flows'],artifact:'flow_review',label:'解释资金流口径与异常',risk:'资金分类不是交易者真实身份，不将流入量等同未来收益。'},
 derivative:{sources:['derivatives'],artifact:'scenario_review',label:'解释合约与期权情景风险',risk:'展示不等于交易权限；保留期限、杠杆、资金费率与缺失波动率限制。'},
 fundamental:{sources:['fundamentals'],artifact:'valuation_review',label:'检查财务估值或代币供给证据',risk:'股票和代币使用不同口径，缺少数据时不套用估值或虚构财报。'},
 portfolio:{sources:['portfolio'],artifact:'exposure_review',label:'检查持仓集中度与估值缺口',risk:'账户、币种和估值时间必须明确；未知估值不得当作零，不将钱包转账重复计为收益。'},
 account_distribution:{sources:['account_distribution'],artifact:'exposure_review',label:'核对多账户分布与重复计量',risk:'不能用单账户摘录替代跨账户汇总，未核实估值和转账去重前不计算总收益。'},
 journal:{sources:['journal'],artifact:'thesis_review',label:'比较原始理由、流水与后续事实',risk:'区分转账、成交、费用和盈亏，不自动改写Thesis或复盘结论。'},
 gates:{sources:['gates'],artifact:'gate_explanation',label:'解释拒绝原因与可修正步骤',risk:'保留服务端状态、理由和有效期，不能把解释当作重新批准。'},
 order:{sources:['order'],artifact:'order_review',label:'解释订单参数、成本与门禁',risk:'只审阅原账户草稿；不得修改审批、提交、执行或对账状态。'},
 strategy:{sources:['strategy','script_backtest'],artifact:'parameter_review_draft',label:'审阅触发、失效条件与参数草稿',risk:'检查未来函数、费用、滑点与过拟合；草稿不能自动启动策略或提交订单。'},
 connections:{sources:['connections'],artifact:'connection_diagnosis',label:'诊断连接、权限与陈旧状态',risk:'只允许脱敏状态；不得读取或请求密钥、助记词、密码、签名或提款权限。'},
 macro:{sources:['economic_events'],artifact:'event_review',label:'梳理事件时间与影响假设',risk:'核对来源、修订和时区，推断与事实分开。'},
 reserves:{sources:['reserves'],artifact:'reserve_review',label:'核对储备证明与负债口径',risk:'储备展示不是偿付能力或资金安全保证。'},
 preferences:{sources:['preferences'],artifact:'workspace_advice',label:'检查布局、导航与恢复建议',risk:'只解释偏好，不修改账户、授权或交易执行状态。'},
 documentation:{sources:['documentation'],artifact:'field_explanation',label:'解释本页字段与操作入口',risk:'按实际版本核对文档与权限，不声称执行或验证了未读取的配置。'},
 monitoring:{sources:['monitoring'],artifact:'monitoring_rule_draft',label:'拟定监控规则并检查任务限制',risk:'不能用计时动画冒充任务状态；预算、失败、取消和恢复按实际服务显示。'}
};
const native={GP:'chart',HP:'chart',DEPTH:'depth',OPT:'derivative',FA:'fundamental',DES:'fundamental',COMP:'fundamental',PORT:'portfolio',TRD:'journal',ORD:'order',ALRT:'monitoring',TOP:'news',N:'news',ECO:'macro',WEI:'universe',W:'universe',MOST:'universe',MAP:'universe',FX:'universe',GOV:'universe',CMDT:'universe',EQS:'universe',SRCH:'universe',SET:'preferences',WORK:'preferences',CONN:'connections',FEED:'connections',PLUG:'connections',XL:'connections',BROKER:'connections',ACCOUNT:'connections',MSG:'monitoring',INBOX:'monitoring',SUPPORT:'documentation',HELP:'documentation',ABOUT:'documentation',FLDS:'documentation'};
function family(feature){
 if(feature.page==='terminal')return native[feature.code]||'documentation';
 if(feature.page==='flash'||feature.page==='news')return 'news';
 if(feature.page==='strategy')return 'strategy';
 if(feature.page==='chain'||feature.page==='more'&&feature.tab==='钱包')return 'wallet';
 if(feature.page==='assets')return feature.tab==='风控'?'gates':feature.tab==='API账号分布'?'account_distribution':['盈亏日历','流水'].includes(feature.tab)?'journal':'portfolio';
 if(feature.page==='auth')return 'connections';
 if(feature.page==='data')return feature.tab==='加密货币储备'?'reserves':'wallet';
 if(feature.page==='market')return ({'图表':'chart','深度':'depth','资金流':'flows','合约数据':'derivative','自选':'universe'})[feature.tab]||'universe';
 if(feature.page==='more')return feature.tab==='宏观'?'macro':feature.tab==='自定义导航'?'preferences':'documentation';
 if(feature.page==='home')return feature.tab==='合约雷达'?'derivative':feature.tab==='功能指南'?'documentation':feature.tab==='AI智搜'?'portfolio':'universe';
 return 'documentation';
}
const contextFields=['panelId','market','instrumentId','venue','chainId','contractAddress','accountId','walletId','timeframe','executionMode','contextVersion'];
function contextSnapshot(context){
 if(!context||!['stocks','cex','onchain'].includes(context.market)||!['READ_ONLY','PAPER'].includes(context.executionMode)||context.market==='onchain'&&context.executionMode!=='READ_ONLY'||!Number.isSafeInteger(context.contextVersion)||context.contextVersion<0)throw Error('invalid_page_ai_context');
 return Object.fromEntries(contextFields.map(key=>{const value=context[key]??(key==='contextVersion'?0:'');if(key!=='contextVersion'&&typeof value!=='string')throw Error('invalid_page_ai_context');return [key,value];}));
}
export function pageAIContextMatches(prepared,context){try{const current=contextSnapshot(context);return contextFields.every(key=>prepared?.[key]===current[key]);}catch{return false;}}
export function pageAIPolicy(feature){
 if(!feature||typeof feature.code!=='string'||!/^(R\d{3}|STR[0-8]|[A-Z]{1,12})$/.test(feature.code))throw Error('invalid_page_ai_feature');
 const key=family(feature),pageNames={home:'研究首页',market:'专业图表',flash:'实时快讯',news:'新闻与研报',strategy:'策略',chain:'链上研究',assets:'资产管理',auth:'账户与授权',data:'数据中心',more:'工具与帮助'},title=(pageNames[feature.page]?pageNames[feature.page]+' / ':'')+(feature.label||feature.tab||feature.code);
 let spec=families[key];
 const strategyDetails={0:'核对策略状态、版本与停止条件。',1:'核对套利两腿、场所、报价时点、资金费率和并发暴露。',2:'核对DCA预算、频率、币种名单、单币上限和暂停条件。',3:'核对网格上下界、层数、资金分配、杠杆与止损。',4:'核对脚本版本、指标周期、未来函数、费用和滑点；差异只能审阅，不能执行。',5:'核对CEX信号来源、跟单比例、延迟、资金上限与账户隔离。',6:'核对链、合约、钱包、Gas、滑点、MEV及信号时点；当前仅只读研究，不请求签名或广播。',7:'核对主力分类口径、样本范围与来源证据，不能推断真实交易者身份。',8:'核对股票交易时段、事件来源、成交口径和跟踪规则。'};
 if(feature.strategyCategory!=null&&strategyDetails[feature.strategyCategory])spec={...spec,risk:spec.risk+strategyDetails[feature.strategyCategory]};
 let markets=key==='wallet'?['onchain']:['chart','depth','derivative','flows','fundamental','order','strategy','portfolio'].includes(key)?['stocks','cex']:key==='reserves'?['cex','onchain']:['stocks','cex','onchain'];
 if(feature.strategyCategory===6)markets=['onchain'];else if(feature.strategyCategory===5)markets=['cex'];else if(feature.strategyCategory===8)markets=['stocks'];
 const nativePage=feature.page==='terminal';
 const available=spec.sources.every(source=>PAGE_AI_SOURCES[source].adapter==='implemented')&&!nativePage;
 const destination=key==='wallet'&&feature.page!=='chain'&&!(feature.page==='more'&&feature.tab==='钱包')?'R056':nativePage?({chart:'R009',news:'R014',wallet:'R056',depth:'R010',portfolio:'R045',journal:'R049',gates:'R050',strategy:'STR0',connections:'R051',macro:'R057',order:'R009'}[key]||'R059'):feature.code;
 const make=(kind,label,sources)=>({id:feature.code+'.'+kind,label,title,allowedReads:sources.map(source=>({source,fields:PAGE_AI_SOURCES[source].reads})),requiredSources:sources,artifact:kind==='gaps'?'data_gap_checklist':spec.artifact,implementedArtifact:'validated_research_reply',permissions:['readiness:write'],destination,failureStates:['context_changed','market_incompatible','data_missing','adapter_unavailable','configuration_required','request_failed'],availability:kind==='gaps'?'review_required':available?'review_required':nativePage?'business_panel_required':'adapter_unavailable',limitations:spec.risk,prompt:kind==='gaps'?`针对“${title}”，列出所需的${spec.sources.map(source=>PAGE_AI_SOURCES[source].label).join('、')}，说明缺失项和核验步骤。你没有读取本页实际内容，不要给出资产、账户或策略结论。${spec.risk}`:`针对“${title}”，${label}。只依据显式提供的${sources.map(source=>PAGE_AI_SOURCES[source].label).join('、')}，保留来源、时点、事实、推断、缺失项。${sources.map(source=>PAGE_AI_SOURCES[source].note||'').join('')}${spec.risk}`});
 return freeze({version:PAGE_AI_VERSION,featureCode:feature.code,family:key,supportedMarkets:markets,aliases:[feature.code,`${feature.page}:${feature.tab||feature.code}${feature.strategyCategory!=null?':'+feature.strategyCategory:''}`],actions:[make('analysis',`${title} · ${spec.label}`,spec.sources),make('gaps',`${title} · 核对数据缺口`,[]),make('risk',`${title} · 检查证据与风险`,spec.sources)]});
}
export function preparePageAIAction(feature,id,context){
 const policy=pageAIPolicy(feature),action=policy.actions.find(item=>item.id===id),snapshot=contextSnapshot(context);
 if(!action)throw Error('unknown_page_ai_action');
 if(!policy.supportedMarkets.includes(snapshot.market))throw Error('market_incompatible');
 if(action.availability!=='review_required')throw Error(action.availability);
 return freeze({schemaVersion:PAGE_AI_VERSION,featureCode:feature.code,feature:{code:feature.code,label:feature.label||feature.tab||feature.code,page:feature.page,tab:feature.tab,...(feature.strategyCategory!=null?{strategyCategory:feature.strategyCategory}:{})},actionId:id,label:action.label,requiredSources:action.requiredSources,artifact:action.artifact,implementedArtifact:action.implementedArtifact,destination:action.destination,question:action.prompt,context:snapshot,executionAvailable:false,autoSubmit:false});
}
export function validatePageAIIntent(value,feature,context){
 if(!value||value.schemaVersion!==PAGE_AI_VERSION||value.featureCode!==feature?.code||value.executionAvailable!==false||value.autoSubmit!==false||!pageAIContextMatches(value.context,context))throw Error('page_ai_context_changed');
 const canonical=preparePageAIAction(feature,value.actionId,context);
 for(const field of ['requiredSources','artifact','implementedArtifact','destination','question'])if(JSON.stringify(value[field])!==JSON.stringify(canonical[field]))throw Error('page_ai_contract_mismatch');
 return canonical;
}
export function pageAIMarketMatches(capture,context){
 if(!capture||!context||!['stocks','cex'].includes(context.market)||capture.data_semantics!=='raw_ohlcv'||!['online','csv','replay'].includes(capture.kind)||!Array.isArray(capture.bars)||!capture.bars.length||typeof capture.source_label!=='string'||!capture.source_label.trim()||/demo|mock|seed|演示|模拟/i.test(capture.source_label||''))return false;
 const aliases={'币安':'binance','欧易okx':'okx','欧易':'okx','纳斯达克':'nasdaq'};
 const venue=value=>aliases[String(value||'').trim().toLowerCase()]||String(value||'').trim().toLowerCase();
 const period=String(context.timeframe||'').replace(/MO$/,'mo').replace(/W$/,'wk').toLowerCase();
 return String(capture.symbol).toUpperCase()===String(context.instrumentId||'').split('/')[0].toUpperCase()&&venue(capture.venue)===venue(context.venue)&&capture.timeframe===period&&capture.market_type===(context.market==='stocks'?'stock':'spot')&&capture.quote_currency===(context.market==='stocks'?'USD':'USDT');
}
export function pageAIReadiness(plan,{context,includeMarket=false,marketCapture=null,includeNews=false,newsReady=false,includeOnchain=false,onchainValid=false,includePortfolio=false,portfolioValid=false}={}){
 if(!plan)return '';
 try{validatePageAIIntent(plan,plan.feature,context);}catch{return '本页动作来自此前上下文，请重新选择。';}
 if(includeMarket&&!plan.requiredSources.includes('market_ohlcv')||includeNews&&!plan.requiredSources.includes('cached_news')||includeOnchain&&!plan.requiredSources.includes('onchain_snapshot')||includePortfolio&&!plan.requiredSources.includes('portfolio'))return '这项本页动作不读取额外材料，请取消多选资料，或先转为手动提问。';
 if(plan.requiredSources.includes('portfolio')&&(!includePortfolio||!portfolioValid))return '本页动作需要当前账户的有效账本材料，请读取并审阅；记录估值不是实时持仓。';
 if(plan.requiredSources.includes('market_ohlcv')&&(!includeMarket||!pageAIMarketMatches(marketCapture,context)))return '本页动作需要当前标的原始K线，请选择有效资料；演示数字不能发送。';
 if(plan.requiredSources.includes('cached_news')&&(!includeNews||!newsReady))return '本页动作需要已获取资讯，请先核对缓存来源。';
 if(plan.requiredSources.includes('onchain_snapshot')&&(!includeOnchain||!onchainValid))return '本页动作需要所选钱包的有效只读附件，请回链上页读取并选择材料。';
 return '';
}
