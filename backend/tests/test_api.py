from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"ok": True}


def test_demo_profile_and_game():
    p = client.get("/api/demo").json()
    assert p["source"] == "demo" and len(p["games"]) == 40
    assert p["stats"]["deep"]["insights"]
    gid = p["games"][0]["id"]
    g = client.get(f"/api/demo/games/{gid}").json()
    assert g["id"] == gid and g["timeline"] and "verdict" in g
    assert client.get("/api/demo/games/nope").status_code == 404


def test_profile_rejects_bad_username():
    assert client.get("/api/profile/%3Cscript%3E").status_code == 400


def test_unknown_api_route_is_json_404():
    r = client.get("/api/profile/a/b")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_profile_coalesces_concurrent_lookups(monkeypatch):
    import asyncio

    from app import main

    calls = []

    async def fake_fetch(username):
        calls.append(username)
        await asyncio.sleep(0.05)
        return {"profileUserId": "1", "gameDatas": []}

    monkeypatch.setattr(main, "fetch_history", fake_fetch)

    async def run():
        return await asyncio.gather(*(main.profile("Dup") for _ in range(3)), return_exceptions=True)

    results = asyncio.run(run())
    assert len(calls) == 1
    assert all(getattr(r, "status_code", None) == 404 for r in results)
