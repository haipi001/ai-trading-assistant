// Position sizing and risk arithmetic for the rail calculator.
// Pure functions: every output is derived from what the user typed. A missing
// input stays null and is reported, never silently filled with a default.

const finite = value => {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

export const RISK_PRESETS = [0.5, 1, 1.5, 2];

// Size a position from the money the trader is willing to lose.
export function positionSize({ account, riskPercent, entry, stop, takeProfit, side = '买入' }) {
  const capital = finite(account);
  const percent = finite(riskPercent);
  const price = finite(entry);
  const stopPrice = finite(stop);
  const target = finite(takeProfit);
  const long = side !== '卖出';

  const gaps = [];
  if (capital === null || capital <= 0) gaps.push('需要填写大于 0 的账户权益');
  if (percent === null || percent <= 0) gaps.push('需要填写大于 0 的单笔风险比例');
  if (price === null || price <= 0) gaps.push('需要填写大于 0 的进场价');
  if (stopPrice === null || stopPrice <= 0) gaps.push('需要填写大于 0 的止损价');
  if (gaps.length) return { ready: false, gaps, metrics: [], warnings: [] };

  const riskAmount = (capital * percent) / 100;
  const perUnit = long ? price - stopPrice : stopPrice - price;

  if (perUnit === 0) {
    return { ready: false, gaps: ['止损价不能等于进场价'], metrics: [], warnings: [] };
  }
  if (perUnit < 0) {
    return {
      ready: false,
      gaps: [long ? '买入时止损价必须低于进场价' : '卖出时止损价必须高于进场价'],
      metrics: [],
      warnings: [],
    };
  }

  const quantity = riskAmount / perUnit;
  const notional = quantity * price;
  const leverage = capital > 0 ? notional / capital : null;
  const stopDistance = (perUnit / price) * 100;

  const warnings = [];
  if (leverage !== null && leverage > 1) warnings.push(`名义金额是权益的 ${leverage.toFixed(2)} 倍，需要 ${leverage.toFixed(2)} 倍杠杆或更多保证金。`);
  if (stopDistance < 0.5) warnings.push(`止损距离只有 ${stopDistance.toFixed(2)}%，正常波动就可能触发，容易被噪声洗出。`);
  if (stopDistance > 20) warnings.push(`止损距离 ${stopDistance.toFixed(2)}% 偏大，单笔波动风险相应放大。`);
  if (leverage !== null && leverage > 3) warnings.push('杠杆超过 3 倍，一次接近止损的跳空就可能超出计划亏损。');

  const metrics = [
    { label: '可亏金额', value: riskAmount.toFixed(2) },
    { label: '持仓数量', value: quantity.toFixed(6) },
    { label: '名义金额', value: notional.toFixed(2) },
    { label: '止损距离', value: `${stopDistance.toFixed(2)}%` },
    { label: '占用权益', value: `${(leverage === null ? 0 : leverage * 100).toFixed(1)}%` },
  ];

  if (target !== null && target > 0) {
    const rewardPerUnit = long ? target - price : price - target;
    if (rewardPerUnit > 0) {
      const reward = rewardPerUnit * quantity;
      metrics.push({ label: '潜在盈利', value: reward.toFixed(2) });
      metrics.push({ label: '盈亏比', value: `${(reward / riskAmount).toFixed(2)} : 1` });
      if (reward / riskAmount < 1.5) warnings.push('盈亏比低于 1.5:1，需要较高胜率才能长期为正。');
    } else {
      warnings.push(long ? '买入时止盈价应高于进场价，当前未计算潜在盈利。' : '卖出时止盈价应低于进场价，当前未计算潜在盈利。');
    }
  }

  return { ready: true, gaps: [], metrics, warnings, riskAmount, quantity, notional, leverage };
}

// What a sequence of losses does to the account — the part traders underestimate.
export function drawdownTable({ account, riskPercent, losses = 10 }) {
  const capital = finite(account);
  const percent = finite(riskPercent);
  if (capital === null || capital <= 0 || percent === null || percent <= 0) return [];
  const rows = [];
  let equity = capital;
  const step = Math.max(1, Math.floor(losses / 5));
  for (let index = 1; index <= losses; index += 1) {
    equity -= (equity * percent) / 100;
    if (index % step === 0 || index === losses) {
      rows.push({
        round: index,
        equity: equity.toFixed(2),
        drawdown: (((capital - equity) / capital) * 100).toFixed(2),
        recovery: equity > 0 ? (((capital - equity) / equity) * 100).toFixed(2) : null,
      });
    }
  }
  return rows;
}

// Recovery percent required to get back to break-even after a drawdown.
export function recoveryNeeded(drawdownPercent) {
  const value = finite(drawdownPercent);
  if (value === null || value <= 0 || value >= 100) return null;
  return ((value / (100 - value)) * 100).toFixed(2);
}
