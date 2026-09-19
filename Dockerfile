# syntax=docker/dockerfile:1

# ---- build: install the locked production dependencies into a virtualenv ----
FROM python:3.12-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

# Compile bytecode now, since the runtime filesystem is read-only; copy instead of
# hardlinking out of the cache mount; never download a different Python.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# ---- runtime: the same slim Python, just the venv and the app, no uv, no build tools ----
FROM python:3.12-slim-bookworm

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin slid \
    && mkdir /data && chown slid:slid /data

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# Owned by root and only readable by the app user, so the running process can't modify its own code.
COPY slid ./slid
RUN python -m compileall -q slid

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SLID_DB=/data/slid.db

# The only writable place: every day's puzzle is stored here the first time it's served.
VOLUME /data

USER slid
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/manifest.webmanifest', timeout=2)"]

# --proxy-headers trusts X-Forwarded-* only from FORWARDED_ALLOW_IPS (set it to your reverse proxy).
CMD ["uvicorn", "slid.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
