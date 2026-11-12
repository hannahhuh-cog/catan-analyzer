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
