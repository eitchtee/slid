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

# The challenge gives this much slack over the route solver.quick() finds, in percent, so it's a
# target good players can reach rather than a near-optimal one.
CHALLENGE_SLACK = 15

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
    challenge  INTEGER,           -- a known route's moves (solver.quick) + CHALLENGE_SLACK%; NULL only for days stored before it existed
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


def _v1_schema_and_slack(conn: sqlite3.Connection) -> None:
    """The current schema, reached from any older file, with the challenge slack applied."""
    # Files from before languages keyed puzzles by date alone; those were all English.
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
    # Challenges used to be the bare route; stored ones get the slack too (none, on a new file).
    conn.execute(
        "UPDATE puzzles SET challenge = (challenge * (100 + ?) + 99) / 100 WHERE challenge IS NOT NULL",
        (CHALLENGE_SLACK,),
    )


# The database's PRAGMA user_version counts the migrations applied to it: MIGRATIONS[n] takes a
# file from version n to n + 1, once, in its own transaction. Only ever append: editing or
# reordering an entry would skip it, or rerun it, on files that already have it.
MIGRATIONS = [
    _v1_schema_and_slack,
]


# Database files migrate() has brought up to date in this process.
_migrated: set[Path] = set()


def migrate() -> int:
    """Brings the database file up to date and returns its version.

    The server runs this at startup, so a database it can't open or write stops it there rather
    than on a player's first request. Safe to run from several workers at once: each step re-reads
    the version under the write lock before applying anything.
    """
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            while True:
                with _writing(conn):
                    version = conn.execute("PRAGMA user_version").fetchone()[0]
                    if version >= len(MIGRATIONS):  # up to date, or written by a newer version of Slid
                        _migrated.add(DB_PATH)
                        return version
                    MIGRATIONS[version](conn)
                    conn.execute(f"PRAGMA user_version = {version + 1}")
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as e:
        raise RuntimeError(f"Can't open or update the puzzle database at {DB_PATH}: {e}") from e


def _connect() -> sqlite3.Connection:
    # Scripts and tests use the store without starting the server, so migrate here too; it's a
    # single version check once a file is known to be current.
    if DB_PATH not in _migrated:
        migrate()
    # Autocommit mode: transactions are opened explicitly with _writing().
    return sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)


def with_slack(moves: int) -> int:
    """The challenge for a route of ``moves``: CHALLENGE_SLACK% more, rounded up (integer math)."""
    return (moves * (100 + CHALLENGE_SLACK) + 99) // 100


def _challenge(p: Puzzle) -> int:
    return with_slack(len(quick(p.start, p.word, p.rows, p.cols)))


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
