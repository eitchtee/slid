"""Finds the fewest moves that solve a Slid board, or a good route fast. Not part of the game.

The search itself lives in slid/solver.py (the server uses its quick() for each day's challenge).

    uv run python scripts/solve.py board GAQIDBDEJEEBITRMRKB.PGTG BRIDGE --cols 6
    uv run python scripts/solve.py simulate                 # every day from launch to today
    uv run python scripts/solve.py simulate --from 2026-09-10 --to 2026-09-18 --lang pt-BR
    uv run python scripts/solve.py simulate --quick          # good routes instead of the shortest, ~50 ms each
"""

import argparse
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from slid import store  # noqa: E402
from slid.i18n import LANGS  # noqa: E402
from slid.puzzle import EMPTY, LAUNCH, daily, number, swap  # noqa: E402
from slid.solver import TooHard, quick, solve  # noqa: E402

DIRECTION = {-1: "left", 1: "right"}  # tile travel, by column step; rows are handled below


def describe(board: str, path: list[int], cols: int) -> list[str]:
    """Human-readable steps: which letter moved which way."""
    steps = []
    for tile in path:
        gap = board.index(EMPTY)
        step = gap - tile
        direction = DIRECTION[step] if abs(step) == 1 else ("down" if step > 0 else "up")
        r, c = divmod(tile, cols)
        steps.append(f"{board[tile]} (row {r + 1}, col {c + 1}) {direction}")
        board = swap(board, gap, tile)
    return steps


def show(board: str, cols: int) -> str:
    return "\n".join("  " + " ".join(board[i : i + cols]) for i in range(0, len(board), cols))


def pinned_boards() -> dict[tuple[str, str], tuple]:
    """Boards the server already stored, read-only so a simulation never pins new days."""
    if not store.DB_PATH.exists():
        return {}
    conn = sqlite3.connect(f"file:{store.DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        return {(d, lang): (w, r, c, s) for d, lang, w, r, c, s in conn.execute(
            "SELECT date, lang, word, rows, cols, start FROM puzzles")}
    except sqlite3.OperationalError:  # a database from before languages
        return {}
    finally:
        conn.close()


def simulate(start: date, end: date, langs: list[str], max_states: int, fast: bool) -> None:
    pinned = pinned_boards()
    print(f"{'date':<10}  {'#':>3}  {'lang':<5}  {'word':<6}  {'size':<4}  {'moves':>5}  {'states':>8}  {'time':>6}  source")
    results = []
    for lang in langs:
        day = start
        while day <= end:
            row = pinned.get((day.isoformat(), lang))
            if row:
                word, rows, cols, board = row
                source = "pinned"
            else:
                p = daily(day, lang)
                word, rows, cols, board = p.word, p.rows, p.cols, p.start
                source = "generated"
            t0 = time.perf_counter()
            try:
                if fast:
                    path, expanded = quick(board, word, rows, cols), "-"
                else:
                    path, expanded = solve(board, word, rows, cols, max_states)
                moves, shown = len(path), str(len(path))
            except TooHard as e:
                expanded, moves, shown = e.expanded, None, f">={e.bound}"
            took = time.perf_counter() - t0
            results.append((lang, len(word), moves))
            print(f"{day.isoformat():<10}  {number(day):>3}  {lang:<5}  {word:<6}  {rows}x{cols:<2}  "
                  f"{shown:>5}  {expanded:>8}  {took:>5.2f}s  {source}", flush=True)
            day += timedelta(days=1)

    kind = "Quick-route" if fast else "Optimal"
    print(f"\n{kind} moves by word length (boards that hit the state cap are left out of min/avg/max)")
    print(f"{'lang':<5}  {'len':>3}  {'days':>4}  {'min':>3}  {'avg':>5}  {'max':>3}  capped")
    for lang in langs:
        for length in sorted({n for l, n, _ in results if l == lang}):
            everything = [m for l, n, m in results if l == lang and n == length]
            moves = [m for m in everything if m is not None]
            stats = (f"{min(moves):>3}  {sum(moves) / len(moves):>5.1f}  {max(moves):>3}" if moves
                     else f"{'-':>3}  {'-':>5}  {'-':>3}")
            print(f"{lang:<5}  {length:>3}  {len(everything):>4}  {stats}  {len(everything) - len(moves)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    one = sub.add_parser("board", help="solve one board")
    one.add_argument("board", help='row-major letters, "." for the gap')
    one.add_argument("word")
    one.add_argument("--cols", type=int, required=True)
    one.add_argument("--quick", action="store_true", help="a good route in well under a second, not always the shortest")

    sim = sub.add_parser("simulate", help="solve every daily board in a date range")
    sim.add_argument("--from", dest="start", type=date.fromisoformat, default=LAUNCH)
    sim.add_argument("--to", dest="end", type=date.fromisoformat, default=date.today())
    sim.add_argument("--lang", choices=list(LANGS), action="append", help="repeatable; default: all")
    sim.add_argument("--max-states", type=int, default=3_000_000,
                     help="give up on a board after expanding this many states and report a lower bound "
                     "(roughly 0.5 GB of RAM per million)")
    sim.add_argument("--quick", action="store_true", help="good routes in well under a second each, not always the shortest")

    args = parser.parse_args()
    if args.cmd == "board":
        board, word = args.board.upper(), args.word.upper()
        if len(board) % args.cols or board.count(EMPTY) != 1:
            parser.error(f"board must be rows x {args.cols} cells with exactly one {EMPTY!r}")
        rows = len(board) // args.cols
        print(show(board, args.cols))
        if args.quick:
            path = quick(board, word, rows, args.cols)
            print(f"\n{word}: {len(path)} moves (quick route, may not be the shortest)")
        else:
            path, expanded = solve(board, word, rows, args.cols)
            print(f"\n{word}: {len(path)} moves, the fewest possible ({expanded} states expanded)")
        for n, step in enumerate(describe(board, path, args.cols), 1):
            print(f"{n:>3}. {step}")
    else:
        simulate(args.start, args.end, args.lang or list(LANGS), args.max_states, args.quick)


if __name__ == "__main__":
    main()
