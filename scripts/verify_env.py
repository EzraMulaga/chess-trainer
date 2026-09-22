"""Phase 0: verify the local environment can import python-chess and drive Stockfish.

Run with: python scripts/verify_env.py
Optionally set STOCKFISH_PATH if the binary isn't on PATH.
"""
import os
import shutil
import sys

MIN_PYTHON = (3, 10)


def check_python_version() -> bool:
    ok = sys.version_info >= MIN_PYTHON
    label = "OK" if ok else "FAIL"
    print(f"[{label}] Python {sys.version.split()[0]} (need >= {'.'.join(map(str, MIN_PYTHON))})")
    return ok


def check_python_chess() -> bool:
    try:
        import chess  # noqa: F401
        import chess.engine  # noqa: F401
    except ImportError as exc:
        print(f"[FAIL] python-chess not importable: {exc}")
        print("       -> activate your venv and run: pip install -r requirements.txt")
        return False
    print(f"[OK] python-chess importable (chess.__version__={chess.__version__})")
    return True


def find_stockfish() -> str | None:
    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    return shutil.which("stockfish")


def check_stockfish() -> bool:
    path = find_stockfish()
    if not path:
        print("[FAIL] Stockfish binary not found on PATH or via STOCKFISH_PATH.")
        print("       -> install it with: sudo apt install stockfish")
        print("       -> or set STOCKFISH_PATH=/path/to/stockfish if installed elsewhere")
        return False
    print(f"[OK] Stockfish binary found at: {path}")

    import chess
    import chess.engine

    try:
        with chess.engine.SimpleEngine.popen_uci(path) as engine:
            board = chess.Board()
            info = engine.analyse(board, chess.engine.Limit(depth=15))
            score = info["score"].white()
            best_move = info.get("pv", [None])[0]
            print(f"[OK] Engine analysis on startpos: depth=15 score={score} bestmove={best_move}")
    except Exception as exc:
        print(f"[FAIL] Stockfish launched but analysis failed: {exc}")
        return False
    return True


def main() -> int:
    print("=== Phase 0 environment verification ===")
    results = [
        check_python_version(),
        check_python_chess(),
    ]
    # Only attempt engine check if python-chess imported successfully.
    if results[-1]:
        results.append(check_stockfish())
    else:
        results.append(False)
        print("[SKIP] Stockfish check skipped (python-chess not available)")

    print("=========================================")
    if all(results):
        print("All checks passed. Environment is ready for Phase 1.")
        return 0
    print("One or more checks failed. Fix the issues above and re-run this script.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
