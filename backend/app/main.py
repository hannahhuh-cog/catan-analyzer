from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .colonist import ColonistError, build_profile, fetch_history, valid_username
from .demo import demo_game, demo_profile

app = FastAPI(title="Catan Analyzer")
_cache: dict[str, tuple[float, dict]] = {}
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
    try:
        data = await fetch_history(username)
    except ColonistError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    result = build_profile(username, data)
    if not result["games"]:
        raise HTTPException(404, f"'{username}' has no recorded games on Colonist.io.")
    _cache[key] = (time.time(), result)
    return result


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
