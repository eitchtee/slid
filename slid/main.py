import asyncio
import datetime as dt
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from . import i18n, store
from .puzzle import LAUNCH, number
from .store import puzzle_for

HERE = Path(__file__).parent
log = logging.getLogger("uvicorn.error")  # so it shows up alongside uvicorn's own output

# Players pick "today" in their own time zone. The first zone to reach a new date is UTC+14,
# where midnight is 10:00 UTC the day before, so tomorrow's puzzles are stored an hour ahead
# of that and nobody waits on generation. If this ever fails, the first request for a day
# generates it instead (store.puzzle_for).
PREGENERATE_AT = dt.time(9, 0, tzinfo=dt.UTC)


def next_pregeneration(now: dt.datetime) -> dt.datetime:
    run = dt.datetime.combine(now.date(), PREGENERATE_AT)
    return run if run > now else run + dt.timedelta(days=1)


def pregenerate(now: dt.datetime) -> None:
    """Stores every day from launch through tomorrow (UTC), in every language."""
    through = now.date() + dt.timedelta(days=1)
    written = store.ensure_through(through, tuple(i18n.LANGS))
    log.info("Puzzles stored through %s (%d new)", through.isoformat(), written)


async def pregenerate_daily() -> None:
    # Once at startup, which also catches up on anything missed while the server was down, then daily.
    while True:
        try:
            await asyncio.to_thread(pregenerate, dt.datetime.now(dt.UTC))
        except Exception:
            log.exception("Storing upcoming puzzles failed; requests will generate them instead")
        now = dt.datetime.now(dt.UTC)
        await asyncio.sleep((next_pregeneration(now) - now).total_seconds())


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(pregenerate_daily())
    yield
    task.cancel()


app = FastAPI(title="Slid", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
# A string as a JS literal inside a double-quoted HTML attribute, e.g. :aria-label="on ? {{ t.mute|js }} : ...".
templates.env.filters["js"] = lambda value: Markup(escape(json.dumps(value)))


def render(request: Request, name: str, context: dict):
    lang = i18n.pick(request)
    context = {"lang": lang, "langs": i18n.LANGS, "t": i18n.STRINGS[lang], **context}
    response = templates.TemplateResponse(request, name, context)
    response.headers["Vary"] = "Cookie, Accept-Language"
    return response


def puzzle_date(value: str) -> dt.date:
    """Parse a YYYY-MM-DD day, 404ing on anything that has no puzzle."""
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(404, "Not a day") from None
    if value != day.isoformat():  # fromisoformat also takes "20260917"; keep one URL per day
        raise HTTPException(404, "Not a day")
    # The client picks "today" in its own timezone; allow one day ahead for zones east of UTC.
    if not LAUNCH <= day <= dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1):
        raise HTTPException(404, "No puzzle for that day")
    return day


def page(request: Request):
    # The client reads the day from the URL path and loads /board itself.
    return render(request, "index.html", {"launch": LAUNCH.isoformat()})


@app.get("/")
def index(request: Request):
    return page(request)


@app.get("/calendar")
def calendar(request: Request):
    return page(request)


# These live at the root: a service worker only controls pages at or below its own path.
@app.get("/sw.js")
def service_worker():
    return FileResponse(HERE / "static/sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(HERE / "static/manifest.webmanifest", media_type="application/manifest+json")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(HERE / "static/favicon.ico")


@app.get("/board")
def board(request: Request, date: str):
    day = puzzle_date(date)
    lang = i18n.pick(request)
    p = puzzle_for(day, lang)
    cfg = {
        "date": day.isoformat(),
        "lang": lang,
        "number": number(day),
        "word": p.word,  # tile spelling; the page shows p.shown
        "rows": p.rows,
        "cols": p.cols,
        "start": p.start,
        "challenge": p.challenge,
    }
    tiles = [(cell, letter) for cell, letter in enumerate(p.start) if letter != "."]
    return render(request, "board.html", {"p": p, "cfg": cfg, "tiles": tiles})


# Declared last so it doesn't shadow /board or /calendar.
@app.get("/{day}")
def day_page(request: Request, day: str):
    puzzle_date(day)
    return page(request)
