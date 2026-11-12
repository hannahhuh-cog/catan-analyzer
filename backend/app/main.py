from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .colonist import ColonistError, build_profile, fetch_history, valid_username
from .demo import demo_game, demo_profile

app = FastAPI(title="Catan Analyzer")
_cache: dict[str, tuple[float, dict]] = {}
_inflight: dict[str, asyncio.Task] = {}
CACHE_TTL = 300


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/demo")
def demo() -> dict:
    return demo_profile()


@app.get("/api/demo/games/{game_id}")
def demo_game_detail(game_id: str) -> dict:
    g = demo_game(game_id)
    if g is None:
        raise HTTPException(404, "Game not found")
    return g


@app.get("/api/profile/{username}")
async def profile(username: str) -> dict:
    username = username.strip()
    if not valid_username(username):
        raise HTTPException(400, "That doesn't look like a Colonist.io username.")
    key = username.lower()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    # Repeated quick searches for the same name share one Colonist.io request.
    task = _inflight.get(key)
    if task is None:
        task = asyncio.ensure_future(fetch_history(username))
        _inflight[key] = task
        task.add_done_callback(lambda _: _inflight.pop(key, None))
    try:
        data = await asyncio.shield(task)
    except ColonistError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    result = build_profile(username, data)
    if not result["games"]:
        raise HTTPException(404, f"{result['username']} has a Colonist.io profile but no games in its public history yet.")
    _cache[key] = (time.time(), result)
    return result


@app.get("/api/{path:path}", include_in_schema=False)
def api_not_found(path: str) -> None:
    raise HTTPException(404, "Not found. Search for a Colonist.io username from the top bar.")


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
