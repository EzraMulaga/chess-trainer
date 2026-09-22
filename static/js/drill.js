// Drill view: drag-and-drop board wired to /drill/due and /drill/positions/{id}/answer.
(function () {
  let dueQueue = [];
  let currentPosition = null;
  let board = null;
  let chessLocal = null;
  let submitting = false;

  function setFeedback(msg, cls) {
    const el = document.getElementById('drill-feedback');
    el.textContent = msg;
    el.className = cls || '';
  }

  function onDragStart(source, piece) {
    if (!currentPosition || submitting) return false;
    if (chessLocal.game_over()) return false;
    const sideToMove = chessLocal.turn();
    if ((sideToMove === 'w' && piece.search(/^b/) !== -1) ||
        (sideToMove === 'b' && piece.search(/^w/) !== -1)) {
      return false;
    }
  }

  function onDrop(source, target) {
    const move = chessLocal.move({ from: source, to: target, promotion: 'q' });
    if (move === null) return 'snapback';
    submitMove(move.san);
  }

  function onSnapEnd() {
    board.position(chessLocal.fen());
  }

  async function submitMove(san) {
    submitting = true;
    setFeedback('Checking...');
    try {
      const result = await api.answer(currentPosition.id, san);
      if (result.correct) {
        setFeedback(`Correct! Next review in ${result.interval_days} day(s).`, 'good');
      } else {
        setFeedback(`Incorrect — correct move was ${result.correct_move_san}.`, 'bad');
      }
      setTimeout(nextPosition, 1400);
    } catch (err) {
      setFeedback('Error: ' + err.message, 'bad');
      submitting = false;
    }
  }

  function nextPosition() {
    dueQueue.shift();
    submitting = false;
    if (dueQueue.length === 0) {
      currentPosition = null;
      setFeedback('Session complete — no more due positions right now.');
      board.position('start');
      return;
    }
    showCurrentPosition();
  }

  function showCurrentPosition() {
    currentPosition = dueQueue[0];
    chessLocal = new Chess(currentPosition.fen);
    const whiteToMove = currentPosition.fen.split(' ')[1] === 'w';
    board.orientation(whiteToMove ? 'white' : 'black');
    board.position(currentPosition.fen);
    setFeedback(`${dueQueue.length} position(s) remaining. Your move (${whiteToMove ? 'White' : 'Black'} to move).`);
  }

  async function loadDue() {
    const repertoire = document.getElementById('drill-repertoire').value.trim() || undefined;
    setFeedback('Loading...');
    try {
      dueQueue = await api.getDue(repertoire);
    } catch (err) {
      setFeedback('Error: ' + err.message, 'bad');
      return;
    }
    if (dueQueue.length === 0) {
      setFeedback('Nothing due right now.');
      board.position('start');
      currentPosition = null;
      return;
    }
    showCurrentPosition();
  }

  document.addEventListener('DOMContentLoaded', () => {
    board = Chessboard('drill-board', {
      draggable: true,
      position: 'start',
      pieceTheme: 'vendor/img/chesspieces/wikipedia/{piece}.png',
      onDragStart,
      onDrop,
      onSnapEnd,
    });
    document.getElementById('drill-load-btn').addEventListener('click', loadDue);
  });
})();
