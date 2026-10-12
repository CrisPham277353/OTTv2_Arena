/** One polling session. Switching targets cancels pending fetches and old timers. */
export function createPoller({load, apply, onError, delay=250, schedule=setTimeout, cancel=clearTimeout}) {
  let generation=0, timer=null, controller=null;
  function stop() {
    generation++;
    if(timer!==null)cancel(timer);
    timer=null;
    controller?.abort();controller=null;
  }
  async function start(key) {
    stop();const session=generation;
    controller=new AbortController();const signal=controller.signal;
    const isCurrent=()=>session===generation;
    async function poll() {
      try {
        const data=await load(key,signal);
        if(!isCurrent())return;
        const again=await apply(data,isCurrent);
        if(isCurrent() && again)timer=schedule(()=>{timer=null;poll();},delay);
      } catch(error) {if(isCurrent())onError(error);}
    }
    await poll();
  }
  return {start,stop};
}
