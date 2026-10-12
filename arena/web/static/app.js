import {initTournaments} from './tournaments.js?v=review-1';
import {createPoller} from './poller.js?v=1';
const $ = id => document.getElementById(id);
let previewRequest=0;
let bots = [], replay = null, gameIndex = 0, frameIndex = 0, renderer = null, timer = null, activeMatch = null, preview = null, loadingReplay = 0, gameCatalog = [];
const reasons = {GOAL_REACHED:'Đến đích', ARMY_ELIMINATED:'Ăn hết toàn bộ quân', NO_PROGRESS:'Thua do 15 lượt riêng không tiến bộ', TYPE_ELIMINATED:'Xóa một loại quân', NO_LEGAL_MOVES:'Đối phương hết nước đi', ADJUDICATED:'Phân xử', BOT_FORFEIT:'Bot bị xử thua'};
const triggers = {THREEFOLD_REPETITION:'Lặp bàn cờ 3 lần', NO_CAPTURE_LIMIT:'50 lượt không ăn quân', PLY_LIMIT:'Đạt 300 lượt'};
const statuses = {SCHEDULED:'CHỜ LỊCH GIẢI', QUEUED:'ĐANG CHỜ', RUNNING:'ĐANG THI ĐẤU', COMPLETED:'ĐÃ HOÀN TẤT', FAILED:'LỖI HỆ THỐNG', INTERRUPTED:'BỊ GIÁN ĐOẠN'};
async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const failure=new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
    failure.status=response.status;throw failure;
  }
  return data;
}
function text(id, value) { $(id).textContent = value; }
function error(message) { $('error').hidden = !message; text('error', message || ''); }
function name(id) { return bots.find(b => b.id === id)?.name || id; }
function showPressure(state) {
  const value=renderer?.pressureLabel?.(state)||'';text('pressure-status',value);$('pressure-status').hidden=!value;
}
function showRules(metadata,version) {
  const rules=metadata?.ruleSummary || gameCatalog.find(g=>g.gameVersion===version)?.ruleSummary || [];
  $('rule-summary').replaceChildren(...rules.map(line=>{const p=document.createElement('p');p.textContent=line;return p}));
}
function option(value, label) { const el = document.createElement('option'); el.value = value; el.textContent = label; return el; }
function pause() { clearTimeout(timer); timer = null; text('play', '▶ Phát'); }
function currentGame() { return replay?.games[gameIndex]; }
function currentState() { const game = currentGame(); return frameIndex === 0 ? game.initialState : game.frames[frameIndex - 1].state; }
function setFrame(index) {
  const game = currentGame(); if (!game) return;
  frameIndex = Math.max(0, Math.min(index, game.frames.length));
  const state = currentState(); renderer.render($('board'), state, game.renderMetadata);showPressure(state);
  $('scrub').value = frameIndex; text('frame-label', `${frameIndex} / ${game.frames.length}`);
  const ended = frameIndex === game.frames.length;
  const slot = game.sideMapping[state.sideToMove];
  text('turn-label', ended ? `Kết thúc · ${name(game.result.winnerBot)} thắng` : `Lượt ${state.ply + 1} · ${state.sideToMove} / ${name(game.botNames[slot])}`);
  $('prev').disabled = frameIndex === 0; $('next').disabled = ended;
  text('move-detail', frameIndex ? `#${game.frames[frameIndex-1].ply} · ${game.frames[frameIndex-1].playerId}: ${renderer.describe(game.frames[frameIndex-1])}` : 'Bố trí ban đầu · 9 quân mỗi bên');
  document.querySelectorAll('.move-row').forEach(el => el.classList.toggle('active', Number(el.dataset.frame) === frameIndex));
  const active = $('move-list').querySelector('.active'); if (active) $('move-list').scrollTop = active.offsetTop - $('move-list').offsetTop - 80;
}
function tick() {
  setFrame(frameIndex + 1);
  if (frameIndex >= currentGame().frames.length) { pause(); return; }
  timer = setTimeout(tick, 650 / Number($('speed').value));
}
function play() {
  if (!currentGame()) return;
  if (timer) { pause(); return; }
  if (frameIndex === currentGame().frames.length) setFrame(0);
  text('play', 'Ⅱ Tạm dừng'); timer = setTimeout(tick, 650 / Number($('speed').value));
}
function selectGame(index) {
  pause(); gameIndex = index; const game = currentGame();
  if (!game) return;
  showRules(game.renderMetadata,game.gameVersion);
  text('side-a', name(game.botNames[game.sideMapping.A])); text('side-b', name(game.botNames[game.sideMapping.B]));
  text('role-a', `Bên A · ${game.sideMapping.A === 'botA' ? 'Bot #1' : 'Bot #2'} · Đi trước · đích i9`);
  text('role-b', `Bên B · ${game.sideMapping.B === 'botA' ? 'Bot #1' : 'Bot #2'} · đích a1`);
  $('scrub').max = game.frames.length; $('scrub').disabled = false; $('play').disabled = false;
  text('move-count', `${game.result.plies} lượt`);
  const rows = game.frames.map((frame, i) => {
    const row = document.createElement('button'); row.className = 'move-row'; row.dataset.frame = i + 1;
    const values = [`${frame.ply}`, frame.playerId, renderer.describe(frame), frame.events.some(e => e.type === 'PIECE_CAPTURED') ? 'ĂN QUÂN' : ''];
    values.forEach((value, j) => { const span = document.createElement('span'); span.textContent = value; if (j===1) span.className = frame.playerId.toLowerCase(); row.append(span); });
    row.addEventListener('click', () => { pause(); setFrame(i + 1); }); return row;
  });
  $('move-list').replaceChildren(...rows); setFrame(0);
}
async function loadReplay(matchId, auto = false) {
  pause(); error('');
  const loadId = ++loadingReplay;
  const data = await api(`/api/matches/${matchId}/replay`);
  // A user may select a different history entry while a previous request is in flight.
  if (activeMatch !== matchId || loadId !== loadingReplay) return;
  const loadedRenderer = await import(data.replayRenderer);
  if (activeMatch !== matchId || loadId !== loadingReplay) return;
  replay = data;
  renderer = loadedRenderer;
  $('game-select').replaceChildren(...data.games.map((g, i) => option(i, `Game ${i+1}`))); $('game-select').disabled = false;
  text('viewer-title', `${data.format} · Luật ${data.gameVersion} · Seed ${data.seedText ?? data.seed}`); text('score', `${data.scores.botA} : ${data.scores.botB}`);
  text('status-badge', statuses[data.status]);
  text('result-title', data.winnerBot ? `${name(data.winnerBot)} thắng` : 'Đang thi đấu');
  text('result-text', `Bot #1 ${name(data.botNames.botA)} ${data.scores.botA} – ${data.scores.botB} ${name(data.botNames.botB)} Bot #2`);
  const results = data.games.map((g, i) => {
    const div = document.createElement('div'); div.className = 'game-result'; div.textContent = `Game ${i+1} · ${g.result.plies} lượt`;
    const strong = document.createElement('strong'); strong.textContent = `${name(g.result.winnerBot)} / ${g.result.winner} · ${reasons[g.result.reason] || g.result.reason}${g.result.details.trigger ? ' · '+(triggers[g.result.details.trigger]||g.result.details.trigger) : ''}`; div.append(strong);
    const detail = g.result.details;
    if (detail.errorCode) { const p = document.createElement('p'); p.className = 'diagnostic'; p.textContent = `${detail.errorCode}: ${detail.message}`; div.append(p); }
    if (detail.criterion) {
      const d = document.createElement('details'), s = document.createElement('summary'), p = document.createElement('p');
      s.textContent = `Phân xử: ${triggers[detail.trigger]||detail.trigger} · ${detail.criterion}`;
      p.textContent = JSON.stringify(detail, null, 2); p.style.whiteSpace = 'pre-wrap'; p.style.overflowWrap = 'anywhere'; d.append(s,p); div.append(d);
    }
    return div;
  });
  $('game-results').replaceChildren(...results);
  $('download').hidden = false; $('download').href = `/api/matches/${matchId}/replay`; $('download').download = `${matchId}.json`;
  selectGame(0); if (auto) play();
  return true;
}
async function refresh() {
  const [matches, stats] = await Promise.all([api('/api/matches'), api('/api/stats')]);
  $('history').replaceChildren(...matches.map(m => {
    const row = document.createElement('tr');
    const values = [new Date(m.createdAt).toLocaleString('vi-VN'), `${name(m.botA)} / ${name(m.botB)}`, m.format,
      m.status === 'COMPLETED' ? `${m.scores.botA} : ${m.scores.botB} · ${name(m.winnerBot)}` : statuses[m.status]];
    values.forEach(v => { const td = document.createElement('td'); td.textContent = v; row.append(td); });
    const td = document.createElement('td'), button = document.createElement('button'); button.textContent = 'Xem';
    button.disabled = !['QUEUED','RUNNING','COMPLETED'].includes(m.status);
    button.addEventListener('click', () => openMatch(m.matchId).catch(e=>error(e.message)));
    td.append(button); row.append(td); return row;
  }));
  if (!matches.length) { const row=document.createElement('tr'), td=document.createElement('td'); td.colSpan=5; td.className='empty'; td.textContent='Chưa có trận. Tạo trận đầu tiên ở phía trên.'; row.append(td); $('history').append(row); }
  $('stats').replaceChildren(...stats.map(s => { const tr=document.createElement('tr'); [name(s.botId),s.matches,s.wins,s.losses].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td)}); return tr; }));
}
async function openMatch(matchId) {
  matchPoller.stop();pause();error('');activeMatch=matchId;replay=null;const viewRequest=++loadingReplay;
  $('game-select').disabled=true;$('scrub').disabled=true;$('download').hidden=true;
  for(const id of ['prev','play','next'])$(id).disabled=true;
  $('game-results').replaceChildren();$('move-list').replaceChildren();
  text('viewer-title','Đang tải bàn cờ');text('result-title','Đang tải trận');
  $('board').scrollIntoView({behavior:'smooth',block:'center'});
  await updateBots();
  if(viewRequest!==loadingReplay || activeMatch!==matchId)return;
  await matchPoller.start(matchId);
}
const matchPoller=createPoller({
  load:(id,signal)=>api(`/api/matches/${id}/live`,{signal}),
  onError:e=>error(e.message),
  apply:async(live,isCurrent)=>{
    const match=live.match,matchId=match.matchId;
    if (activeMatch === matchId && isCurrent()) {
      text('status-badge',statuses[match.status]);
      if (live.game && ['QUEUED','RUNNING'].includes(match.status)) {
        const game=live.game;
        const loadedRenderer=await import(game.replayRenderer);
        if(!isCurrent() || activeMatch!==matchId)return false;
        renderer=loadedRenderer;
        renderer.render($('board'),game.state,game.renderMetadata);showPressure(game.state);showRules(game.renderMetadata,match.gameVersion);
        text('viewer-title',`Đang đấu · Game ${game.gameNumber} · ${match.format}`);
        text('side-a',name(game.botNames[game.sideMapping.A]));text('side-b',name(game.botNames[game.sideMapping.B]));
        text('role-a',`Bên A · ${game.sideMapping.A==='botA'?'Bot #1':'Bot #2'} · đích i9`);
        text('role-b',`Bên B · ${game.sideMapping.B==='botA'?'Bot #1':'Bot #2'} · đích a1`);
        text('score',`${match.scores.botA} : ${match.scores.botB}`);
        text('turn-label',game.result ? `Game ${game.gameNumber} đã kết thúc` : `Lượt ${game.state.ply+1} · ${game.state.sideToMove}`);
        text('frame-label',`${game.state.ply} lượt đã đi`);text('move-count',`${game.state.ply} lượt`);
        const frame=game.frames.at(-1);text('move-detail',frame?renderer.describe(frame):'Bố trí ban đầu');
        const rows=game.frames.map(f=>{const p=document.createElement('p');p.className='last-move';p.textContent=`#${f.ply} ${f.playerId} · ${renderer.describe(f)}`;return p});
        $('move-list').replaceChildren(...rows);$('move-list').scrollTop=$('move-list').scrollHeight;
        text('result-title','Đang thi đấu');text('result-text','Bàn cờ đang cập nhật từ snapshot engine. Kết thúc trận sẽ mở toàn bộ replay.');
      }
    }
    if (['RUNNING','QUEUED'].includes(match.status))return true;
    await refresh();
    if(!isCurrent())return false;
    if(match.status!=='COMPLETED')throw new Error(match.error||'Trận bị gián đoạn');
    if(activeMatch===matchId) {
      const loaded=await loadReplay(matchId,false);
      if(!loaded || !isCurrent())return false;
      selectGame(replay.games.length-1);$('game-select').value=gameIndex;setFrame(currentGame().frames.length);
    }
    return false;
  }
});
$('match-form').addEventListener('submit', async event => {
  event.preventDefault(); error('');
  const seed = Number($('seed').value);
  if (!Number.isSafeInteger(seed) || seed < 0) { error('Seed phải là số nguyên từ 0 đến 9007199254740991.'); return; }
  if($('start').disabled)return;
  const payload={gameId:'ottv2',gameVersion:$('game-version').value,botA:$('bot-a').value,botB:$('bot-b').value,format:$('format').value,seed};
  matchPoller.stop();pause();activeMatch=null;const viewRequest=++loadingReplay;
  $('start').disabled=true; text('start', 'Đang tạo trận…');
  try {
    const profile=gameCatalog.find(g=>g.gameVersion===payload.gameVersion);
    const initial=profile?await fetch(profile.initialStateUrl||'/static/initial-state.json').then(r=>r.json()):null;
    const loadedRenderer=profile?await import(profile.replayRenderer):renderer;
    const match = await api('/api/matches', {method:'POST', headers:{'Content-Type':'application/json',...teamHeaders()},
      body:JSON.stringify(payload)});
    if(viewRequest!==loadingReplay)return;
    activeMatch=match.matchId; replay=null;renderer=loadedRenderer;preview=initial;
    if(profile)showRules(preview.metadata,profile.gameVersion);
    $('game-select').disabled=true; $('scrub').disabled=true;
    for (const id of ['prev','play','next']) $(id).disabled=true;
    $('game-results').replaceChildren(); $('move-list').replaceChildren(); $('download').hidden=true;
    text('side-a', name(payload.botA)); text('side-b', name(payload.botB));
    text('role-a','Bên A · Bot #1 · Đi trước · đích i9'); text('role-b','Bên B · Bot #2 · đích a1');
    text('score','0 : 0'); text('frame-label','0 / 0'); text('move-count','0 lượt');
    text('turn-label','Đang chờ dữ liệu trận'); text('move-detail','Bot đang thi đấu trong nền…');
    text('result-text','Bàn cờ sẽ cập nhật ngay khi trận bắt đầu.');
    if (preview) {renderer.render($('board'),preview.state,preview.metadata);showPressure(preview.state);}
    text('viewer-title','Bot đang thi đấu'); text('result-title','Đang chờ kết quả'); text('status-badge','ĐANG CHỜ');
    await refresh();
    if(viewRequest===loadingReplay)await matchPoller.start(match.matchId);
  } catch(e) {if(viewRequest===loadingReplay)error(e.message);}
  finally {$('start').disabled=false;text('start','Bắt đầu trận ↗');}
});
$('prev').addEventListener('click',()=>{pause();setFrame(frameIndex-1)});
$('next').addEventListener('click',()=>{pause();setFrame(frameIndex+1)});
$('play').addEventListener('click',play);
$('scrub').addEventListener('input',()=>{pause();setFrame(Number($('scrub').value))});
$('game-select').addEventListener('change',()=>selectGame(Number($('game-select').value)));
$('refresh').addEventListener('click',()=>refresh().catch(e=>error(e.message)));
function updateStrategy() { text('strategy', `#1: ${bots.find(b=>b.id===$('bot-a').value)?.description}   ·   #2: ${bots.find(b=>b.id===$('bot-b').value)?.description}`); }
$('bot-a').addEventListener('change', updateStrategy); $('bot-b').addEventListener('change', updateStrategy);
async function init() {
  bots = await api('/api/bots');
  for (const id of ['bot-a','bot-b']) $(id).replaceChildren(...bots.map(b=>option(b.id,b.name)));
  $('bot-b').value='goal_rush'; updateStrategy();
  // Use the plugin's own fixture to preview the board; no initialization rules in UI.
  gameCatalog = await api('/api/games');
  const versions=gameCatalog.filter(g=>g.gameId==='ottv2'),game=versions.find(g=>g.isDefault)||versions[0];
  for(const id of ['game-version','submission-version']) {$(id).replaceChildren(...versions.map(g=>option(g.gameVersion,`${g.gameVersion}${g.isDefault?' · mới':''}`)));$(id).value=game.gameVersion;}
  const initialRenderer=await import(game.replayRenderer);
  const initialPreview=await fetch(game.initialStateUrl||'/static/initial-state.json').then(r=>r.json());
  if($('game-version').value===game.gameVersion && !activeMatch && !replay) {
    renderer=initialRenderer;preview=initialPreview;
    renderer.render($('board'),preview.state,preview.metadata);showPressure(preview.state);showRules(preview.metadata,game.gameVersion);
  }
  await updateBots();
  await refresh();
}
init().catch(e=>error(`Không tải được ứng dụng: ${e.message}`));

// Team-owned source submissions. Team keys are sent in headers, never in URLs.
let teamKey = localStorage.getItem('arenaTeamKey') || '', currentTeam = null, submissionPoll = null;
let botRefresh=0,submissionRefresh=0,teamSession=0;
function teamHeaders() { return teamKey ? {'X-Team-Key':teamKey} : {}; }
function submissionError(message) { $('submission-error').hidden=!message; text('submission-error',message||''); }
async function updateBots(selectId = null) {
  const request=++botRefresh,data=await api('/api/bots');
  if(request!==botRefresh)return;
  const before = {a:$('bot-a').value,b:$('bot-b').value};
  bots=data;
  const eligible=bots.filter(b=>!b.gameVersion || !$('game-version').value || b.gameVersion===$('game-version').value);
  for (const id of ['bot-a','bot-b']) {
    const samples=document.createElement('optgroup'); samples.label='Bot mẫu / đấu thử';
    const teams=document.createElement('optgroup'); teams.label='Bot do đội nộp';
    eligible.forEach(b=>(b.source==='submission'?teams:samples).append(option(b.id,b.name)));
    $(id).replaceChildren(teams,samples);
  }
  if (eligible.some(b=>b.id===before.a)) $('bot-a').value=before.a;
  if (eligible.some(b=>b.id===before.b)) $('bot-b').value=before.b;
  if (selectId && eligible.some(b=>b.id===selectId)) $('bot-a').value=selectId;
  updateStrategy();
}
async function refreshSubmissions() {
  clearTimeout(submissionPoll);
  if (!teamKey || !currentTeam) return;
  const request=++submissionRefresh,teamId=currentTeam.teamId;
  const data=await api('/api/submissions',{headers:teamHeaders()});
  if(request!==submissionRefresh || currentTeam?.teamId!==teamId)return;
  const labels={PENDING_CHECK:'Chờ kiểm tra',CHECKING:'Đang kiểm tra',READY:'Sẵn sàng thi đấu',INVALID:'Lỗi cú pháp',CHECK_FAILED:'Kiểm tra thất bại',SANDBOX_UNAVAILABLE:'Sandbox chưa sẵn sàng'};
  $('submissions').replaceChildren(...data.map(row=>{
    const tr=document.createElement('tr');
    const title=document.createElement('td');title.textContent=`${row.botName} · v${row.version} · luật ${row.gameVersion}`;
    const status=document.createElement('td');status.className='submission-state';status.textContent=labels[row.status]||row.status;
    const diagnostic=document.createElement('td');diagnostic.className='submission-diagnostic';diagnostic.textContent=row.validation;
    const actions=document.createElement('td');
    const button=document.createElement('button');button.textContent='Đấu thử';button.disabled=row.status!=='READY';
    button.addEventListener('click',async()=>{try{$('game-version').value=row.gameVersion;await updateBots(row.id);$('format').value='BO1';$('bot-b').value='goal_rush';updateStrategy();$('match-form').requestSubmit();}catch(e){submissionError(e.message)}});
    const source=document.createElement('button');source.textContent='Tải code';source.style.marginTop='5px';
    source.addEventListener('click',async()=>{
      try {
        const response=await fetch(`/api/submissions/${row.id}/source`,{headers:teamHeaders()});
        if(!response.ok) throw new Error('Không tải được source của đội');
        const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
        link.href=url;link.download=row.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      } catch(e){submissionError(e.message)}
    });
    actions.append(button,document.createElement('br'),source);tr.append(title,status,diagnostic,actions);return tr;
  }));
  if(!data.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=4;td.className='empty';td.textContent='Đội chưa có bài nộp. Tải template và nộp file .py ở trên.';tr.append(td);$('submissions').append(tr)}
  await updateBots();
  if(request===submissionRefresh && currentTeam?.teamId===teamId && data.some(r=>['PENDING_CHECK','CHECKING'].includes(r.status))) submissionPoll=setTimeout(()=>refreshSubmissions().catch(e=>submissionError(e.message)),1000);
}
async function enterTeam(key, created = null) {
  const request=++teamSession;
  let team;
  try {team=await api('/api/team',{headers:{'X-Team-Key':key}});}
  catch(e){if(request!==teamSession)return false;throw e;}
  if(request!==teamSession)return false;
  teamKey=key;
  currentTeam=team;localStorage.setItem('arenaTeamKey',key);
  $('team-access').hidden=true;$('team-session').hidden=false;text('team-label',`Đội: ${team.name}`);
  $('new-team-key').hidden=!created;$('team-key-notice').hidden=!created;
  if(created)$('new-team-key').value=key;
  await refreshSubmissions().catch(e=>submissionError(e.message));
  tournamentUI.refresh();
  return request===teamSession;
}
$('team-form').addEventListener('submit',async e=>{
  e.preventDefault();submissionError('');const button=e.submitter;button.disabled=true;
  try{const team=await api('/api/teams',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('team-name').value})});if(await enterTeam(team.teamKey,team))text('submission-message','Đã tạo đội. Hãy lưu mã truy cập trước khi nộp code.');}
  catch(err){submissionError(err.message)}finally{button.disabled=false}
});
$('team-login').addEventListener('submit',async e=>{e.preventDefault();submissionError('');try{if(await enterTeam($('team-key').value.trim()))text('submission-message','Đã vào đội.')}catch(err){teamKey='';currentTeam=null;submissionError(err.message)}});
$('team-logout').addEventListener('click',()=>{clearTimeout(submissionPoll);teamSession++;submissionRefresh++;teamKey='';currentTeam=null;localStorage.removeItem('arenaTeamKey');$('team-access').hidden=false;$('team-session').hidden=true;$('team-key').value='';$('new-team-key').value='';$('submissions').replaceChildren();text('submission-message','');tournamentUI.refresh();});
$('submission-form').addEventListener('submit',async e=>{
  e.preventDefault();submissionError('');$('submit-code').disabled=true;
  try {
    const file=$('submission-file').files[0];
    if(!file || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\.py$/.test(file.name)) throw new Error('Chọn file Python .py có tên không chứa đường dẫn.');
    if(file.size>256*1024 || !file.size) throw new Error('File .py phải từ 1 byte đến 256 KiB.');
    const source=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
    const row=await api('/api/submissions',{method:'POST',headers:{'Content-Type':'application/json',...teamHeaders()},body:JSON.stringify({botName:$('submission-name').value,filename:file.name,source,gameId:'ottv2',gameVersion:$('submission-version').value})});
    text('submission-message',`Đã nhận ${row.botName} v${row.version}. ${row.validation}`);
    await refreshSubmissions();
  }catch(err){submissionError(err.message)}finally{$('submit-code').disabled=false}
});
async function initSubmissions() {
  const runtime=await api('/api/runtime');text('runtime-badge',runtime.ready?'SANDBOX HOẠT ĐỘNG':'SANDBOX CHƯA SẴN SÀNG');
  $('runtime-badge').title=runtime.message;
  if(!runtime.ready) text('submission-message','Có thể gửi code; bài nộp sẽ chờ cho tới khi server có sandbox Linux hoạt động.');
  if(teamKey){try{await enterTeam(teamKey)}catch(e){
    if(e.status===401){teamKey='';currentTeam=null;localStorage.removeItem('arenaTeamKey');submissionError('Mã đội đã lưu không còn hợp lệ; hãy vào đội lại.');}
    else submissionError('Chưa tải được thông tin đội. Mã đã lưu được giữ lại; hãy thử tải lại trang.');
  }}
}
initSubmissions().catch(e=>submissionError(e.message));

$('game-version').addEventListener('change',async()=>{
  try {
    await updateBots();
    const selected=gameCatalog.find(g=>g.gameVersion===$('game-version').value);
    if(selected && !replay && !activeMatch) {
      const request=++previewRequest,version=selected.gameVersion;
      const initial=await fetch(selected.initialStateUrl||'/static/initial-state.json').then(r=>r.json());
      const loadedRenderer=await import(selected.replayRenderer);
      if(request!==previewRequest || version!==$('game-version').value || replay || activeMatch)return;
      preview=initial;renderer=loadedRenderer;showRules(null,version);
      renderer.render($('board'),preview.state,preview.metadata);showPressure(preview.state);
    }
  } catch(e){error(e.message)}
});

const tournamentUI=initTournaments({api,headers:teamHeaders,getTeam:()=>currentTeam,openMatch});
