export const NAV_GROUPS=Object.freeze(['总览','行情','资讯','研究','资产','交易','设置与工具']);
export function defaultNavigationGroup(code,page){
 if(page)return ({home:'总览',market:'行情',flash:'资讯',news:'资讯',strategy:'研究',chain:'研究',assets:'资产',auth:'设置与工具',data:'设置与工具',more:'设置与工具'})[page]||'设置与工具';
 if(['WEI','W','MOST','MAP','FX','GOV','CMDT','GP','HP','DEPTH'].includes(code))return '行情';
 if(['TOP','N','ECO','MSG','INBOX'].includes(code))return '资讯';
 if(['DES','FA','OPT','COMP','EQS','SRCH','FLDS'].includes(code))return '研究';
 if(code==='PORT')return '资产';
 if(['ORD','TRD','ALRT'].includes(code))return '交易';
 return '设置与工具';
}
export function cleanNavigationGroups(value,codes){return Object.fromEntries(Object.entries(value&&typeof value==='object'?value:{}).filter(([id,label])=>codes.includes(id)&&typeof label==='string'&&label.trim().length>0&&label.length<=32).map(([id,label])=>[id,label.trim()]));}
