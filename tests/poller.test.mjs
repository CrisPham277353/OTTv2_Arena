import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPoller} from '../arena/web/static/poller.js';

function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function clock(){const tasks=new Map();let next=0;return {tasks,schedule:(fn,delay)=>{tasks.set(++next,{fn,delay});return next;},cancel:id=>tasks.delete(id)};}

test('switching matches aborts old loads and ignores their late responses',async()=>{
  const pending=new Map(),applied=[],errors=[],timers=clock();
  const poller=createPoller({load:(key,signal)=>{const request=deferred();pending.set(key,{...request,signal});return request.promise;},
    apply:data=>{applied.push(data);return true;},onError:e=>errors.push(e),...timers});
  const old=poller.start('old'),current=poller.start('new');
  assert.equal(pending.get('old').signal.aborted,true);
  pending.get('new').resolve('new board');await current;
  pending.get('old').resolve('old board');await old;
  assert.deepEqual(applied,['new board']);assert.equal(timers.tasks.size,1);assert.deepEqual(errors,[]);
  poller.stop();assert.equal(timers.tasks.size,0);
});

test('a cancelled renderer load cannot publish a stale board or restart polling',async()=>{
  const rendering=deferred(),entered=deferred(),boards=[],timers=clock();
  const poller=createPoller({load:async()=>({match:'one'}),apply:async(data,isCurrent)=>{
    entered.resolve();await rendering.promise;if(isCurrent())boards.push(data);return true;
  },onError:assert.fail,...timers});
  const request=poller.start('one');await entered.promise;poller.stop();rendering.resolve();await request;
  assert.deepEqual(boards,[]);assert.equal(timers.tasks.size,0);
});

test('errors from the old match do not affect the current viewer',async()=>{
  const old=deferred(),errors=[],boards=[];
  const poller=createPoller({load:key=>key==='old'?old.promise:Promise.resolve('current'),
    apply:data=>{boards.push(data);return false;},onError:e=>errors.push(e.message)});
  const first=poller.start('old');await poller.start('new');old.reject(new Error('old failure'));await first;
  assert.deepEqual(boards,['current']);assert.deepEqual(errors,[]);poller.stop();
});

test('completed matches stop polling and current errors are reported once',async()=>{
  const errors=[],timers=clock();let loads=0;
  const poller=createPoller({load:async key=>{loads++;if(key==='bad')throw new Error('network');return key;},
    apply:()=>false,onError:e=>errors.push(e.message),...timers});
  await poller.start('completed');assert.equal(timers.tasks.size,0);
  await poller.start('bad');assert.equal(loads,2);assert.deepEqual(errors,['network']);assert.equal(timers.tasks.size,0);
  poller.stop();
});
