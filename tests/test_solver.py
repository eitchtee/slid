import random

import pytest

from slid import puzzle
from slid.solver import TooHard, needs_at_least, quick, solve


def replay(board: str, path: list[int], rows: int, cols: int) -> str:
    for tile in path:
        gap = board.index(puzzle.EMPTY)
        assert tile in puzzle.neighbors(gap, rows, cols), "every step must slide a tile next to the gap"
        board = puzzle.swap(board, gap, tile)
    return board


def scrambled(seed: int, word: str, cols: int, steps: int) -> str:
    rng = random.Random(seed)
    board = puzzle._solved_board(rng, word, 4, cols)
    previous = None
    while steps > 0 or puzzle.is_solved(board, word, 4, cols):
        gap = board.index(puzzle.EMPTY)
        tile = rng.choice([n for n in puzzle.neighbors(gap, 4, cols) if n != previous])
        board, previous, steps = puzzle.swap(board, gap, tile), gap, steps - 1
    return board


CASES = [(n, word, cols) for n in range(4) for word, cols in [("CAT", 4), ("ROPE", 4), ("GRAPE", 5), ("BRIDGE", 6)]]


@pytest.mark.parametrize(("seed", "word", "cols"), CASES)
def test_quick_routes_solve_and_never_beat_the_optimum(seed, word, cols):
    board = scrambled(seed, word, cols, steps=14)
    best, _ = solve(board, word, 4, cols)
    route = quick(board, word, 4, cols)
    assert puzzle.is_solved(replay(board, best, 4, cols), word, 4, cols)
    assert puzzle.is_solved(replay(board, route, 4, cols), word, 4, cols)
    assert len(route) >= len(best)


def test_solved_board_needs_no_moves():
    assert solve("CAT." + "Q" * 12, "CAT", 4, 4) == ([], 0)
    assert quick("CAT." + "Q" * 12, "CAT", 4, 4) == []


def test_three_letter_goal_needs_the_gap():
    # CAT is spelled but the gap is elsewhere: one move brings the gap into the row.
    path, _ = solve("CATQ" + "QQQ." + "Q" * 8, "CAT", 4, 4)
    assert len(path) == 1


def test_capped_search_reports_a_lower_bound():
    board = scrambled(1, "BRIDGE", 6, steps=60)
    with pytest.raises(TooHard) as err:
        solve(board, "BRIDGE", 4, 6, max_states=50)
    assert err.value.bound >= 1


@pytest.mark.parametrize(("seed", "word", "cols"), CASES[:8])
def test_needs_at_least_matches_the_optimum(seed, word, cols):
    board = scrambled(seed, word, cols, steps=10)
    best = len(solve(board, word, 4, cols)[0])
    assert needs_at_least(board, word, 4, cols, best)
    assert not needs_at_least(board, word, 4, cols, best + 1)
