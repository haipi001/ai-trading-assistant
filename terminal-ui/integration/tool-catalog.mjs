// Only tools backed by existing handlers appear here. Labels do not promise unavailable sources.
export const TOOL_CATALOG=Object.freeze([
 {id:'ai',label:'AI 资料分析',en:'AI material analysis',icon:'AI',role:'research'},
 {id:'research',label:'AI 任务与记录',en:'AI tasks and records',icon:'◷',role:'tasks'},
 {id:'notes',label:'本机笔记',en:'Local notes',icon:'✎',role:'utility'},
 {id:'calculator',label:'风险计算器',en:'Risk calculator',icon:'∑',role:'utility'},
 {id:'news',label:'资讯速览',en:'News briefing',icon:'▤',role:'context'},
 {id:'depth',label:'深度与成交',en:'Depth and trades',icon:'≡',role:'context'},
 {id:'funds',label:'资金流向',en:'Money flow',icon:'$',role:'context'},
 {id:'analysis',label:'技术分析',en:'Technical analysis',icon:'↗',role:'context'},
 {id:'trade',label:'快捷下单',en:'Order ticket',icon:'⇄',role:'execution'},
 {id:'feature',label:'特色数据',en:'Special data',icon:'▥',role:'context'},
 {id:'etf',label:'ETF 数据',en:'ETF data',icon:'ETF',role:'context'},
 {id:'sidebarLayout',label:'面板布局',en:'Panel layout',icon:'▦',role:'layout'},
 {id:'help',label:'帮助中心',en:'Help',icon:'?',role:'help'}
].map(Object.freeze));
