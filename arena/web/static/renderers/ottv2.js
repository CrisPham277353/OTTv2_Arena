// Only this renderer knows the OTT board/pieces. All states come from saved replay.
export function render(container, state, metadata) {
  const pieces = new Map(state.pieces.map(p => [p.at, p]));
  const frag = document.createDocumentFragment();
  for (let row = metadata.size; row >= 1; row--) {
    const axis = document.createElement('div'); axis.className = 'axis'; axis.textContent = row; frag.append(axis);
    metadata.columns.forEach((col, index) => {
      const at = `${col}${row}`, piece = pieces.get(at);
      const cell = document.createElement('div');
      cell.className = `cell ${(row + index) % 2 ? 'dark' : ''}`;
      cell.dataset.at = at;
      if (Object.values(metadata.targets).includes(at)) cell.classList.add('goal');
      if (state.lastMove?.from === at) cell.classList.add('from');
      if (state.lastMove?.to === at) cell.classList.add('to');
      cell.setAttribute('aria-label', `${at}: ${piece ? `${piece.side} ${metadata.pieceLabels[piece.kind]}` : 'trống'}`);
      cell.title = cell.getAttribute('aria-label');
      if (piece) {
        const token = document.createElement('span'); token.className = `piece ${piece.side.toLowerCase()}`;
        token.textContent = piece.kind;
        const team = document.createElement('small'); team.textContent = piece.side; token.append(team); cell.append(token);
      }
      frag.append(cell);
    });
  }
  frag.append(document.createElement('div'));
  metadata.columns.forEach(col => { const axis = document.createElement('div'); axis.className = 'axis'; axis.textContent = col; frag.append(axis); });
  container.replaceChildren(frag);
}

export function describe(frame) {
  if (!frame.action) return 'Bot bị xử thua';
  const captured = frame.events.find(e => e.type === 'PIECE_CAPTURED');
  return `${frame.action.from} → ${frame.action.to}${captured ? ` · ăn ${captured.side}:${captured.kind}` : ''}`;
}

export function pressureLabel(state) {
  const p=state.antiStall;
  return p ? `Không ăn quân: ${p.noCapturePlies}/${p.noCaptureLimit} lượt · Không tiến bộ: A ${p.noProgressTurns.A}/${p.noProgressLimit}, B ${p.noProgressTurns.B}/${p.noProgressLimit} lượt riêng` : '';
}
