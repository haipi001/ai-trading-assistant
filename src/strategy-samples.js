// Simulated strategy cases for the strategy workbench.
// Hand-authored examples, never live results. Every record carries sample:true,
// the UI badges it, and nothing here is written to storage or sent to a backend.
// The numbers are internally consistent (orders, pnl and the equity trend agree)
// but they are fabricated. A losing case is included on purpose: a page that only
// shows wins teaches the wrong thing.

export const SAMPLE_DISCLOSURE =
  '模拟案例：参数、成交与收益均为手工编写的示例，不是真实成交、不是回测结果，也不代表未来表现。';

const curve = values => values.map((value, index) => ({ index, value }));

export const SAMPLE_STRATEGIES = {
  AI网格: [
    {
      id: 'sample-grid-btc', sample: true, kind: 'AI网格',
      name: 'BTC 震荡网格', symbol: 'BTC/USDT', amount: '2000',
      currency: 'USDT', mode: '一键创建',
      detail: '58,000–72,000 · 24格 · 等差',
      status: '运行中', pnl: '+186.42', orders: 342,
      createdAt: '10-18 09:12',
      winRate: '71.3%', drawdown: '-4.18%', pairs: 342,
      equity: curve([0, 2.1, 3.4, 2.8, 4.6, 6.1, 5.2, 7.4, 8.1, 9.3]),
    },
    {
      id: 'sample-grid-eth', sample: true, kind: 'AI网格',
      name: 'ETH 宽幅网格', symbol: 'ETH/USDT', amount: '1500',
      currency: 'USDT', mode: '手动创建',
      detail: '2,800–3,600 · 32格 · 等差',
      status: '运行中', pnl: '+94.18', orders: 218,
      createdAt: '10-24 15:40',
      winRate: '64.8%', drawdown: '-6.92%', pairs: 218,
      equity: curve([0, 1.4, 2.9, 2.2, 3.5, 4.1, 3.6, 5.8, 6.3, 6.9]),
    },
    {
      id: 'sample-grid-sol', sample: true, kind: 'AI网格',
      name: 'SOL 高频网格', symbol: 'SOL/USDT', amount: '800',
      currency: 'USDT', mode: '手动创建',
      detail: '130–190 · 40格 · 等差',
      status: '已暂停', pnl: '-42.60', orders: 511,
      createdAt: '10-29 11:03',
      winRate: '48.2%', drawdown: '-12.40%', pairs: 511,
      equity: curve([0, 1.2, 0.4, -1.8, -0.9, -3.2, -4.1, -3.4, -5.2, -5.3]),
    },
  ],

  现货DCA: [
    {
      id: 'sample-dca-btc', sample: true, kind: '现货DCA',
      name: 'BTC 每日定投', symbol: 'BTC/USDT', amount: '200',
      currency: 'USDT', mode: '一键创建 · 每天',
      detail: '止盈 20% · 无首次延迟',
      status: '运行中', pnl: '+412.80', orders: 48,
      createdAt: '09-02 08:00',
      winRate: '—', drawdown: '-8.60%', pairs: 48,
      equity: curve([0, 3.2, 1.4, 6.8, 5.1, 9.4, 12.6, 11.2, 15.8, 17.4]),
    },
    {
      id: 'sample-dca-eth', sample: true, kind: '现货DCA',
      name: 'ETH 每周定投', symbol: 'ETH/USDT', amount: '500',
      currency: 'USDT', mode: '手动创建 · 每周',
      detail: '止盈 25% · 首期已执行',
      status: '运行中', pnl: '+168.35', orders: 22,
      createdAt: '08-16 10:30',
      winRate: '—', drawdown: '-5.20%', pairs: 22,
      equity: curve([0, 1.8, 3.4, 2.6, 4.9, 5.5, 4.8, 7.1, 8.2, 8.9]),
    },
    {
      id: 'sample-dca-sol', sample: true, kind: '现货DCA',
      name: 'SOL 定投（已终止）', symbol: 'SOL/USDT', amount: '100',
      currency: 'USDT', mode: '一键创建 · 每天',
      detail: '止盈 15% · 累计 31 期',
      status: '已终止', pnl: '-76.20', orders: 31,
      createdAt: '07-11 09:00', stoppedAt: '10-12 16:22',
      winRate: '—', drawdown: '-14.30%', pairs: 31,
      equity: curve([0, 1.1, -0.6, -2.4, -1.8, -4.2, -5.9, -4.8, -3.1, -2.9]),
    },
  ],

  合约DCA: [
    {
      id: 'sample-fdca-btc', sample: true, kind: '合约DCA',
      name: 'BTC 做多DCA', symbol: 'BTC/USDT', amount: '600',
      currency: 'USDT', mode: '平衡型 · 做多 · 3x',
      detail: '每4小时 · 每2.5%加仓 · 8%止盈',
      status: '运行中', pnl: '+238.55', orders: 36,
      createdAt: '10-08 13:20',
      winRate: '58.3%', drawdown: '-9.40%', pairs: 36,
      equity: curve([0, 2.8, 4.1, 3.2, 6.4, 7.8, 6.9, 8.8, 10.2, 11.1]),
    },
    {
      id: 'sample-fdca-eth', sample: true, kind: '合约DCA',
      name: 'ETH 做空DCA（已终止）', symbol: 'ETH/USDT', amount: '400',
      currency: 'USDT', mode: '保守型 · 做空 · 2x',
      detail: '每天 · 每3.0%加仓 · 6%止盈',
      status: '已终止', pnl: '-118.40', orders: 14,
      createdAt: '09-19 20:05', stoppedAt: '10-03 07:41',
      winRate: '35.7%', drawdown: '-29.60%', pairs: 14,
      equity: curve([0, -1.4, -3.8, -2.9, -7.2, -9.6, -8.1, -11.4, -12.8, -19.2]),
    },
  ],

  指标实盘: [
    {
      id: 'sample-live-td', sample: true, kind: '指标实盘',
      name: 'TD序列反转 · BTC', symbol: 'BTC/USDT', amount: '3000',
      currency: 'USDT', mode: '5分 · TD信号',
      detail: 'TD 超买超卖反转，单位置手数 0.01',
      status: '运行中', pnl: '+86.30', orders: 27,
      createdAt: '10-25 21:14',
      winRate: '55.6%', drawdown: '-3.90%', pairs: 27,
      equity: curve([0, 0.9, 1.8, 1.2, 2.4, 1.9, 3.1, 3.6, 3.0, 2.9]),
    },
    {
      id: 'sample-live-ma', sample: true, kind: '指标实盘',
      name: '均线突破 · ETH', symbol: 'ETH/USDT', amount: '2000',
      currency: 'USDT', mode: '15分 · MA交叉',
      detail: 'MA5 上穿 MA20 开多，反向平仓',
      status: '已暂停', pnl: '-31.75', orders: 19,
      createdAt: '10-21 14:38',
      winRate: '47.4%', drawdown: '-7.10%', pairs: 19,
      equity: curve([0, 0.6, -1.2, -0.4, -1.9, -2.6, -1.8, -1.1, -1.6, -1.6]),
    },
  ],
};

export const SAMPLE_BACKTESTS = [
  {
    id: 'sample-bt-td', sample: true,
    name: 'TD超卖反转', symbol: 'BTC/USDT', period: '5分', range: '近90天',
    return: '+18.42%', drawdown: '-6.83%', winRate: '62.5%', trades: 48, ratio: '1.84',
    benchmark: '+4.10%',
    note: '在震荡区间表现较好；单边下跌时连续加仓的暴露未单独统计。',
    equity: curve([0, 2.4, 5.1, 4.2, 7.8, 9.6, 8.9, 13.2, 15.8, 18.4]),
  },
  {
    id: 'sample-bt-ma', sample: true,
    name: 'RSI均线交叉', symbol: 'ETH/USDT', period: '15分', range: '近90天',
    return: '+9.76%', drawdown: '-4.21%', winRate: '58.3%', trades: 36, ratio: '1.52',
    benchmark: '+2.85%',
    note: '交叉信号在盘整段反复触发，实际成交次数高于信号次数。',
    equity: curve([0, 1.2, 3.0, 2.4, 4.6, 5.8, 5.1, 7.4, 8.6, 9.8]),
  },
  {
    id: 'sample-bt-volume', sample: true,
    name: '成交量突破', symbol: 'SOL/USDT', period: '1时', range: '近90天',
    return: '-3.18%', drawdown: '-11.40%', winRate: '44.0%', trades: 62, ratio: '0.86',
    benchmark: '+6.20%',
    note: '失败案例：跑输基准，高频突破在低流动性时段滑点显著。',
    equity: curve([0, 1.8, -0.4, -2.9, -1.2, -4.6, -6.1, -4.8, -2.6, -3.2]),
  },
];

export const SAMPLE_BASKETS = [
  {
    id: 'sample-basket-entry', sample: true,
    name: '分批建仓',
    note: '三个标的同时挂限价买单，适合把一笔资金拆到多个币种。',
    rows: [
      { pair: 'BTC/USDT', side: '买入', type: '限价', price: '63200', amount: '0.02' },
      { pair: 'ETH/USDT', side: '买入', type: '限价', price: '3180', amount: '0.4' },
      { pair: 'SOL/USDT', side: '买入', type: '限价', price: '146', amount: '8' },
    ],
  },
  {
    id: 'sample-basket-hedge', sample: true,
    name: '对冲减仓',
    note: '一边卖出高波动持仓，一边买入低波动标的，降低组合整体 beta。',
    rows: [
      { pair: 'BTC/USDT', side: '卖出', type: '限价', price: '68000', amount: '0.01' },
      { pair: 'ETH/USDT', side: '卖出', type: '市价', price: '', amount: '0.2' },
      { pair: 'USDC/USDT', side: '买入', type: '限价', price: '1.0', amount: '900' },
    ],
  },
  {
    id: 'sample-basket-rebalance', sample: true,
    name: '轮动调仓',
    note: '把涨幅过大的标的换成滞涨的，配置比例按目标权重执行。',
    rows: [
      { pair: 'SOL/USDT', side: '卖出', type: '限价', price: '178', amount: '12' },
      { pair: 'ETH/USDT', side: '买入', type: '限价', price: '3240', amount: '0.65' },
    ],
  },
];

// Samples are merged at render time so user data is never polluted by examples.
// A sample disappears once the user copies it into their own list.
export function samplesFor(kind, existing = []) {
  const list = SAMPLE_STRATEGIES[kind] || [];
  const copied = new Set(existing.map(item => item.sampleFrom).filter(Boolean));
  return list.filter(item => !copied.has(item.id));
}

export function copySample(item) {
  const { sample, sampleFrom, equity, ...rest } = item;
  return {
    ...rest,
    id: Date.now() + Math.floor(Math.random() * 1000),
    sampleFrom: sampleFrom || item.id,
    status: item.status === '已终止' ? '运行中' : item.status,
    stoppedAt: undefined,
    createdAt: '刚刚',
  };
}

// Ratio of the last value to the largest absolute value, clamped, so a losing
// curve still draws inside the same box instead of collapsing to a flat line.
export function curvePath(equity, width = 100, height = 28) {
  if (!Array.isArray(equity) || equity.length < 2) return null;
  const values = equity.map(point => point.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - ((value - min) / span) * height;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return { points: points.join(' '), positive: values[values.length - 1] >= 0, last: values[values.length - 1] };
}
