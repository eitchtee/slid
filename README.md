# Slid

A new word sliding puzzle every day.

Slide lettered tiles into the gap until the day's word reads left to right in a
row or top to bottom in a column. Your score is the number of moves. Everyone
gets the same puzzle each day, and every past day stays playable.

## How to play

1. Tap a tile next to the empty space to slide it in, or swipe it. On a keyboard, use the
   arrow keys or WASD.
2. Swipe a tile further along the empty space's row or column and every tile between them
   moves along with it.
3. Spell the day's word left to right in a row, or top to bottom in a column. A 3-letter
   word only counts when the empty space completes its row or column.
4. Every tile that moves counts as a move. Each day has a challenge, a move count it's known
   to be solvable in: match it, or beat it.

## Features

- **One daily puzzle** (#1 is 2026-09-01). Days rotate evenly through 3-, 4-, 5- and 6-letter
  words. No word repeats until every word of its length has had a day; then that length starts
  over. The date also seeds the board's letters and scramble.
- **Board size follows the word:** 3 and 4 letters play on 4×4, 5 on 4×5, 6 on 4×6.
  A 3-letter word only counts when the gap completes its row or column. Boards are
  built by placing the word, filling the rest with random letters, and random-walking
  the gap away from that solved state, so every board is solvable, and none can be
  solved in fewer than 8 moves.
- **English and Brazilian Portuguese**, each with its own word list (about 2,100 and 1,200
  common words) and daily puzzle. Portuguese words keep their accents on screen (PÃO) while
  the tiles use plain letters (PAO). Picked from the browser's language until the player
  chooses one.
- **A daily challenge and medals:** the challenge is a move count we know the day can be solved
  in: the route a fast solver (`slid/solver.py`) finds when the day is generated, usually within
  a move or two of the optimum, plus 15% slack (`CHALLENGE_SLACK` in `slid/store.py`). Solving at
  or under it earns 🏆; up to 2× it (at least +8 moves) 🥇; up to 3× (at least +16) 🥈; any
  other solve 🥉. The board shows the medal a game is on track
  for, and the calendar shows each solved day's medal. The limits live in `TIERS` in
  `slid/static/app.js`.
- **Past games** in a calendar at `/calendar`, and every game has its own short URL: `/17` is
  game #17 (dated URLs like `/2026-09-17` still work).
- **A share text worth sharing**, spoiler-free: the medal and moves over the challenge
  (`Slid #19 🥇 18/16`), a heatmap of how often you moved the tile in each spot (the word's final
  spot in 🟩, never its letters), your streak, "Can you do better?", and a short link: the home
  page for today's game, `/19` for a past one.
- **Streaks** of days solved on the day itself, shown in the top bar. Catching up on past games
  later doesn't count.
- **No accounts.** Progress lives in the browser's `localStorage`. The server only
  keeps each day's puzzle (and its challenge) in SQLite.
- **Days are stored ahead of time.** On startup and then daily at 09:00 UTC, the server stores
  every day from launch through tomorrow in every language. UTC+14 is the first zone to reach a
  new date, at 10:00 UTC, so no player waits for generation. If that ever fails, the first
  request for a day generates it instead. Once a day is stored, changing the generator or the
  word lists can't alter it.
- **Tap, swipe or keyboard:** tap a tile next to the gap, use the arrow keys / WASD, or swipe on
  touchscreens. Swiping a tile further along the gap's row or column pushes every tile between
  them, one move per tile.
- **Installable PWA** that works offline for days you've already opened.
- **Sound effects** synthesized with [Cuelume](https://github.com/Danilaa1/cuelume).

Built with FastAPI, Jinja, HTMX and Alpine.js. No build step.

## Running locally

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run uvicorn slid.main:app --reload --reload-dir slid
```

Open http://localhost:8000. Add `?debug` to the URL for a button that resets today's game.

Run the tests with:

```sh
uv run pytest
```

## Docker

```sh
cp compose.example.yaml compose.yaml
docker compose up -d --build
```

The container runs as a non-root user on a read-only filesystem, with all Linux
capabilities dropped. Its only writable path is the `slid-data` volume, which holds
the puzzle database: keep it across upgrades. It serves plain HTTP on port 8000, so
put it behind a reverse proxy for HTTPS (needed to install the PWA), and set
`FORWARDED_ALLOW_IPS` in `compose.yaml` to the proxy's address.

Locally the database is `./data/slid.db`; set `SLID_DB` to put it elsewhere.

## Project layout

```
slid/
  main.py       routes
  puzzle.py     daily puzzle generation and the win rule
  solver.py     A* search: the fewest moves, or a good route fast (the daily challenge)
  store.py      SQLite store that pins each day's puzzle and challenge once generated
  words.py      word lists, per language (generated by scripts/build_words.py)
  i18n.py       UI strings and language detection
  templates/    page shell and board
  static/       game logic (app.js), styles, service worker, icons
scripts/
  make_icons.py regenerates the icons (uv run --with pillow python scripts/make_icons.py)
  solve.py      solves a board, or every daily board in a range (see its docstring)
  build_words.py builds slid/words.py from the word sources
tests/
```

## Words

`slid/words.py` is generated by `scripts/build_words.py` (`uv run --with wordfreq python
scripts/build_words.py`); edit the script, not the output. English words come from
[12dicts](http://wordlist.aspell.net/12dicts/) by Alan Beale (public domain), ranked by
[wordfreq](https://github.com/rspeer/wordfreq); Portuguese words from
[fserb/pt-br](https://github.com/fserb/pt-br) by Fernando Serboncini (MIT). Both were then
reviewed by hand: the script keeps the English exclusions and the Portuguese keep-lists.

Editing a list only affects days that aren't stored yet. Stored days are also the history the
next word is picked against, so a new word list never repeats a word already used, and words
added later go out before any repeat.

To add a language, add it to the build script (plain A–Z tiles, real spelling kept), its
strings to `STRINGS` and an entry to `LANGS` in `slid/i18n.py`. Its puzzles start from
launch day, like every language.

## Maintaining

The win rule lives in two places: `word_cells()` in `slid/puzzle.py` (used to
generate boards) and `check()` in `slid/static/app.js` (used while playing). Keep
them in step.

`app.js` and `style.css` are linked with a hash of their contents (`/static/app.js?v=…`), so a
deploy reaches players on their first load: CDNs, browsers and the service worker all see a new
URL. Those URLs are cached for a year; every other static file is revalidated on each request.
Bumping `CACHE` in `slid/static/sw.js` is only needed to clear old copies out of installed apps.
