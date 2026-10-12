const $ = id => document.getElementById(id);
const statusLabels = {OPEN:'ĐANG ĐĂNG KÝ', RUNNING:'ĐANG THI ĐẤU', COMPLETED:'ĐÃ HOÀN TẤT', PAUSED:'TẠM DỪNG', SCHEDULED:'Chờ lịch', QUEUED:'Đang chờ', FAILED:'Lỗi hệ thống', INTERRUPTED:'Bị gián đoạn'};
const option = (value, label) => {const el=document.createElement('option');el.value=value;el.textContent=label;return el;};
const cell = value => {const el=document.createElement('td');el.textContent=value;return el;};

export function initTournaments({api, headers, getTeam, openMatch}) {
  let selected = new URL(location.href).searchParams.get('tournament') || '', current = null, poll = null, revision = 0, busy = false, refreshRequest=0;
  function showError(message) {$('tournament-error').hidden=!message;$('tournament-error').textContent=message||'';}
  function setSelection(id) {
    selected=id;revision++;
    const url=new URL(location.href);
    if(id)url.searchParams.set('tournament',id);else url.searchParams.delete('tournament');
    history.replaceState(null,'',url);
  }
  async function updateEntryControls() {
    const team=getTeam(), tournament=current;
    $('tournament-create-button').disabled=!team || busy;
    $('tournament-auth-hint').hidden=!!team;
    $('tournament-entry-form').hidden=!team || tournament?.status!=='OPEN';
    $('tournament-start').hidden=!team || !tournament || tournament.organizerTeamId!==team.teamId || tournament.status!=='OPEN';
    $('tournament-resume').hidden=!team || !tournament || tournament.organizerTeamId!==team.teamId || tournament.status!=='PAUSED';
    $('tournament-start').disabled=busy || (tournament?.entries.length||0)<2;
    $('tournament-resume').disabled=busy;
    if(!tournament)return;
    const enrolled=tournament.entries.find(e=>e.teamId===team?.teamId);
    $('tournament-withdraw').hidden=!enrolled;
    if(tournament.status!=='OPEN') {
      $('tournament-entry-hint').textContent='Danh sách đã khóa. Nộp bot mới vẫn được, nhưng bot trong giải giữ nguyên phiên bản đã chọn.';
      return;
    }
    if(!team) {$('tournament-entry-hint').textContent='Vào đội ở phía trên, nộp bot đúng bộ luật và đăng ký tại đây.';return;}
    const teamId=team.teamId, id=tournament.tournamentId;
    const rows=await api('/api/submissions',{headers:headers()});
    if(getTeam()?.teamId!==teamId || current?.tournamentId!==id || current.status!=='OPEN')return;
    const eligible=rows.filter(r=>r.status==='READY' && r.gameId===tournament.gameId && r.gameVersion===tournament.gameVersion);
    const previous=$('tournament-bot').value;
    $('tournament-bot').replaceChildren(...eligible.map(r=>option(r.id,`${r.botName} · v${r.version} · ${r.gameVersion}`)));
    if(eligible.some(r=>r.id===previous))$('tournament-bot').value=previous;
    else if(enrolled && eligible.some(r=>r.id===enrolled.botId))$('tournament-bot').value=enrolled.botId;
    $('tournament-register').disabled=busy || !eligible.length;
    $('tournament-withdraw').disabled=busy;
    $('tournament-entry-hint').textContent=eligible.length ? (enrolled ? 'Đội đã đăng ký. Có thể đổi phiên bản trước khi chủ giải khóa danh sách.' : 'Chọn một phiên bản READY để đăng ký. Mỗi đội có một suất.') : `Đội chưa có bot READY cho ${tournament.gameId} ${tournament.gameVersion}. Nộp code và chờ kiểm tra ở phía trên.`;
  }
  function render(tournament, standings) {
    current=tournament;$('tournament-detail').hidden=false;
    $('tournament-title').textContent=tournament.name;
    $('tournament-status').textContent=statusLabels[tournament.status]||tournament.status;
    $('tournament-info').textContent=`Chủ giải: ${tournament.organizerName} · ${tournament.gameId} ${tournament.gameVersion} · ${tournament.format} · ${tournament.entries.length}/${tournament.maxTeams} đội · ${standings.completedMatches}/${standings.totalMatches} trận xong`;
    $('tournament-share').href=`/?tournament=${tournament.tournamentId}`;
    $('tournament-lock').hidden=!tournament.lockedAt;
    $('tournament-lock').textContent=tournament.lockedAt ? `Đã khóa lúc ${new Date(tournament.lockedAt).toLocaleString('vi-VN')}: phiên bản bot, hash source/SDK, bộ luật, thể thức và seed từng trận.` : '';
    $('tournament-standings').replaceChildren(...standings.rows.map(row=>{
      const tr=document.createElement('tr'), label=cell(row.teamName), small=document.createElement('small');
      small.className='sub';small.textContent=`${row.botName} · v${row.botVersion}`;label.append(small);
      label.title=`Bot ID: ${row.botId}\nArtifact SHA256: ${row.artifactSha256}`;
      tr.append(cell(row.rank),label,cell(row.played),cell(`${row.wins}–${row.losses}`),cell(row.points),cell(`${row.gameWins}–${row.gameLosses} (${row.gameDifference>0?'+':''}${row.gameDifference})`),cell(row.headToHeadPoints));return tr;
    }));
    if(!standings.rows.length){const tr=document.createElement('tr'),td=cell('Chưa có đội đăng ký.');td.colSpan=7;td.className='empty';tr.append(td);$('tournament-standings').append(tr);}
    const teams=Object.fromEntries(tournament.entries.map(e=>[e.teamId,e.teamName]));
    $('tournament-fixtures').replaceChildren(...tournament.fixtures.map(f=>{
      const tr=document.createElement('tr'),state=cell(f.status==='COMPLETED'?`${f.scores.botA} : ${f.scores.botB}`:statusLabels[f.status]||f.status),actions=cell('');
      if(f.error){const small=document.createElement('small');small.className='sub';small.textContent=f.error;state.append(small);}
      const button=document.createElement('button');button.type='button';button.textContent=f.status==='COMPLETED'?'Xem replay':'Xem bàn cờ';button.disabled=!['QUEUED','RUNNING','COMPLETED'].includes(f.status);
      button.addEventListener('click',()=>openMatch(f.matchId).catch(e=>showError(e.message)));actions.append(button);
      if(f.attempts.length){const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`${f.attempts.length} lần chạy trước`;detail.append(summary);
        for(const attempt of f.attempts){const p=document.createElement('p');p.textContent=`${attempt.matchId} · ${statusLabels[attempt.status]||attempt.status}`;detail.append(p);}actions.append(detail);}
      tr.append(cell(f.round),cell(`${teams[f.teamA]} / ${teams[f.teamB]}`),state,actions);return tr;
    }));
    if(!tournament.fixtures.length){const tr=document.createElement('tr'),td=cell('Lịch đấu được tạo khi chủ giải bấm Khóa bot & bắt đầu giải.');td.colSpan=4;td.className='empty';tr.append(td);$('tournament-fixtures').append(tr);}
    $('tournament-message').textContent=tournament.error || (tournament.status==='COMPLETED' ? 'Giải đã hoàn tất. Kết quả và replay được lưu sau khi khởi động lại.' : '');
  }
  async function refresh() {
    clearTimeout(poll);const request=++refreshRequest,requestRevision=revision;
    try {
      const list=await api('/api/tournaments');
      if(request!==refreshRequest || requestRevision!==revision)return;
      if(!selected && list.length)setSelection(list[0].tournamentId);
      $('tournament-select').replaceChildren(option('','Chọn giải đấu'),...list.map(t=>option(t.tournamentId,`${t.name} · ${statusLabels[t.status]} · ${t.teamCount} đội`)));
      $('tournament-select').value=selected;
      if(selected){
        const selectedId=selected, detailRevision=revision;
        const tournament=await api(`/api/tournaments/${selectedId}`);
        if(request!==refreshRequest || detailRevision!==revision || selectedId!==selected)return;
        render(tournament,tournament.standings);
      } else {current=null;$('tournament-detail').hidden=true;$('tournament-message').textContent='Chưa có giải. Vào đội và tạo giải đầu tiên.';}
      await updateEntryControls();
    } catch(e){if(request===refreshRequest)showError(e.message);}
    finally{if(request===refreshRequest)poll=setTimeout(refresh,current?.status==='RUNNING'?1000:3000);}
  }
  async function mutate(url, body, message) {
    if(busy)return;
    busy=true;showError('');
    try {
      await updateEntryControls();
      const result=await api(url,{method:'POST',headers:{'Content-Type':'application/json',...headers()},...(body ? {body:JSON.stringify(body)} : {})});
      if(result.tournamentId)setSelection(result.tournamentId);
      await refresh();$('tournament-message').textContent=message;
    }catch(e){showError(e.message);}finally{busy=false;await updateEntryControls().catch(e=>showError(e.message));}
  }
  $('tournament-select').addEventListener('change',()=>{setSelection($('tournament-select').value);showError('');refresh();});
  $('tournament-refresh').addEventListener('click',()=>{showError('');refresh();});
  $('tournament-form').addEventListener('submit',e=>{
    e.preventDefault();const seed=Number($('tournament-seed').value);
    if(!Number.isSafeInteger(seed)||seed<0){showError('Seed phải là số nguyên từ 0 đến 9007199254740991.');return;}
    const [gameId,gameVersion]=$('tournament-version').value.split('@');
    mutate('/api/tournaments',{name:$('tournament-name').value,gameId,gameVersion,format:$('tournament-format').value,seed},'Đã tạo giải. Chia sẻ liên kết cho các đội đăng ký bot.');
  });
  $('tournament-entry-form').addEventListener('submit',e=>{e.preventDefault();mutate(`/api/tournaments/${selected}/entries`,{botId:$('tournament-bot').value},'Đã lưu phiên bản bot đăng ký.');});
  $('tournament-withdraw').addEventListener('click',()=>mutate(`/api/tournaments/${selected}/withdraw`,null,'Đã rút đội khỏi giải.'));
  $('tournament-start').addEventListener('click',()=>mutate(`/api/tournaments/${selected}/start`,null,'Đã khóa phiên bản bot và tạo lịch. Các trận sẽ tự động bắt đầu.'));
  $('tournament-resume').addEventListener('click',()=>mutate(`/api/tournaments/${selected}/resume`,null,'Đã tiếp tục giải. Trận lỗi có lần chạy mới; lịch sử cũ vẫn được giữ.'));
  async function init() {
    const games=await api('/api/games');
    $('tournament-version').replaceChildren(...games.map(g=>option(`${g.gameId}@${g.gameVersion}`,`${g.name||g.gameId} ${g.gameVersion}`)));
    const preferred=games.find(g=>g.isDefault)||games[0];if(preferred)$('tournament-version').value=`${preferred.gameId}@${preferred.gameVersion}`;
    await refresh();
  }
  init().catch(e=>showError(e.message));
  return {refresh};
}
