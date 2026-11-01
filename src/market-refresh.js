// Schedule after completion: slow requests never overlap. Hidden pages stop polling.
export function observeMarketSnapshot(load, receive, environment = {}) {
  const schedule = environment.schedule || setTimeout;
  const cancel = environment.cancel || clearTimeout;
  const page = environment.page || document;
  let stopped = false, running = false, timer = null, controller = null;
  const run = async () => {
    if (stopped || running || page.visibilityState === 'hidden') return;
    if (timer !== null) { cancel(timer); timer = null; }
    running = true;
    controller = new AbortController();
    try {
      const result = await load(controller.signal);
      if (!stopped) receive(result);
    } catch {
      if (!stopped) receive({status:'offline',candles:[],source:'行情刷新失败'});
    } finally {
      running = false;
      if (!stopped && page.visibilityState !== 'hidden') timer = schedule(run, 30000);
    }
  };
  const visibility = () => {
    if (timer !== null) { cancel(timer); timer = null; }
    if (page.visibilityState !== 'hidden') void run();
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
