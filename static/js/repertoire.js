// Repertoire view: PGN import, engine candidate generation, prune/approve workflow.
(function () {
  async function handleImport(e) {
    e.preventDefault();
    const pgn = document.getElementById('import-pgn-text').value;
    const repertoire = document.getElementById('import-repertoire').value.trim();
    const statusEl = document.getElementById('import-status');
    statusEl.textContent = 'Importing...';
    try {
      const result = await api.importPgn(pgn, repertoire);
      statusEl.textContent = `Imported ${result.position_ids.length} position(s).`;
      document.getElementById('pending-repertoire').value = repertoire;
      loadPending();
    } catch (err) {
      statusEl.textContent = 'Error: ' + err.message;
    }
  }

  async function handleGenerate(e) {
    e.preventDefault();
    const statusEl = document.getElementById('generate-status');
    const params = {
      seed_fen: document.getElementById('generate-fen').value.trim(),
      repertoire: document.getElementById('generate-repertoire').value.trim(),
      max_ply: parseInt(document.getElementById('generate-max-ply').value, 10) || 4,
      multipv: parseInt(document.getElementById('generate-multipv').value, 10) || 2,
      eval_drop_cp: parseInt(document.getElementById('generate-eval-drop').value, 10) || 50,
      search_depth: parseInt(document.getElementById('generate-depth').value, 10) || 18,
      max_candidates: parseInt(document.getElementById('generate-max-candidates').value, 10) || 50,
    };
    statusEl.textContent = 'Generating (calls Stockfish, may take a moment)...';
    try {
      const result = await api.generateCandidates(params);
      statusEl.textContent = `Generated ${result.position_ids.length} position(s) (including seed).`;
      document.getElementById('pending-repertoire').value = params.repertoire;
      loadPending();
    } catch (err) {
      statusEl.textContent = 'Error: ' + err.message;
    }
  }

  function formatEval(pos) {
    if (pos.eval_mate !== null && pos.eval_mate !== undefined) return `(mate in ${pos.eval_mate})`;
    if (pos.eval_cp !== null && pos.eval_cp !== undefined) return `(${(pos.eval_cp / 100).toFixed(2)})`;
    return '';
  }

  async function loadPending() {
    const repertoire = document.getElementById('pending-repertoire').value.trim() || undefined;
    const listEl = document.getElementById('pending-list');
    listEl.innerHTML = '<li>Loading...</li>';
    let pending;
    try {
      pending = await api.listPending(repertoire);
    } catch (err) {
      listEl.innerHTML = `<li>Error: ${err.message}</li>`;
      return;
    }
    if (pending.length === 0) {
      listEl.innerHTML = '<li>No pending candidates.</li>';
      return;
    }
    listEl.innerHTML = '';
    for (const pos of pending) {
      const li = document.createElement('li');
      li.className = 'pending-item';

      const label = document.createElement('span');
      label.textContent = `[${pos.id}] loading line...`;
      li.appendChild(label);

      const approveBtn = document.createElement('button');
      approveBtn.textContent = 'Approve';
      approveBtn.addEventListener('click', () => updateStatus(pos.id, 'approved'));

      const rejectBtn = document.createElement('button');
      rejectBtn.textContent = 'Reject';
      rejectBtn.addEventListener('click', () => updateStatus(pos.id, 'rejected'));

      li.appendChild(approveBtn);
      li.appendChild(rejectBtn);
      listEl.appendChild(li);

      api.getLine(pos.id).then((line) => {
        const sanLine = line.map((p) => p.move_san).filter(Boolean).join(' ') || '(starting position)';
        label.textContent = `[${pos.id}] ${sanLine} ${formatEval(pos)}`;
      }).catch(() => {
        label.textContent = `[${pos.id}] (line unavailable)`;
      });
    }
  }

  async function updateStatus(positionId, status) {
    try {
      await api.setStatus(positionId, status);
      loadPending();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('import-form').addEventListener('submit', handleImport);
    document.getElementById('generate-form').addEventListener('submit', handleGenerate);
    document.getElementById('pending-load-btn').addEventListener('click', loadPending);
  });
})();
