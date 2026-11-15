import {newsSnapshot} from './news-feed-model.js';
export function subscriptionStale(row,now=Date.now()){
 const at=Date.parse(row.fetched_at||'');return row.status!=='ready'||!Number.isFinite(at)||now-at>row.refresh_seconds*2000;
}
export function subscriptionArticles(rows,now=Date.now()){
 return rows.flatMap(row=>{
  const data=newsSnapshot({provider:'panews',status:'ready',articles:(row.result?.articles||[]).slice(0,100)});
  return data.articles.map(item=>({...item,id:`subscription:${row.id}:${item.id}`,sourceId:`subscription:${row.id}`,publisher:row.name,sourceStale:subscriptionStale(row,now),sourceFailed:row.status==='error',sourceFetchedAt:row.fetched_at}));
 });
}
export function mergeSubscriptionNews(data,rows,now=Date.now()){
 const custom=subscriptionArticles(rows,now);
 if(!data&&!custom.length)return data;
 const base=data||{articles:[],source_status:[],provider:'custom',status:'ready',settings:{auto_refresh:false},errors_count:0};
 const seen=new Set();
 const articles=[...base.articles,...custom].sort((a,b)=>(b.publishedAt||'').localeCompare(a.publishedAt||'')).filter(row=>{const key=`${row.kind}:${row.url}`;if(seen.has(key))return false;seen.add(key);return true;});
 const fetchedAt=[base.fetchedAt,...rows.map(row=>row.fetched_at)].filter(value=>value&&Number.isFinite(Date.parse(value))).sort((a,b)=>Date.parse(b)-Date.parse(a))[0]||null;
 return {...base,articles,fetchedAt,customSources:rows,errors_count:(base.errors_count||0)+rows.filter(row=>row.status==='error').length};
}
