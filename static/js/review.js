// Game review view: table + eval chart + click-a-row-to-see-the-board.
(function () {
  let evalChart = null;
  let reviewBoard = null;
  let plyFens = [];

  function formatEval(cp, mate) {
    if (mate !== null && mate !== undefined) return (mate > 0 ? '#' : '#-') + Math.abs(mate);
    if (cp === null || cp === undefined) return '?';
    return (cp / 100).toFixed(2);
  }

  function evalToPawns(cp, mate) {
    const clamp = 10;
    if (mate !== null && mate !== undefined) return mate > 0 ? clamp : -clamp;
    if (cp === null || cp === undefined) return 0;
    return Math.max(-clamp, Math.min(clamp, cp / 100));
  }

  // Replays the UCI move sequence locally with chess.js to get a FEN per
  // ply, since the review API only returns evals/classifications, not FENs.
  function computeFens(uciMoves) {
    const chessLocal = new Chess();
    const fens = [chessLocal.fen()];
    for (const uci of uciMoves) {
      const from = uci.slice(0, 2);
      const to = uci.slice(2, 4);
      const promotion = uci.length > 4 ? uci.slice(4) : undefined;
      chessLocal.move({ from, to, promotion });
      fens.push(chessLocal.fen());
    }
    return fens;
  }

  function renderTable(moves) {
    const tbody = document.querySelector('#review-table tbody');
    tbody.innerHTML = '';
    moves.forEach((m, idx) => {
      const tr = document.createElement('tr');
      tr.className = 'cls-' + m.classification;
      tr.innerHTML = `
        <td>${m.ply}</td>
        <td>${m.move_san}</td>
        <td>${formatEval(m.eval_before_cp, m.eval_before_mate)}</td>
        <td>${formatEval(m.eval_after_cp, m.eval_after_mate)}</td>
        <td>${m.classification}</td>
      `;
      tr.addEventListener('click', () => showPly(idx + 1));
      tbody.appendChild(tr);
    });
  }

  function renderSummary(moves) {
    const counts = {};
    moves.forEach((m) => { counts[m.classification] = (counts[m.classification] || 0) + 1; });
    document.getElementById('review-summary').textContent =
      Object.entries(counts).map(([k, v]) => `${k}: ${v}`).join('   ');
  }

  function renderChart(moves) {
    const ctx = document.getElementById('eval-chart').getContext('2d');
    const labels = moves.map((m) => m.ply);
    const data = moves.map((m) => evalToPawns(m.eval_after_cp, m.eval_after_mate));
    if (evalChart) evalChart.destroy();
    evalChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Eval (pawns, White POV)',
          data,
          borderColor: '#2b6cb0',
          tension: 0.1,
          pointRadius: 2,
        }],
      },
      options: {
        scales: { y: { min: -10, max: 10 } },
        onClick: (evt, elements) => {
          if (elements.length > 0) showPly(elements[0].index + 1);
        },
      },
    });
  }

  function showPly(ply) {
    if (!reviewBoard || plyFens[ply] === undefined) return;
    reviewBoard.position(plyFens[ply]);
  }

  async function handleReview(e) {
    e.preventDefault();
    const pgn = document.getElementById('review-pgn-text').value;
    const depth = parseInt(document.getElementById('review-depth').value, 10) || 16;
    const statusEl = document.getElementById('review-status');
    statusEl.textContent = 'Reviewing (this can take a while for long games)...';
    try {
      const result = await api.reviewGame(pgn, depth);
      statusEl.textContent = `Game ${result.game_id} reviewed — ${result.moves.length} moves.`;
      renderTable(result.moves);
      renderSummary(result.moves);
      renderChart(result.moves);
      plyFens = computeFens(result.moves.map((m) => m.move_uci));
      if (!reviewBoard) {
        reviewBoard = Chessboard('review-board', {
          position: 'start',
          pieceTheme: 'vendor/img/chesspieces/wikipedia/{piece}.png',
        });
      } else {
        reviewBoard.position('start');
      }
    } catch (err) {
      statusEl.textContent = 'Error: ' + err.message;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('review-form').addEventListener('submit', handleReview);
  });
})();
