import json
from collections import Counter
import re
from datetime import date

from fastapi.testclient import TestClient

from slid import i18n, puzzle, store
from slid.main import app
from slid.words import plain

client = TestClient(app)


def board_cfg(day: str, **headers) -> dict:
    res = client.get("/board", params={"date": day}, headers=headers)
    assert res.status_code == 200
    return json.loads(re.search(r"x-data='slid\((.*?)\)'", res.text).group(1))


def test_board_endpoint():
    cfg = board_cfg("2026-09-18")
    p = store.puzzle_for(date(2026, 9, 18), "en")
    assert cfg == {
        "date": "2026-09-18", "lang": "en", "number": 18,
        "word": p.word, "rows": p.rows, "cols": p.cols, "start": p.start, "challenge": p.challenge,
    }
    assert p.start == puzzle.daily(date(2026, 9, 18), "en", Counter()).start  # empty history in a fresh database
    assert cfg["challenge"] > 0
    for bad in ["2099-01-01", "2026-08-31", "nope", "20260918"]:
        assert client.get("/board", params={"date": bad}).status_code == 404


def test_board_renders_one_button_per_tile():
    cfg = board_cfg("2026-09-01")
    html = client.get("/board", params={"date": "2026-09-01"}).text
    assert html.count('class="tile"') == cfg["rows"] * cfg["cols"] - 1


def test_day_urls():
    assert client.get("/").status_code == 200
    assert client.get("/2026-09-17").status_code == 200
    assert client.get("/calendar").status_code == 200
    for bad in ["/2026-08-31", "/2099-01-01", "/2026-13-01", "/20260917", "/nope"]:
        assert client.get(bad).status_code == 404


def test_language_choice():
    c = TestClient(app)
    pt = c.get("/", headers={"Accept-Language": "pt-BR"})
    assert '<html lang="pt-BR">' in pt.text and "Como jogar" in pt.text
    assert "Cookie" in pt.headers["vary"]
    # The board follows the language: Portuguese strings and the Portuguese word.
    board = c.get("/board", params={"date": "2026-09-03"}, headers={"Accept-Language": "pt-BR"})
    assert "Resolvido" in board.text
    pt_word = board_cfg("2026-09-03", **{"Accept-Language": "pt-BR"})["word"]
    assert pt_word == plain(puzzle.word_for(date(2026, 9, 3), "pt-BR"))
    # A picked language (cookie) beats the browser's...
    c.cookies.set(i18n.COOKIE, "en")
    assert "How to play" in c.get("/", headers={"Accept-Language": "pt-BR"}).text
    # ...and a shared link's ?lang= beats both.
    assert "Como jogar" in c.get("/2026-09-17", params={"lang": "pt-BR"}).text
    c.cookies.set(i18n.COOKIE, "xx")  # unknown values fall back to detection
    assert "Como jogar" in c.get("/", headers={"Accept-Language": "pt-BR"}).text


def test_accept_language_parsing():
    assert i18n.from_accept_language("pt-PT,pt;q=0.9,en;q=0.8") == "pt-BR"
    assert i18n.from_accept_language("de, en;q=0.5, pt;q=0.4") == "en"
    assert i18n.from_accept_language("") == "en"


def test_pwa_files():
    manifest = client.get("/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    for icon in manifest.json()["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert client.get("/sw.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/static/icons/apple-touch-icon.png").status_code == 200
