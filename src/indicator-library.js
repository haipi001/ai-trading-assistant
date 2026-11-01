export const INDICATOR_FAVORITES_KEY = "ai-trading-assistant-indicator-favorites-v1";
export const INDICATORS = [
  ["清算热力图", "追踪潜在清算密集区域", "NEW", "市场指数"],
  ["主力大单跟踪", "识别大额主动成交与方向", "PRO", "特色指标"],
  ["聪明钱追踪", "将链上交易与持仓轨迹标到 K 线", "PRO", "特色指标"],
  ["巨鲸追踪", "跟踪巨鲸在链上与交易所的转账行为", "PRO", "特色指标"],
  ["BOLL", "布林线", "", "技术指标"], ["EMA", "指数平滑移动平均线", "", "技术指标"],
  ["MA", "移动平均线", "", "技术指标"], ["MACD", "指数平滑异同移动平均线", "", "技术指标"],
  ["筹码分布", "筹码分布图", "PRO", "市场指数"], ["VWAP", "成交量加权平均价", "", "技术指标"],
];
export const RENDERED_INDICATORS = new Set(["BOLL", "EMA", "MA", "MACD", "VWAP"]);
export function readIndicatorFavorites(storage) {
  const raw = storage.getItem(INDICATOR_FAVORITES_KEY);
  if (raw === null) return [];
  let data;
  try { data = JSON.parse(raw); } catch { throw new Error("指标收藏格式损坏，原数据未改写"); }
  if (data?.schema !== 1 || !Array.isArray(data.items) || data.items.length > 200 || data.items.some(value => typeof value !== "string" || value.length > 100) || new Set(data.items).size !== data.items.length) throw new Error("指标收藏结构不支持，原数据未改写");
  return data.items;
}
export function toggleIndicatorFavorite(storage, name) {
  if (typeof name !== "string" || !name || name.length > 100) throw new Error("收藏名称无效");
  const current = readIndicatorFavorites(storage);
  const items = current.includes(name) ? current.filter(item => item !== name) : [...current, name];
  if (items.length > 200) throw new Error("收藏已达200项上限");
  storage.setItem(INDICATOR_FAVORITES_KEY, JSON.stringify({ schema: 1, items }));
  return items;
}
export function filterIndicatorLibrary({ section = "全部", category = "全部", query = "", favorites = [], studies = [] } = {}) {
  return INDICATORS.filter(item => (section !== "收藏" || favorites.includes(item[0])) &&
    (section !== "快捷" || studies.includes(item[0])) && (category === "全部" || item[3] === category) &&
    `${item[0]} ${item[1]}`.toLowerCase().includes(query.trim().toLowerCase()));
}
