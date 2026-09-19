from collections import Counter
from datetime import date, timedelta

import pytest

from slid import puzzle
from slid.i18n import LANGS
from slid.puzzle import LAUNCH, LENGTHS, ORDERS, daily, is_solved, length_for, word_cells, word_for
from slid.solver import needs_at_least
from slid.words import WORDS, plain

DAYS = [LAUNCH + timedelta(days=n) for n in range(400)]
LANG_DAYS = [(lang, day) for lang in LANGS for day in DAYS]


@pytest.mark.parametrize("lang", LANGS)
def test_word_pools(lang):
    assert set(WORDS[lang]) == set(LENGTHS)
    for length, words in WORDS[lang].items():
        # Real spellings may carry accents; the tiles are plain A-Z of the right length.
        assert all(len(plain(w)) == length and plain(w).isalpha() and plain(w).isascii() for w in words)
        assert len({plain(w) for w in words}) == len(words), "two words would share the same tiles"


def test_plain_drops_accents_and_cedillas():
    assert plain("PÃO") == "PAO"
    assert plain("MAÇÃ") == "MACA"
    assert plain("avô") == "AVO"


def test_numbering_starts_at_launch():
    assert LAUNCH == date(2026, 9, 1)
    assert puzzle.number(LAUNCH) == 1
    assert puzzle.number(date(2026, 9, 18)) == 18


def test_lengths_rotate_evenly():
    for block in range(100):
        days = [LAUNCH + timedelta(days=4 * block + k) for k in range(4)]
        assert sorted(length_for(d) for d in days) == list(LENGTHS)


def simulate(lang: str, days: int, used: Counter | None = None) -> list[str]:
    """Words handed out day by day, the way the store does it, with a running history."""
    used = Counter() if used is None else used
    words = []
    for n in range(days):
        word = word_for(LAUNCH + timedelta(days=n), lang, used)
        used[plain(word)] += 1
        words.append(word)
    return words


@pytest.mark.parametrize("lang", LANGS)
def test_no_word_repeats_until_its_length_runs_out(lang):
    shortest = min(len(ws) for ws in WORDS[lang].values())
    words = simulate(lang, 4 * shortest)  # every length gets `shortest` days
    assert len(set(words)) == len(words)


@pytest.mark.parametrize("lang", LANGS)
def test_a_length_starts_over_once_every_word_has_had_a_day(lang):
    n = 3
    order = ORDERS[lang][n]
    words = [w for w in simulate(lang, 4 * (len(order) + 2)) if len(plain(w)) == n]
    assert words[: len(order)] == order
    assert words[len(order) :] == order[:2]


@pytest.mark.parametrize("lang", LANGS)
def test_history_free_pick_matches_the_running_history(lang):
    days = 4 * 150
    assert simulate(lang, days) == [word_for(LAUNCH + timedelta(days=d), lang) for d in range(days)]


def test_words_already_used_are_skipped():
    day = LAUNCH  # a 3-, 4-, 5- or 6-letter day; take its length's first two words
    order = ORDERS["en"][length_for(day)]
    assert word_for(day, "en", Counter()) == order[0]
    assert word_for(day, "en", Counter({plain(order[0]): 1})) == order[1]
    # Once everything has been used once, the fewest-used word goes first again.
    everything = Counter({plain(w): 1 for w in order})
    everything[plain(order[0])] = 2
    assert word_for(day, "en", everything) == order[1]


def test_display_keeps_the_real_spelling():
    for d in range(200):
        p = daily(LAUNCH + timedelta(days=d), "pt-BR")
        assert plain(p.shown) == p.word
        if p.display is not None:
            assert p.display != p.word
            return
    raise AssertionError("expected an accented word in 200 days")


def test_languages_get_different_puzzles():
    day = date(2026, 9, 18)
    en, pt = daily(day, "en"), daily(day, "pt-BR")
    assert en.word in {plain(w) for w in WORDS["en"][len(en.word)]}
    assert pt.word in {plain(w) for w in WORDS["pt-BR"][len(pt.word)]}
    assert en != pt


def test_daily_is_deterministic_and_varies():
    assert daily(date(2026, 9, 18), "en") == daily(date(2026, 9, 18), "en")
    assert len({daily(d, "en").start for d in DAYS[:30]}) == 30


@pytest.mark.parametrize("lang", LANGS)
def test_all_lengths_show_up(lang):
    assert {len(daily(d, lang).word) for d in DAYS} == set(WORDS[lang])


@pytest.mark.parametrize(("lang", "day"), LANG_DAYS)
def test_daily_board_shape(lang, day):
    p = daily(day, lang)
    assert p.rows == 4
    assert p.cols == puzzle.COLS_FOR_LENGTH[len(p.word)]
    assert len(p.start) == p.rows * p.cols
    assert p.start.count(puzzle.EMPTY) == 1
    assert not is_solved(p.start, p.word, p.rows, p.cols)
    assert needs_at_least(p.start, p.word, p.rows, p.cols, puzzle.MIN_MOVES)
    for letter in set(p.word):
        assert p.start.count(letter) >= p.word.count(letter)


def test_solved_boards_obey_the_gap_rule():
    # The scramble starts from these, so a 3-letter word must already share its line with the gap.
    for n in range(200):
        board = puzzle._solved_board(puzzle.random.Random(n), "CAT", 4, 4)
        assert is_solved(board, "CAT", 4, 4), board


def test_neighbors_do_not_wrap_rows():
    assert sorted(puzzle.neighbors(3, 4, 4)) == [2, 7]
    assert sorted(puzzle.neighbors(5, 4, 4)) == [1, 4, 6, 9]


def test_word_cells_row_and_column():
    assert word_cells("XROPE" + "Q" * 14 + ".", "ROPE", 4, 5) == [1, 2, 3, 4]
    col = "QBQQ" + "QEQQ" + "QEQQ" + "QRQ."
    assert word_cells(col, "BEER", 4, 4) == [1, 5, 9, 13]


def test_three_letter_word_needs_the_gap_in_its_row():
    assert word_cells("CAT." + "QQQQ" + "QQQQ" + "QQQQ", "CAT", 4, 4) == [0, 1, 2]
    assert word_cells(".CAT" + "QQQQ" + "QQQQ" + "QQQQ", "CAT", 4, 4) == [1, 2, 3]
    assert not is_solved("CATQ" + "QQQQ" + "QQQQ" + "QQQ.", "CAT", 4, 4)


def test_three_letter_word_needs_the_gap_in_its_column():
    assert word_cells("CQQQ" + "AQQQ" + "TQQQ" + ".QQQ", "CAT", 4, 4) == [0, 4, 8]
    assert not is_solved("CQQQ" + "AQQQ" + "TQQQ" + "QQQ.", "CAT", 4, 4)


def test_longer_words_do_not_need_the_gap():
    assert is_solved("ROPE" + "QQQQ" + "QQQQ" + "QQQ.", "ROPE", 4, 4)
    assert is_solved("XROPE" + "Q" * 14 + ".", "ROPE", 4, 5)


def test_word_must_read_forwards_and_not_wrap():
    assert not is_solved("TAC." + "QQQQ" + "QQQQ" + "QQQQ", "CAT", 4, 4)
    assert not is_solved("QQCA" + "T.QQ" + "QQQQ" + "QQQQ", "CAT", 4, 4)
