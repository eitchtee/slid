import datetime as dt
import sqlite3
from collections import Counter
from datetime import date

from slid import main, puzzle, solver, store

# A tiny board one move from solved: sliding T left spells CAT with the gap beside it.
NEAR = puzzle.Puzzle("CAT", 4, 4, "CA.T" + "Q" * 12)


def rows() -> list[tuple]:
    conn = sqlite3.connect(store.DB_PATH)
    try:
        return conn.execute("SELECT date, lang, challenge FROM puzzles ORDER BY date, lang").fetchall()
    finally:
        conn.close()


def test_new_days_are_stored_with_a_challenge():
    day = date(2026, 9, 18)
    p = store.puzzle_for(day, "en")
    assert p.start == puzzle.daily(day, "en", Counter()).start  # an empty history, like this fresh database
    route = len(solver.quick(p.start, p.word, p.rows, p.cols))
    assert p.challenge == store.with_slack(route) > route  # a found route, plus slack
    assert rows() == [("2026-09-18", "en", p.challenge)]


def test_store_pins_the_first_generated_puzzle(monkeypatch):
    day = date(2026, 9, 10)
    first = store.puzzle_for(day, "en")
    # A later change to the generator (or the word list) must not alter a stored day...
    monkeypatch.setattr(store, "daily", lambda d, lang, used=None: NEAR)
    store.puzzle_for.cache_clear()
    assert store.puzzle_for(day, "en") == first
    # ...while a day (or language) that was never stored uses the new generator.
    assert store.puzzle_for(day, "pt-BR") == puzzle.Puzzle("CAT", 4, 4, NEAR.start, challenge=store.with_slack(1))


def test_ensure_through_stores_every_day_since_launch(monkeypatch):
    monkeypatch.setattr(store, "daily", lambda d, lang, used=None: NEAR)
    assert store.ensure_through(date(2026, 9, 3), ("en", "pt-BR")) == 6
    assert [(d, lang) for d, lang, _ in rows()] == [
        (f"2026-09-0{n}", lang) for n in (1, 2, 3) for lang in ("en", "pt-BR")
    ]
    assert all(challenge == store.with_slack(1) for *_, challenge in rows())
    # Running again only adds what's missing.
    assert store.ensure_through(date(2026, 9, 3), ("en", "pt-BR")) == 0
    assert store.ensure_through(date(2026, 9, 4), ("en", "pt-BR")) == 2


def test_migrates_databases_from_before_languages_and_challenges():
    old = "OLD." + "Q" * 12
    conn = sqlite3.connect(store.DB_PATH)
    with conn:
        conn.execute(
            "CREATE TABLE puzzles (date TEXT PRIMARY KEY, word TEXT NOT NULL, rows INTEGER NOT NULL, "
            "cols INTEGER NOT NULL, start TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute("INSERT INTO puzzles (date, word, rows, cols, start) VALUES ('2026-09-05', 'OLD', 4, 4, ?)", (old,))
    conn.close()
    # Old rows become English and get their challenge the first time they're read (OLD is already solved).
    assert store.puzzle_for(date(2026, 9, 5), "en") == puzzle.Puzzle("OLD", 4, 4, old, challenge=0)
    assert rows() == [("2026-09-05", "en", 0)]
    assert store.puzzle_for(date(2026, 9, 5), "pt-BR").word != "OLD"


def test_ensure_through_fills_missing_challenges(monkeypatch):
    monkeypatch.setattr(store, "daily", lambda d, lang, used=None: NEAR)
    store.ensure_through(date(2026, 9, 1), ("en",))
    conn = sqlite3.connect(store.DB_PATH)
    with conn:
        conn.execute("UPDATE puzzles SET challenge = NULL")
    conn.close()
    assert store.ensure_through(date(2026, 9, 1), ("en",)) == 1
    assert rows() == [("2026-09-01", "en", store.with_slack(1))]


def test_pregeneration_runs_an_hour_before_the_first_time_zone_reaches_tomorrow():
    utc = dt.UTC
    # UTC+14 reaches a new date at 10:00 UTC, so the run is at 09:00 UTC every day.
    assert main.next_pregeneration(dt.datetime(2026, 9, 18, 3, 0, tzinfo=utc)) == dt.datetime(2026, 9, 18, 9, 0, tzinfo=utc)
    assert main.next_pregeneration(dt.datetime(2026, 9, 18, 9, 0, tzinfo=utc)) == dt.datetime(2026, 9, 19, 9, 0, tzinfo=utc)
    assert main.next_pregeneration(dt.datetime(2026, 9, 18, 23, 59, tzinfo=utc)) == dt.datetime(2026, 9, 19, 9, 0, tzinfo=utc)
    # A time given in another zone is compared correctly (15:00 in UTC+14 is 01:00 UTC).
    plus14 = dt.timezone(dt.timedelta(hours=14))
    assert main.next_pregeneration(dt.datetime(2026, 9, 18, 15, 0, tzinfo=plus14).astimezone(utc)) == dt.datetime(
        2026, 9, 18, 9, 0, tzinfo=utc
    )


def test_pregenerate_stores_through_tomorrow_utc(monkeypatch):
    monkeypatch.setattr(store, "daily", lambda d, lang, used=None: NEAR)
    main.pregenerate(dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.UTC))
    assert {d for d, _, _ in rows()} == {"2026-09-01", "2026-09-02", "2026-09-03"}
    assert {lang for _, lang, _ in rows()} == {"en", "pt-BR"}


def test_with_slack_rounds_up():
    assert [store.with_slack(n) for n in (0, 1, 8, 13, 20, 26)] == [0, 2, 10, 15, 23, 30]


def test_stored_challenges_get_the_slack_exactly_once():
    # A database from before the slack: its stored challenges are bare routes.
    conn = sqlite3.connect(store.DB_PATH)
    with conn:
        conn.execute(store.SCHEMA)
        conn.execute(
            "INSERT INTO puzzles (date, lang, word, rows, cols, start, challenge) VALUES ('2026-09-02', 'en', 'CAT', 4, 4, ?, 20)",
            (NEAR.start,),
        )
    conn.close()
    assert store.puzzle_for(date(2026, 9, 2), "en").challenge == 23
    # Reconnecting (every request does) must not add it again.
    store.puzzle_for.cache_clear()
    assert store.puzzle_for(date(2026, 9, 2), "en").challenge == 23
    store.ensure_through(date(2026, 9, 1), ("en",))
    assert dict((d, c) for d, _, c in rows())["2026-09-02"] == 23

