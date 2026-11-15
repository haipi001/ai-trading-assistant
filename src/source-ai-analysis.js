// Deterministic analysis of already-read public material.
// Every number below is computed from the caller's snapshot. Nothing is fabricated:
// a field the source did not provide stays missing and is reported as a gap.

const num = value => typeof value === 'number' && Number.isFinite(value);
const round = (value, digits = 2) => (num(value) ? Number(value.toFixed(digits)) : null);
const sum = rows => rows.reduce((total, row) => total + row, 0);
const signed = (value, digits = 2) => (num(value) ? `${value > 0 ? '+' : ''}${value.toFixed(digits)}` : '未提供');
const percent = (value, digits = 2) => (num(value) ? `${value > 0 ? '+' : ''}${value.toFixed(digits)}%` : '未提供');

// Streams can deliver holes, nulls or partial rows. Drop what cannot be read
// rather than letting one bad row throw and blank the whole panel.
const rows = value => (Array.isArray(value) ? value.filter(row => row && typeof row === 'object') : []);
const field = (row, key) => (row && typeof row === 'object' && num(row[key]) ? row[key] : null);


function metric(label, value, hint) {
  return { label, value: value == null ? '未提供' : String(value), hint: hint || '' };
}

function result(summary, { metrics = [], findings = [], risks = [], gaps = [], basis = '' } = {}) {
  return { ready: true, summary, metrics: metrics.filter(Boolean), findings, risks, gaps, basis };
}

export function emptyAnalysis(reason) {
  return { ready: false, summary: reason || '当前范围没有已校验资料；不使用示例补齐。', metrics: [], findings: [], risks: [], gaps: [reason || '缺少可用来源'], basis: '' };
}

function totals(rowsIn) {
  const list = rows(rowsIn);
  const notional = sum(list.map(row => (field(row, 'price') ?? 0) * (field(row, 'quantity') ?? 0)));
  const quantity = sum(list.map(row => field(row, 'quantity') ?? 0));
  return { notional, quantity };
}

function within(rowsIn, mid, ratio) {
  const lower = mid * (1 - ratio);
  const upper = mid * (1 + ratio);
  return rows(rowsIn).filter(row => (field(row, 'price') ?? NaN) >= lower && (field(row, 'price') ?? NaN) <= upper);
}

// 订单与成交 — spread, book imbalance, and where liquidity actually sits.
export function analyzeDepth(material) {
  const asks = rows(material?.asks);
  const bids = rows(material?.bids);
  if (!asks.length || !bids.length) return emptyAnalysis('盘口没有可用的买卖档位');

  const bestAsk = field(asks[0], 'price');
  const bestBid = field(bids[0], 'price');
  if (!num(bestAsk) || !num(bestBid) || bestAsk <= 0 || bestBid <= 0) return emptyAnalysis('盘口最优价无效');

  const mid = (bestAsk + bestBid) / 2;
  const spread = bestAsk - bestBid;
  const spreadBps = (spread / mid) * 10000;
  const ask = totals(asks);
  const bid = totals(bids);
  const total = ask.quantity + bid.quantity;
  const imbalance = total > 0 ? (bid.quantity - ask.quantity) / total : null;
  const bidInner = within(bids, mid, 0.005);
  const askInner = within(asks, mid, 0.005);
  const bidInnerQty = sum(bidInner.map(row => row.quantity));
  const askInnerQty = sum(askInner.map(row => row.quantity));
  const innerTotal = bidInnerQty + askInnerQty;
  const innerImbalance = innerTotal > 0 ? (bidInnerQty - askInnerQty) / innerTotal : null;

  const lean = imbalance == null ? '无法判断' : imbalance > 0.15 ? '买方挂单占优' : imbalance < -0.15 ? '卖方挂单占优' : '买卖挂单接近平衡';
  const tightness = spreadBps < 5 ? '价差很窄' : spreadBps < 20 ? '价差正常' : '价差偏宽';

  const findings = [
    `中间价 ${round(mid, 6)}，最优买 ${round(bestBid, 6)} / 最优卖 ${round(bestAsk, 6)}。`,
    `全档买卖挂单量失衡 ${signed(imbalance == null ? null : imbalance * 100, 1)}%，${lean}。`,
    `中间价 ±0.5% 范围内买卖量失衡 ${signed(innerImbalance == null ? null : innerImbalance * 100, 1)}%，这部分才是真正贴近成交的流动性。`,
  ];
  if (spreadBps > 50) findings.push('价差超过 50 个基点，市价单的即时滑点成本会明显偏高。');

  const risks = [];
  if (spreadBps > 30) risks.push(`价差 ${round(spreadBps, 1)} 个基点偏宽，市价成交要吃较厚的价差。`);
  if (total > 0 && ask.quantity > 0 && bid.quantity > 0) {
    const thinSide = ask.quantity < bid.quantity ? '卖盘' : '买盘';
    const ratio = Math.min(ask.quantity, bid.quantity) / Math.max(ask.quantity, bid.quantity);
    if (ratio < 0.4) risks.push(`${thinSide}挂单量只有另一侧的一半不到（比值 ${round(ratio, 2)}），单笔大额委托会显著推动价格。`);
  }
  if (innerTotal > 0 && innerTotal / total < 0.25) risks.push('盘口深度集中在远离中间价的档位，贴近成交的挂单只占很小一部分。');

  const gaps = [];
  if (asks.length < 5 || bids.length < 5) gaps.push(`只读取到 ${asks.length} 档卖 / ${bids.length} 档买，深度覆盖有限。`);
  gaps.push('盘口是瞬时快照，不反映撤单与隐藏单。');

  return result(
    `盘口${tightness}（${round(spreadBps, 1)} 个基点），${lean}。买卖挂单比 ${round(ask.quantity > 0 ? bid.quantity / ask.quantity : null, 2)}，中间价 ${round(mid, 6)}。`,
    {
      metrics: [
        metric('中间价', round(mid, 6)),
        metric('价差', `${round(spread, 6)}（${round(spreadBps, 1)} bps）`),
        metric('买盘挂单量', round(bid.quantity, 4), `约 ${round(bid.notional, 2)} USDT`),
        metric('卖盘挂单量', round(ask.quantity, 4), `约 ${round(ask.notional, 2)} USDT`),
        metric('全档失衡', `${signed(imbalance == null ? null : imbalance * 100, 1)}%`),
        metric('贴近档失衡', `${signed(innerImbalance == null ? null : innerImbalance * 100, 1)}%`, '中间价 ±0.5%'),
      ],
      findings, risks, gaps,
      basis: '由已读取的公开盘口快照计算',
    },
  );
}

// 资金流向 — public trade flow, explicitly not account capital flow.
export function analyzeTrades(material) {
  const trades = rows(material?.recent_public_trades);
  if (!trades.length) return emptyAnalysis('没有可用的公开成交样本');

  const buys = trades.filter(row => row.side === '买入');
  const sells = trades.filter(row => row.side === '卖出');
  const amount = row => (field(row, 'price') ?? 0) * (field(row, 'quantity') ?? 0);
  const buyNotional = sum(buys.map(amount));
  const sellNotional = sum(sells.map(amount));
  const totalNotional = buyNotional + sellNotional;
  const net = buyNotional - sellNotional;
  const netRatio = totalNotional > 0 ? net / totalNotional : null;
  const buyRatio = totalNotional > 0 ? buyNotional / totalNotional : null;

  const prices = trades.map(row => field(row, 'price')).filter(num);
  const first = prices[prices.length - 1];
  const last = prices[0];
  const drift = num(first) && first > 0 ? ((last - first) / first) * 100 : null;

  const sizes = trades.map(amount).sort((a, b) => b - a);
  const top3 = sum(sizes.slice(0, 3));
  const concentration = totalNotional > 0 ? top3 / totalNotional : null;
  const largest = sizes[0];
  const average = totalNotional / trades.length;

  const times = trades.map(row => field(row, 'time')).filter(num);
  const span = times.length > 1 ? Math.round((Math.max(...times) - Math.min(...times)) / 1000) : null;

  const lean = netRatio == null ? '无法判断' : netRatio > 0.1 ? '主动买盘占优' : netRatio < -0.1 ? '主动卖盘占优' : '主动买卖大致均衡';

  const findings = [
    `样本内主动买 ${round(buyNotional, 2)} / 主动卖 ${round(sellNotional, 2)} USDT，净额 ${signed(round(net, 2))}。`,
    `单笔金额中位量级约 ${round(average, 2)} USDT，最大一笔 ${round(largest, 2)} USDT。`,
    span == null ? '样本没有可比较的时间跨度。' : `样本覆盖约 ${span} 秒，期间价格变动 ${percent(drift)}。`,
  ];
  if (concentration != null && concentration > 0.5) findings.push(`前 3 笔成交占总金额 ${round(concentration * 100, 1)}%，方向由少数大单决定。`);

  const risks = [];
  if (trades.length < 10) risks.push(`只有 ${trades.length} 笔成交，样本过小，方向结论不稳定。`);
  if (concentration != null && concentration > 0.6) risks.push('成交金额高度集中在大单，可能是扫单或对倒，不代表持续买卖意愿。');
  if (num(drift) && Math.abs(drift) > 1) risks.push(`样本期内价格已变动 ${percent(drift)}，此流向可能已部分反映在价格里。`);

  return result(
    `最近 ${trades.length} 笔公开成交中${lean}，主动买占比 ${round(buyRatio == null ? null : buyRatio * 100, 1)}%，净流入 ${signed(round(net, 2))} USDT。`,
    {
      metrics: [
        metric('样本笔数', trades.length),
        metric('主动买金额', round(buyNotional, 2)),
        metric('主动卖金额', round(sellNotional, 2)),
        metric('净流入', signed(round(net, 2))),
        metric('主动买占比', `${round(buyRatio == null ? null : buyRatio * 100, 1)}%`),
        metric('前 3 笔集中度', `${round(concentration == null ? null : concentration * 100, 1)}%`),
        metric('样本价格变动', percent(drift)),
      ],
      findings, risks,
      gaps: ['这是公开逐笔成交的方向归类，不是交易所资金流入流出，也不是账户资金变动。', '样本只覆盖最近一段时间，不能外推为全天或全市场资金流。'],
      basis: '由已读取的公开逐笔成交计算',
    },
  );
}

function mean(values) {
  if (!values.length) return null;
  return sum(values) / values.length;
}

function stddev(values) {
  if (values.length < 2) return null;
  const average = mean(values);
  return Math.sqrt(sum(values.map(value => (value - average) ** 2)) / (values.length - 1));
}

function simpleMA(closes, period) {
  if (closes.length < period) return null;
  const slice = closes.slice(-period);
  return sum(slice) / period;
}

function rsi(closes, period = 14) {
  if (closes.length < period + 1) return null;
  let gain = 0;
  let loss = 0;
  for (let index = closes.length - period; index < closes.length; index += 1) {
    const change = closes[index] - closes[index - 1];
    if (change >= 0) gain += change;
    else loss -= change;
  }
  if (loss === 0) return gain === 0 ? 50 : 100;
  const rs = gain / loss;
  return 100 - 100 / (1 + rs);
}

// 技术分析 — trend, volatility and levels computed from the bars actually read.
export function analyzeCandles(material) {
  const bars = rows(material?.candles);
  if (bars.length < 2) return emptyAnalysis('K 线条数不足，无法计算走势');

  const closes = bars.map(row => field(row, 'close')).filter(num);
  const highs = bars.map(row => field(row, 'high')).filter(num);
  const lows = bars.map(row => field(row, 'low')).filter(num);
  const volumes = bars.map(row => field(row, 'volume')).filter(num);
  if (closes.length < 2) return emptyAnalysis('K 线收盘价无效');

  const first = closes[0];
  const last = closes[closes.length - 1];
  const change = first > 0 ? ((last - first) / first) * 100 : null;
  const high = highs.length ? Math.max(...highs) : null;
  const low = lows.length ? Math.min(...lows) : null;
  const range = num(high) && num(low) && low > 0 ? ((high - low) / low) * 100 : null;

  const returns = [];
  for (let index = 1; index < closes.length; index += 1) {
    if (closes[index - 1] > 0) returns.push(((closes[index] - closes[index - 1]) / closes[index - 1]) * 100);
  }
  const volatility = stddev(returns);
  const maxMove = returns.length ? returns.reduce((worst, value) => (Math.abs(value) > Math.abs(worst) ? value : worst), 0) : null;

  const ma5 = simpleMA(closes, 5);
  const ma10 = simpleMA(closes, 10);
  const ma20 = simpleMA(closes, 20);
  const strength = rsi(closes);

  const half = Math.max(1, Math.floor(volumes.length / 2));
  const recentVolume = mean(volumes.slice(-half));
  const priorVolume = mean(volumes.slice(0, volumes.length - half));
  const volumeChange = num(recentVolume) && num(priorVolume) && priorVolume > 0 ? ((recentVolume - priorVolume) / priorVolume) * 100 : null;

  const alignment = [ma5, ma10, ma20].every(num)
    ? ma5 > ma10 && ma10 > ma20 ? '均线多头排列' : ma5 < ma10 && ma10 < ma20 ? '均线空头排列' : '均线交织，方向不明'
    : '均线样本不足';

  const trend = !num(change) ? '未提供' : change > 2 ? '上行' : change < -2 ? '下行' : '横盘';

  const findings = [
    `样本 ${bars.length} 根，收盘自 ${round(first, 6)} 到 ${round(last, 6)}，变动 ${percent(change)}。`,
    `区间最高 ${round(high, 6)} / 最低 ${round(low, 6)}，振幅 ${round(range, 2)}%。`,
    `${alignment}${num(ma5) ? `；MA5 ${round(ma5, 6)}，MA10 ${round(ma10, 6)}` : ''}。`,
    num(strength) ? `RSI(${Math.min(14, closes.length - 1)}) 约 ${round(strength, 1)}。` : '样本不足以计算 RSI。',
  ];
  if (num(volumeChange)) findings.push(`后半段均量较前半段变动 ${percent(volumeChange)}。`);

  const risks = [];
  if (num(volatility) && volatility > 2) risks.push(`单根平均波动 ${round(volatility, 2)}%，波动显著偏高，止损容易被噪声触发。`);
  if (num(strength) && strength > 70) risks.push('RSI 高于 70，短线处于超买区，追高的回撤风险上升。');
  if (num(strength) && strength < 30) risks.push('RSI 低于 30，短线处于超卖区，反弹未必代表趋势反转。');
  if (num(maxMove) && Math.abs(maxMove) > 3 * (volatility || 1)) risks.push(`存在一根异常波动 ${percent(maxMove)}，可能是消息或流动性缺口，不宜当作趋势斜率。`);

  const gaps = [`只有 ${bars.length} 根 K 线参与计算，指标窗口越长越不完整。`, '未做复权、除权或跨场所对齐。', '以上是历史统计，不构成对未来价格的预测。'];

  return result(
    `样本内价格${trend} ${percent(change)}，${alignment}，单根波动约 ${round(volatility, 2)}%。`,
    {
      metrics: [
        metric('样本根数', bars.length),
        metric('区间变动', percent(change)),
        metric('振幅', `${round(range, 2)}%`),
        metric('最高 / 最低', `${round(high, 6)} / ${round(low, 6)}`),
        metric('单根波动', `${round(volatility, 2)}%`),
        metric('MA5', round(ma5, 6)),
        metric('MA10', round(ma10, 6)),
        metric('RSI', num(strength) ? round(strength, 1) : '样本不足'),
        metric('量能变化', percent(volumeChange)),
      ],
      findings, risks, gaps,
      basis: '由已读取的公开 OHLCV 计算',
    },
  );
}

// 特色数据 — derived microstructure the generic panels do not surface.
export function analyzeProfile(material) {
  const bars = rows(material?.candles);
  const trades = rows(material?.trades);
  if (!bars.length && !trades.length) return emptyAnalysis('特色数据需要 K 线与成交样本，当前都未读取到');

  const metrics = [];
  const findings = [];
  const risks = [];
  const gaps = [];

  const usable = bars.filter(row => num(field(row, 'high')) && num(field(row, 'low')) && num(field(row, 'close')));
  if (usable.length >= 2) {
    const typical = usable.map(row => ({ price: (field(row, 'high') + field(row, 'low') + field(row, 'close')) / 3, volume: field(row, 'volume') ?? 0 }));
    const volumeTotal = sum(typical.map(row => row.volume));
    const vwap = volumeTotal > 0 ? sum(typical.map(row => row.price * row.volume)) / volumeTotal : null;
    const lastClose = field(usable[usable.length - 1], 'close');
    const deviation = num(vwap) && vwap > 0 && num(lastClose) ? ((lastClose - vwap) / vwap) * 100 : null;

    metrics.push(metric('样本 VWAP', round(vwap, 6)), metric('现价相对 VWAP', percent(deviation)));
    if (num(deviation)) findings.push(`现价高于成交量加权均价 ${percent(deviation)}，${deviation > 0 ? '近期成交者整体处于浮盈' : '近期成交者整体处于浮亏'}。`);

    const upper = Math.max(...usable.map(row => field(row, 'high')));
    const lower = Math.min(...usable.map(row => field(row, 'low')));
    if (num(upper) && num(lower) && upper > lower) {
      const buckets = new Array(10).fill(0);
      for (const row of usable) {
        const index = Math.min(9, Math.max(0, Math.floor(((field(row, 'close') - lower) / (upper - lower)) * 10)));
        buckets[index] += field(row, 'volume') ?? 0;
      }
      const peak = buckets.indexOf(Math.max(...buckets));
      const bucketLow = lower + ((upper - lower) * peak) / 10;
      const bucketHigh = lower + ((upper - lower) * (peak + 1)) / 10;
      const bucketShare = volumeTotal > 0 ? buckets[peak] / volumeTotal : null;
      metrics.push(metric('成交密集区', `${round(bucketLow, 6)} – ${round(bucketHigh, 6)}`, `占样本量 ${round(bucketShare == null ? null : bucketShare * 100, 1)}%`));
      findings.push(`成交量最密集的价格带在 ${round(bucketLow, 6)} – ${round(bucketHigh, 6)}，历史上这里是换手最集中的位置。`);
      if (bucketShare != null && bucketShare > 0.3) risks.push(`单一价格带吸收 ${round(bucketShare * 100, 1)}% 的成交量，价格离开该带后容易快速移动。`);
    }
    gaps.push('密集区由收盘价分桶近似得出，不是逐笔成交量分布。');
  } else gaps.push('K 线不足，未计算 VWAP 与密集区。');

  const amounts = trades.map(row => (field(row, 'price') ?? 0) * (field(row, 'quantity') ?? 0)).filter(value => value > 0).sort((a, b) => b - a);
  if (amounts.length) {
    const total = sum(amounts);
    const big = amounts.filter(value => value >= 10000);
    const bigShare = total > 0 ? sum(big) / total : null;
    metrics.push(metric('大单（≥1万）占比', `${round(bigShare == null ? null : bigShare * 100, 1)}%`, `${big.length} / ${amounts.length} 笔`));
    if (big.length) findings.push(`成交样本中有 ${big.length} 笔单笔金额超过 1 万 USDT，合计占总金额 ${round(bigShare == null ? null : bigShare * 100, 1)}%。`);
    else findings.push('成交样本中没有单笔超过 1 万 USDT 的委托，当前样本偏散户化。');
    gaps.push('大单阈值是本地固定口径，不等同于机构或主力。');
  } else gaps.push('没有成交样本，未计算大单占比。');

  return result(
    `以已读取的 ${usable.length} 根 K 线与 ${amounts.length} 笔成交计算：VWAP、成交密集区与单笔金额分布。`,
    { metrics, findings, risks, gaps, basis: '由 K 线与逐笔成交本地计算' },
  );
}

// ETF 数据 — no source is connected, so this reports the gap instead of inventing numbers.
export function analyzeEtf() {
  return {
    ready: false,
    summary: 'ETF 数据在当前工作区没有已接入的来源。本面板不生成示例净值、份额或资金流。',
    metrics: [],
    findings: [],
    risks: ['在没有 ETF 来源的情况下讨论 ETF 持仓、溢价或申赎，会把缺失资料当成事实。'],
    gaps: [
      '需要接入基金代码、跟踪指数与基金公司公告来源。',
      '需要份额规模、资产净值（NAV）与二级市场收盘价，才能计算溢折价。',
      '需要逐日申赎与资金流数据，才能判断 ETF 层面的净流入。',
    ],
    basis: '',
  };
}

export function analyzeNews(material) {
  const articles = rows(material?.articles);
  if (!articles.length) return emptyAnalysis('资讯服务没有返回文章');

  const publishers = [...new Set(articles.map(row => row.publisher || row.source).filter(value => typeof value === 'string' && value.trim()))];
  const times = articles.map(row => Date.parse(typeof row.publishedAt === 'string' ? row.publishedAt : '')).filter(Number.isFinite);
  const span = times.length > 1 ? Math.round((Math.max(...times) - Math.min(...times)) / 3600000) : null;
  const sorted = times.length ? [...times].sort((a, b) => b - a) : [];
  const newest = sorted.length ? Math.round((Date.now() - sorted[0]) / 60000) : null;

  return result(
    `已读取 ${articles.length} 条资讯，来自 ${publishers.length} 个发布方${num(newest) ? `，最新一条距今约 ${newest} 分钟` : ''}。`,
    {
      metrics: [
        metric('条数', articles.length),
        metric('发布方', publishers.length, publishers.slice(0, 4).join('、')),
        metric('时间跨度', span == null ? '不足 1 小时' : `${span} 小时`),
        metric('最新一条', num(newest) ? `${newest} 分钟前` : '发布时间未提供'),
      ],
      findings: [
        articles.length < 3 ? '样本条数很少，不足以代表当前舆情方向。' : '以下仅是已获取的标题与摘要，没有做语义聚类或情绪打分。',
        publishers.length < 2 ? '只有一个发布方，不构成交叉验证。' : `${publishers.length} 个发布方各自独立报道，同一事件的不同报道不应算作独立确认。`,
      ],
      risks: material?.stale ? ['这批资讯已标记为陈旧，用作判断可能滞后。'] : [],
      gaps: ['只读取标题与摘要，未读取全文。', '没有做情绪或主题分类，不给出舆情结论。'],
      basis: '由已读取的资讯缓存统计',
    },
  );
}

// A render-time exception used to blank the entire right panel. Analysis is
// best-effort: an unreadable snapshot degrades to a stated gap, never a crash.
export function analyzeSource(kind, material) {
  if (!material) return emptyAnalysis('该来源当前没有可读取的资料');
  try {
    if (kind === 'depth') return analyzeDepth(material);
    if (kind === 'funds') return analyzeTrades(material);
    if (kind === 'analysis') return analyzeCandles(material);
    if (kind === 'feature') return analyzeProfile(material);
    if (kind === 'news') return analyzeNews(material);
    if (kind === 'etf') return analyzeEtf(material);
    return emptyAnalysis('未知来源');
  } catch {
    return emptyAnalysis('资料格式与预期不符，本次未做计算；原始资料仍可在下方展开核对。');
  }
}

// Build the prompt from the computed readout instead of dumping raw JSON.
export function analysisQuestion(analysis, label, material) {
  const lines = [
    `请审阅「${label}」的本地计算摘要。这些数字来自已读取的公开资料快照，由本地规则计算，不是模型证据，也不代表独立核验。`,
    `摘要：${analysis.summary}`,
  ];
  if (analysis.metrics.length) lines.push('指标：' + analysis.metrics.map(row => `${row.label} ${row.value}`).join('；'));
  if (analysis.findings.length) lines.push('本地观察：' + analysis.findings.join(' '));
  if (analysis.risks.length) lines.push('已识别风险：' + analysis.risks.join(' '));
  if (analysis.gaps.length) lines.push('资料缺口：' + analysis.gaps.join(' '));
  lines.push('要求：区分事实、推断、缺失与过期风险；不得声称独立核验、完整覆盖或交易授权；不得给出确定性买卖建议。');
  if (material?.source) lines.push(`来源标识：${material.source}`);
  return lines.join('\n');
}
