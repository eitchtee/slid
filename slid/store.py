"""Keeps every day's puzzle exactly as it was first generated.

The generator is deterministic, but changing it (a new word list, board sizes, a
different scramble) would silently turn old days into different puzzles,
breaking saved games and shared links. So each day is stored in SQLite the first
time it's generated, and read back from then on. Each language has its own puzzle
per day.

The stored days are also the word history: a new day gets a word no stored day in
its language has used yet, until that word length runs out (see puzzle.word_for).

Days are normally stored ahead of time by ensure_through() (see main.py); a request
for a day that isn't stored yet generates and stores it on the spot instead.
"""

import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from .puzzle import LAUNCH, Puzzle, daily
from .solver import quick
from .words import WORDS

# Docker sets SLID_DB to a path on a volume; locally it lives in ./data (gitignored).
DB_PATH = Path(os.environ.get("SLID_DB", Path(__file__).parent.parent / "data" / "slid.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS puzzles (
    date       TEXT NOT NULL,     -- YYYY-MM-DD
    lang       TEXT NOT NULL,     -- a key of i18n.LANGS
    word       TEXT NOT NULL,     -- tile spelling, plain A-Z
    rows       INTEGER NOT NULL,
    cols       INTEGER NOT NULL,
    start      TEXT NOT NULL,     -- rows*cols characters, row by row, "." is the gap
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    challenge  INTEGER,           -- moves in a known route (solver.quick); NULL only for days stored before it existed
    display    TEXT,              -- real spelling when it differs from word (PÃO for PAO)
    PRIMARY KEY (date, lang)
)
"""
SELECT = "SELECT word, rows, cols, start, challenge, display FROM puzzles WHERE date = ? AND lang = ?"


@contextmanager
def _writing(conn: sqlite3.Connection):
    """A transaction that takes the write lock up front, so a read inside it can't go stale."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(puzzles)")}


def _migrate(conn: sqlite3.Connection) -> None:
    # Databases from before languages keyed puzzles by date alone; those were all English.
    if (columns := _columns(conn)) and "lang" not in columns:
        conn.execute("ALTER TABLE puzzles RENAME TO puzzles_pre_lang")
        conn.execute(SCHEMA)
        conn.execute(
            "INSERT INTO puzzles (date, lang, word, rows, cols, start, created_at) "
            "SELECT date, 'en', word, rows, cols, start, created_at FROM puzzles_pre_lang"
        )
        conn.execute("DROP TABLE puzzles_pre_lang")
    conn.execute(SCHEMA)
    # Columns added later. Days stored before challenges get theirs the next time they're read.
    for column in ("challenge INTEGER", "display TEXT"):
        if column.split()[0] not in _columns(conn):
            conn.execute(f"ALTER TABLE puzzles ADD COLUMN {column}")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit mode: transactions are opened explicitly with _writing().
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    with _writing(conn):
        _migrate(conn)
    return conn


def _challenge(p: Puzzle) -> int:
    return len(quick(p.start, p.word, p.rows, p.cols))


def _read(conn: sqlite3.Connection, key: tuple[str, str]) -> Puzzle | None:
    row = conn.execute(SELECT, key).fetchone()
    if row is None:
        return None
    word, rows, cols, start, challenge, display = row
    return Puzzle(word, rows, cols, start, challenge=challenge, display=display)


def _load_or_create(conn: sqlite3.Connection, day: date, lang: str) -> Puzzle:
    key = (day.isoformat(), lang)
    p = _read(conn, key)
    if p is None:
        with _writing(conn):
            # Checked again under the lock: another worker may have stored it meanwhile.
            p = _read(conn, key)
            if p is None:
                used = Counter(word for (word,) in conn.execute("SELECT word FROM puzzles WHERE lang = ?", (lang,)))
                p = daily(day, lang, used)
                p = replace(p, challenge=_challenge(p))
                conn.execute(
                    "INSERT INTO puzzles (date, lang, word, rows, cols, start, challenge, display) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (*key, p.word, p.rows, p.cols, p.start, p.challenge, p.display),
                )
    if p.challenge is None:
        p = replace(p, challenge=_challenge(p))
        with _writing(conn):
            conn.execute(
                "UPDATE puzzles SET challenge = ? WHERE date = ? AND lang = ? AND challenge IS NULL",
                (p.challenge, *key),
            )
    return p


@lru_cache(maxsize=256)
def puzzle_for(day: date, lang: str) -> Puzzle:
    """The day's puzzle: the stored one, or generated and stored now if it isn't yet."""
    conn = _connect()
    try:
        return _load_or_create(conn, day, lang)
    finally:
        conn.close()


def ensure_through(end: date, langs=tuple(WORDS)) -> int:
    """Stores every day from LAUNCH through ``end``, in every language, that isn't stored yet.

    Days are generated in date order, so each one's word history is complete. Also fills in
    challenges for days stored before they existed. Returns how many days it wrote. Once a
    day is stored, changes to the word lists or the generator can't touch it.
    """
    conn = _connect()
    try:
        done = set(conn.execute("SELECT date, lang FROM puzzles WHERE challenge IS NOT NULL"))
        written = 0
        day = LAUNCH
        while day <= end:
            for lang in langs:
                if (day.isoformat(), lang) not in done:
                    _load_or_create(conn, day, lang)
                    written += 1
            day += timedelta(days=1)
        return written
    finally:
        conn.close()
