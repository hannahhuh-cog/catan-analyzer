import httpx
import pytest

from app.colonist import ColonistError, aggregate, build_profile, fetch_history, valid_username


def _player(uid, name, rank, points, order, human=True):
    return {
        "userId": uid,
        "username": name,
        "rank": rank,
        "points": points,
        "finished": True,
        "quitWithPenalty": False,
        "isHuman": human,
        "playerColor": 1,
        "playOrder": order,
    }


def _game(i, my_rank, my_order, n=4):
    players = [_player("1", "Me", my_rank, 10 if my_rank == 1 else 7, my_order)]
    others = [r for r in range(1, n + 1) if r != my_rank]
    orders = [o for o in range(1, n + 1) if o != my_order]
    for k, (r, o) in enumerate(zip(others, orders)):
        players.append(_player(str(10 + k), f"Opp{k}", r, 10 if r == 1 else 6, o, human=k != 2))
    return {
        "id": str(i),
        "setting": {"victoryPointsToWin": 10, "mapSetting": 1, "modeSetting": 1, "diceSetting": 0},
        "finished": True,
        "turnCount": 60,
        "startTime": str(1_700_000_000_000 + i * 1000),
        "duration": "1800000",
        "players": players,
        "userStats": [],
        "hasReplay": True,
    }


def test_username_validation():
    assert valid_username("Saeid#7757")
    assert valid_username("john_doe.1")
    assert not valid_username("")
    assert not valid_username("a/../b")
    assert not valid_username("x" * 41)


def test_build_profile_and_play_order_insight():
    # Wins every game when placing first, never when placing fourth.
    raw = [_game(i, 1 if i % 2 == 0 else 3, 1 if i % 2 == 0 else 4) for i in range(20)]
    p = build_profile("me", {"profileUserId": "1", "gameDatas": raw})
    assert len(p["games"]) == 20
    s = p["stats"]
    assert s["overall"]["wins"] == 10
    po = {r["key"]: r for r in s["breakdowns"]["play_order"]}
    assert po[1]["win_rate"] == 1.0 and po[4]["win_rate"] == 0.0
    kinds = {(i["kind"], i["evidence"].get("dimension"), i["evidence"].get("key")) for i in s["insights"]}
    assert ("strength", "play_order", 1) in kinds
    assert ("weakness", "play_order", 4) in kinds


def test_aggregate_empty():
    assert aggregate([])["insights"] == []


@pytest.mark.anyio
async def test_fetch_history_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if "missing" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json={"profileUserId": "1", "gameDatas": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await fetch_history("ok", client))["gameDatas"] == []
        with pytest.raises(ColonistError) as e:
            await fetch_history("missing", client)
        assert e.value.status == 404
        with pytest.raises(ColonistError) as e:
            await fetch_history("bad/name", client)
        assert e.value.status == 400


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _raw(players, vp=10, finished=True, i=0):
    return {
        "id": str(i),
        "setting": {"victoryPointsToWin": vp, "mapSetting": 0, "modeSetting": 0, "diceSetting": 0, "eloType": 0},
        "finished": finished,
        "turnCount": 60,
        "startTime": str(1_700_000_000_000 + i * 1000),
        "duration": "1800000",
        "players": players,
    }


def test_forfeit_counts_as_loss_and_abandoned_game_is_dropped():
    me_left = {**_player("1", "Me", 2, 4, 1), "finished": False}
    forfeit = _raw([me_left, _player("2", "Opp", 1, 7, 2)], vp=15, i=1)
    abandoned = _raw([_player("1", "Me", 1, 3, 1), _player("2", "Opp", 2, 2, 2)], vp=15, finished=False, i=2)
    won = _raw([_player("1", "Me", 1, 15, 1), _player("2", "Opp", 2, 10, 2)], vp=15, i=3)
    s = build_profile("me", {"profileUserId": "1", "gameDatas": [forfeit, abandoned, won]})["stats"]["overall"]
    assert (s["games"], s["wins"], s["left"]) == (2, 1, 1)


def test_bot_games_are_left_out_of_the_level():
    raw = []
    for i in range(30):
        bots = i < 20
        me_rank = 1 if bots else (1 if i % 4 == 0 else 3)
        ps = [_player("1", "Me", me_rank, 10 if me_rank == 1 else 7, 1)]
        for k, r in enumerate(r for r in range(1, 5) if r != me_rank):
            ps.append(_player(str(10 + k), "Bot" if bots else f"Opp{k}", r, 10 if r == 1 else 6, k + 2, human=not bots))
        raw.append(_raw(ps, i=i))
    s = build_profile("me", {"profileUserId": "1", "gameDatas": raw})["stats"]
    assert s["overall"]["games"] == 10 and s["overall"]["bot_games_excluded"] == 20
    assert s["insights"][0]["kind"] != "strength"
    assert any("games with bots" in i["title"] for i in s["insights"])


def test_close_losses_are_judged_against_the_table():
    # Every loss is a 4th place 2 VP behind, but so is every other loser: nothing unusual.
    raw = []
    for i in range(20):
        me_rank = 1 if i % 4 == 0 else 2
        ps = [_player("1", "Me", me_rank, 10 if me_rank == 1 else 8, 1)]
        for k, r in enumerate(r for r in range(1, 5) if r != me_rank):
            ps.append(_player(str(10 + k), f"Opp{k}", r, 10 if r == 1 else 8, k + 2))
        raw.append(_raw(ps, i=i))
    ins = build_profile("me", {"profileUserId": "1", "gameDatas": raw})["stats"]["insights"]
    close = next(i for i in ins if "VP of the winner" in i["title"])
    assert close["kind"] == "info"
