import {spotDcaConfiguration} from './spot-dca-configuration.js';
import {gridConfiguration,checkGridParameters} from './grid-parameter-check.js';
const limits={amount:30,risk:64,trigger:200,invalidation:200,constraints:400,'grid.lower':30,'grid.upper':30,'grid.intervals':3,'dca.frequency':8,'dca.first_run_local':19,'dca.take_profit_percent':30};
export function applyStrategyChanges(parameters,changes){
 const result=structuredClone(parameters);
 for(const c of changes){if(c.field.startsWith('grid.'))result.grid[c.field.slice(5)]=c.field==='grid.intervals'?Number(c.after):c.after;else if(c.field.startsWith('dca.')){const key=c.field.slice(4);if(c.after===''&&key!=='frequency')delete result.dca[key];else result.dca[key]=c.after;}else result[c.field]=c.after;}
 return result;
}
export function strategyParameterChanges(changes,material){
 if(!Array.isArray(changes)||changes.length>8)throw Error('invalid strategy changes');
 const seen=new Set();
 for(const c of changes){
  const dcaKey=c?.field?.startsWith('dca.')?c.field.slice(4):null,optionalDca=['first_run_local','take_profit_percent'].includes(dcaKey);
  if(dcaKey&&!material?.parameters?.dca)throw Error('missing DCA source');
  const original=dcaKey?(material.parameters.dca[dcaKey]??''):c?.field?.startsWith('grid.')?material?.parameters?.grid?.[c.field.slice(5)]:material?.parameters?.[c?.field];
  if(!c||Object.keys(c).sort().join(',')!=='after,before,citation_ids,field,rationale'||!Object.hasOwn(limits,c.field)||original==null||seen.has(c.field)||c.before!==String(original)||typeof c.after!=='string'||(!c.after.trim()&&!(optionalDca&&c.after===''))||c.after===c.before||c.after.length>limits[c.field]||typeof c.rationale!=='string'||!c.rationale.trim()||c.rationale.length>600||JSON.stringify(c.citation_ids)!=='["SP1"]')throw Error('invalid strategy change');
  if(c.field==='amount'&&(!/^\d{1,16}(\.\d{1,12})?$/.test(c.after)||Number(c.after)<=0))throw Error('invalid proposed amount');
  if(c.field==='grid.intervals'&&!/^[1-9][0-9]{0,2}$/.test(c.after))throw Error('invalid proposed grid count');
  seen.add(c.field);
 }
 const proposed=applyStrategyChanges(material.parameters,changes);
 if(proposed.grid){gridConfiguration(proposed.grid);checkGridParameters({lower:proposed.grid.lower,upper:proposed.grid.upper,gridCount:String(proposed.grid.intervals),amount:proposed.amount});}
 if(proposed.dca)spotDcaConfiguration(proposed.dca);
 return changes;
}
