import {panelVisibility} from './panel-visibility.js';
// Schedule after completion: slow requests never overlap. Hidden pages stop polling.
export function observeMarketSnapshot(load, receive, environment = {}) {
  const schedule = environment.schedule || setTimeout;
  const cancel = environment.cancel || clearTimeout;
  const page = environment.page || panelVisibility(document);
  let stopped = false, running = false, timer = null, controller = null, resumeRequested = false;
  const run = async () => {
    if (stopped || running || page.visibilityState === 'hidden') return;
    if (timer !== null) { cancel(timer); timer = null; }
    running = true;
    controller = new AbortController();
    try {
      const result = await load(controller.signal);
      if (!stopped && !controller.signal.aborted && page.visibilityState !== 'hidden') receive(result);
    } catch {
      if (!stopped && !controller.signal.aborted && page.visibilityState !== 'hidden') receive({status:'offline',candles:[],source:'行情刷新失败'});
    } finally {
      running = false;
      if(!stopped&&page.visibilityState!=='hidden'){if(resumeRequested){resumeRequested=false;void run();}else timer=schedule(run,30000);}
    }
  };
  const visibility = () => {
    if (timer !== null) { cancel(timer); timer = null; }
    if(page.visibilityState==='hidden'){controller?.abort();resumeRequested=false;}else if(running&&controller?.signal.aborted)resumeRequested=true;else void run();
  };
  page.addEventListener('visibilitychange', visibility);
  void run();
  return () => {
    stopped = true;
    if (timer !== null) cancel(timer);
    controller?.abort();
    page.removeEventListener('visibilitychange', visibility);
  };
}
