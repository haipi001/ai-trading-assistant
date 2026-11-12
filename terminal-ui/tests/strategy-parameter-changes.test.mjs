import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyParameterChanges} from '../../src/strategy-parameter-changes.js';
test('parameter proposals require exact original values and cannot change execution identity',()=>{
 const material={parameters:{trigger:'weekly',amount:'100'}};
 const valid={field:'trigger',before:'weekly',after:'monthly',rationale:'Budget review',citation_ids:['SP1']};
 assert.equal(strategyParameterChanges([valid],material)[0],valid);
 for(const patch of [{field:'account_id'},{before:'old'},{after:''},{citation_ids:['SP2']},{run:true}])assert.throws(()=>strategyParameterChanges([{...valid,...patch}],material));
 assert.throws(()=>strategyParameterChanges([valid,valid],material));
 assert.throws(()=>strategyParameterChanges([{...valid,field:'amount',before:'100',after:'Infinity'}],material));
});

test('grid proposals are combined, validated, and copied without mutating original bounds',async()=>{
 const {applyStrategyChanges}=await import('../../src/strategy-parameter-changes.js');
 const material={parameters:{amount:'100',grid:{kind:'arithmetic_grid',lower:'100',upper:'200',intervals:10}}};
 const change={field:'grid.upper',before:'200',after:'250',rationale:'Review a hypothetical range',citation_ids:['SP1']};
 strategyParameterChanges([change],material);const proposed=applyStrategyChanges(material.parameters,[change]);
 assert.equal(proposed.grid.upper,'250');assert.equal(material.parameters.grid.upper,'200');
 assert.throws(()=>strategyParameterChanges([{...change,after:'99'}],material));
 assert.throws(()=>strategyParameterChanges([{...change,field:'grid.intervals',before:'10',after:'2.5'}],material));
 assert.throws(()=>strategyParameterChanges([{...change,field:'grid.lower',before:'100',after:'300'}],material));
});

test('DCA frequency and optional conditions can be reviewed without scheduling or mutating original plans',async()=>{
 const {applyStrategyChanges}=await import('../../src/strategy-parameter-changes.js');
 const material={parameters:{amount:'100',dca:{kind:'spot_dca',frequency:'每周',first_run_local:'2027-01-02T09:30',take_profit_percent:'20'}}};
 const change={field:'dca.frequency',before:'每周',after:'每月',rationale:'User cadence review',citation_ids:['SP1']};
 const remove={...change,field:'dca.take_profit_percent',before:'20',after:''};
 strategyParameterChanges([change,remove],material);const proposed=applyStrategyChanges(material.parameters,[change,remove]);
 assert.equal(proposed.dca.frequency,'每月');assert.equal(proposed.dca.take_profit_percent,undefined);assert.equal(material.parameters.dca.frequency,'每周');
 assert.throws(()=>strategyParameterChanges([{...change,after:'每秒'}],material));
 assert.throws(()=>strategyParameterChanges([{...change,field:'dca.first_run_local',before:'2027-01-02T09:30',after:'2027-02-30T09:30'}],material));
});
