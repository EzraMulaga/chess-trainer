// Thin fetch wrapper over the Phase 5 FastAPI endpoints.
const api = (() => {
  async function request(path, options) {
    const resp = await fetch(path, options);
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const body = await resp.json();
        detail = body.detail || detail;
      } catch (e) {
        // response wasn't JSON; fall back to statusText
      }
      throw new Error(detail);
    }
    if (resp.status === 204) return null;
    return resp.json();
  }

  function withRepertoire(base, repertoire) {
    return repertoire ? `${base}?repertoire=${encodeURIComponent(repertoire)}` : base;
  }

  function postJson(path, body) {
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  return {
    importPgn(pgn, repertoire) {
      return postJson('/repertoire/import-pgn', { pgn, repertoire });
    },
    generateCandidates(params) {
      return postJson('/repertoire/generate-candidates', params);
    },
    listPending(repertoire) {
      return request(withRepertoire('/repertoire/pending', repertoire));
    },
    getLine(positionId) {
      return request(`/repertoire/positions/${positionId}/line`);
    },
    setStatus(positionId, status) {
      return postJson(`/repertoire/positions/${positionId}/status`, { status });
    },
    getDue(repertoire) {
      return request(withRepertoire('/drill/due', repertoire));
    },
    answer(positionId, move, quality) {
      const body = { move };
      if (quality !== undefined) body.quality = quality;
      return postJson(`/drill/positions/${positionId}/answer`, body);
    },
    reviewGame(pgn, searchDepth) {
      return postJson('/games/review', { pgn, search_depth: searchDepth || 16 });
    },
    getGame(gameId) {
      return request(`/games/${gameId}`);
    },
  };
})();
