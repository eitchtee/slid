"""Daily puzzle generation.

A board is a row-major string of ``rows * cols`` characters, with ``EMPTY``
marking the single empty cell. Playing happens in the browser (static/app.js);
the server only builds each day's starting board.
"""

import random
import string
from collections import Counter
from dataclasses import dataclass
from datetime import date

from .words import WORDS, plain

LAUNCH = date(2026, 9, 1)  # puzzle #1
EMPTY = "."
ROWS = 4
COLS_FOR_LENGTH = {3: 4, 4: 4, 5: 5, 6: 6}
LENGTHS = tuple(sorted(COLS_FOR_LENGTH))
SCRAMBLE_STEPS = 240
# No board may be solvable in fewer moves than this. Filler letters sometimes line up so
# the word is only a move or two away, so those boards get scrambled further.
MIN_MOVES = 8
# A word this short only counts when the gap shares its row or column. On a 4x4
# board that means the word plus the gap fill the whole line.
GAP_RULE_LENGTH = 3


@dataclass(frozen=True)
class Puzzle:
    word: str  # tile spelling, plain A-Z
    rows: int
    cols: int
    start: str
    # A move count we know is reachable (the store fills it in with solver.quick()).
    challenge: int | None = None
    display: str | None = None  # real spelling, e.g. PÃO for PAO; None when it's the same

    @property
    def shown(self) -> str:
        return self.display or self.word


def _order(lang: str, length: int) -> list[str]:
    words = list(WORDS[lang][length])
    random.Random(f"slid:words:{lang}:{length}").shuffle(words)
    return words


# Each language and length has a fixed shuffled order that its words are handed out in.
ORDERS = {lang: {n: _order(lang, n) for n in pools} for lang, pools in WORDS.items()}


def number(day: date) -> int:
    return (day - LAUNCH).days + 1


def length_for(day: date) -> int:
    """Days rotate evenly through the word lengths: every block of four days from launch
    has one of each, in a shuffled order, so board sizes stay varied."""
    block, position = divmod(number(day) - 1, len(LENGTHS))
    order = list(LENGTHS)
    random.Random(f"slid:lengths:{block}").shuffle(order)
    return order[position]


def word_for(day: date, lang: str, used: Counter | None = None) -> str:
    """The day's word, in its real spelling.

    ``used`` counts the (tile spellings of) words already given out in this language. The
    pick is the first word, in its length's fixed order, that has been used the fewest
    times: no word repeats until every word of that length has had a day, and words added
    to a list later go out before any repeat. Without ``used``, the history is assumed to
    have followed that order from launch, which gives the same answer when it has.
    """
    order = ORDERS[lang][length_for(day)]
    if used is None:
        return order[((number(day) - 1) // len(LENGTHS)) % len(order)]
    fewest = min(used[plain(w)] for w in order)
    return next(w for w in order if used[plain(w)] == fewest)


def daily(day: date, lang: str, used: Counter | None = None) -> Puzzle:
    """Everything about a day's puzzle is derived from the date, language and word history."""
    display = word_for(day, lang, used)
    word = plain(display)
    rng = random.Random(f"slid:{lang}:{day.isoformat()}")
    rows, cols = ROWS, COLS_FOR_LENGTH[len(word)]
    solved = _solved_board(rng, word, rows, cols)
    start = _scramble(rng, solved, word, rows, cols)
    from .solver import needs_at_least  # here, not at the top: the solver imports this module

    while not needs_at_least(start, word, rows, cols, MIN_MOVES):
        start = _scramble(rng, start, word, rows, cols)
    return Puzzle(word=word, rows=rows, cols=cols, start=start, display=None if display == word else display)


def _lines(rows: int, cols: int) -> list[list[int]]:
    """Every row, then every column, as lists of cells in reading order."""
    return [[r * cols + c for c in range(cols)] for r in range(rows)] + [
        [r * cols + c for r in range(rows)] for c in range(cols)
    ]


def _solved_board(rng: random.Random, word: str, rows: int, cols: int) -> str:
    placements = [
        (line, line[at : at + len(word)])
        for line in _lines(rows, cols)
        for at in range(len(line) - len(word) + 1)
    ]
    line, word_cells = rng.choice(placements)

    board = [rng.choice(string.ascii_uppercase) for _ in range(rows * cols)]
    for cell, letter in zip(word_cells, word):
        board[cell] = letter
    # The gap goes next to a short word, so the solved state obeys the gap rule.
    gap_cells = line if len(word) <= GAP_RULE_LENGTH else range(rows * cols)
    board[rng.choice([i for i in gap_cells if i not in word_cells])] = EMPTY
    return "".join(board)


def _scramble(rng: random.Random, board: str, word: str, rows: int, cols: int) -> str:
    """Random-walk the gap from a solved board, so the result is always solvable."""
    previous = None
    steps = 0
    while steps < SCRAMBLE_STEPS or is_solved(board, word, rows, cols):
        gap = board.index(EMPTY)
        options = [n for n in neighbors(gap, rows, cols) if n != previous]
        tile = rng.choice(options)
        board = swap(board, gap, tile)
        previous = gap
        steps += 1
    return board


def neighbors(cell: int, rows: int, cols: int) -> list[int]:
    r, c = divmod(cell, cols)
    return [
        (r + dr) * cols + (c + dc)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
        if 0 <= r + dr < rows and 0 <= c + dc < cols
    ]


def swap(board: str, a: int, b: int) -> str:
    cells = list(board)
    cells[a], cells[b] = cells[b], cells[a]
    return "".join(cells)


def word_cells(board: str, word: str, rows: int, cols: int) -> list[int]:
    """Cells spelling ``word`` left-to-right in a row or top-to-bottom in a column.

    Short words (see GAP_RULE_LENGTH) only count when the gap is in the same line.
    """
    for line in _lines(rows, cols):
        text = "".join(board[i] for i in line)
        if len(word) <= GAP_RULE_LENGTH and EMPTY not in text:
            continue
        at = text.find(word)
        if at != -1:
            return line[at : at + len(word)]
    return []


def is_solved(board: str, word: str, rows: int, cols: int) -> bool:
    return bool(word_cells(board, word, rows, cols))
