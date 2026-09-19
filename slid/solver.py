"""Solving Slid boards: the fewest moves, or a good route fast.

The server uses quick() to set each day's challenge; scripts/solve.py uses solve()
to study boards.

Pushing k tiles at once costs k moves, the same as k single slides, so single-tile
moves are enough. The search is A* over board states, where a move swaps the gap
with a neighbouring tile and the goal is a solved board (see puzzle.word_cells).

The heuristic is a lower bound on the moves left, so plain A* returns an optimal
answer: for each place the word could end up, every letter still needs at least
the Manhattan distance from its nearest matching tile, and each move shifts one
tile one cell. For words under the gap rule, the gap also has to reach the word's
line, and it moves one cell per move too; the larger of those two bounds is used.
"""

import heapq
import itertools

from .puzzle import EMPTY, GAP_RULE_LENGTH, _lines, neighbors, swap


def goals(word: str, rows: int, cols: int) -> list[tuple[list[int], list[int] | None]]:
    """Every (cells the word would occupy, cells the gap may be in or None) that counts as solved."""
    out = []
    for line in _lines(rows, cols):
        for at in range(len(line) - len(word) + 1):
            cells = line[at : at + len(word)]
            gap_cells = [c for c in line if c not in cells] if len(word) <= GAP_RULE_LENGTH else None
            out.append((cells, gap_cells))
    return out


class TooHard(Exception):
    """The search hit its state cap. ``bound`` is a proven lower bound on the optimum."""

    def __init__(self, bound: int, expanded: int):
        super().__init__(f"at least {bound} moves")
        self.bound, self.expanded = bound, expanded


def solve(
    board: str,
    word: str,
    rows: int,
    cols: int,
    max_states: int | None = None,
    weight: float = 1.0,
    give_up_at: int | None = None,
) -> tuple[list[int], int]:
    """The tiles to move, in order (as the cell each one starts from), and how many states were expanded.

    With ``weight`` above 1 this is weighted A*: it trusts the heuristic more and dives for a
    solution instead of proving none is shorter. The route is then at most ``weight`` times
    the optimum, and usually much closer, found in a fraction of the time.

    ``give_up_at`` (unweighted only) stops with TooHard once no route shorter than that many
    moves can exist, which is cheap to establish for small numbers.
    """
    size = rows * cols
    dist = [[abs(a // cols - b // cols) + abs(a % cols - b % cols) for b in range(size)] for a in range(size)]
    letters = sorted(set(word))
    # Per placement: (letter index, the cells that letter must fill) for each distinct letter,
    # and the gap cells if the gap rule applies.
    placements = [
        (
            [(k, tuple(cell for cell, ch in zip(cells, word) if ch == letter)) for k, letter in enumerate(letters)],
            gap_cells,
        )
        for cells, gap_cells in goals(word, rows, cols)
    ]
    slot = {letter: k for k, letter in enumerate(letters)}
    # Only the cells each letter could end up in matter to the heuristic.
    relevant = [sorted({c for needs, _ in placements for j, cells in needs if j == k for c in cells}) for k in range(len(letters))]

    def h(state: str) -> int:
        """0 exactly when the state is solved, so it doubles as the goal test."""
        tiles: list[list[int]] = [[] for _ in letters]
        for i, ch in enumerate(state):
            k = slot.get(ch)
            if k is not None:
                tiles[k].append(i)
        # nearest[k][cell]: how far the closest tile with letter k is from that cell.
        nearest = []
        for k, ts in enumerate(tiles):
            near = {}
            for cell in relevant[k]:
                row = dist[cell]
                m = size
                for t in ts:
                    if row[t] < m:
                        m = row[t]
                near[cell] = m
            nearest.append(near)
        # A repeated letter (the E's in CHEESE) needs a different tile for each of its cells, so
        # it costs the cheapest matching of tiles to cells, not each cell's nearest tile. Letters
        # repeat at most a few times, so trying every assignment is cheap.
        matched: dict[tuple[int, tuple[int, ...]], int] = {}

        def cost(k: int, cells: tuple[int, ...]) -> int:
            if len(cells) == 1:
                return nearest[k][cells[0]]
            if (k, cells) not in matched:
                matched[k, cells] = min(
                    sum(dist[c][t] for c, t in zip(cells, pick)) for pick in itertools.permutations(tiles[k], len(cells))
                )
            return matched[k, cells]

        gap = state.index(EMPTY)
        best = size * size
        for needs, gap_cells in placements:
            bound = sum(cost(k, cells) for k, cells in needs)
            if gap_cells is not None:
                bound = max(bound, min(dist[gap][g] for g in gap_cells))
            if bound < best:
                best = bound
                if best == 0:
                    break
        return best

    if h(board) == 0:
        return [], 0
    tie = itertools.count()
    # (f, -g, tiebreak, state): prefer deeper states on ties, they're closer to a goal.
    frontier = [(weight * h(board), 0, next(tie), board)]
    # state -> g * 64 + where the gap was before the move that reached it (packed to save memory).
    seen = {board: size}
    expanded = 0
    while frontier:
        f, neg_g, _, state = heapq.heappop(frontier)
        g = -neg_g
        if g > seen[state] >> 6:
            continue  # a shorter route to this state was found after it was queued
        expanded += 1
        if give_up_at is not None and f >= give_up_at:
            raise TooHard(f, expanded)
        if max_states and expanded > max_states:
            # Unweighted, f is the lowest open bound, so nothing shorter exists; weighted, it proves nothing.
            raise TooHard(f if weight == 1 else None, expanded)
        gap = state.index(EMPTY)
        for tile in neighbors(gap, rows, cols):
            nxt = swap(state, gap, tile)
            old = seen.get(nxt)
            if old is not None and old >> 6 <= g + 1:
                continue
            seen[nxt] = (g + 1) << 6 | gap
            est = h(nxt)
            if est == 0:
                path = []
                while nxt != board:
                    before = seen[nxt] & 63
                    path.append(nxt.index(EMPTY))  # the moved tile started where the gap is now
                    nxt = swap(nxt, nxt.index(EMPTY), before)
                return path[::-1], expanded
            heapq.heappush(frontier, (g + 1 + weight * est, -(g + 1), next(tie), nxt))
    raise ValueError("unsolvable board")


def needs_at_least(board: str, word: str, rows: int, cols: int, moves: int) -> bool:
    """Whether every route that solves the board takes at least ``moves`` moves.

    Cheap for small numbers: plain A* only has to look that deep, and on most boards the
    heuristic alone already proves it.
    """
    try:
        path, _ = solve(board, word, rows, cols, give_up_at=moves)
    except TooHard:
        return True
    return len(path) >= moves  # plain A* finds the shortest route


# Weights and state budgets for quick(): each weight stalls on some boards that another
# weight finishes instantly, so they take turns with small budgets before the last resort.
FIND = ((3, 40_000), (6, 40_000), (12, 60_000))
SHORTEN = (2, 20_000)


def quick(board: str, word: str, rows: int, cols: int) -> list[int]:
    """A good route, fast: usually within a move or two of the optimum.

    Weighted searches take turns with small budgets until one finds a route, then a more
    careful pass tries to shorten it. Measured on 800 upcoming boards (both languages):
    about 0.1 s on average, 0.5 s at the 95th percentile, under 2 s at worst. If every
    budget runs out, an unbudgeted search finishes the job, slower but certain.
    """
    route = None
    for weight, budget in FIND:
        try:
            route, _ = solve(board, word, rows, cols, max_states=budget, weight=weight)
            break
        except TooHard:
            continue
    if route is None:
        route, _ = solve(board, word, rows, cols, weight=FIND[0][0])
    try:
        closer, _ = solve(board, word, rows, cols, max_states=SHORTEN[1], weight=SHORTEN[0])
        if len(closer) < len(route):
            route = closer
    except TooHard:
        pass
    return route
