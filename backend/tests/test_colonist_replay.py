"""Round-trip simulated games through a Colonist-shaped replay and back."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.catan.analyze import analyze_game
from app.catan.board import ENUM_BY_RESOURCE, Board, parse_id
from app.catan.colonist_replay import COLONIST_COLORS, ReplayError, replay_to_game
from app.catan.sim import PlayerSpec, simulate
from app.main import app

SPECS = [
    PlayerSpec("hannah", "city_rush", 0.8),
    PlayerSpec("B", "expansion", 0.5),
    PlayerSpec("C", "balanced", 0.3),
    PlayerSpec("D", "dev_cards", 0.6),
]
TO_COLONIST = {slot: c for c, (_, slot) in COLONIST_COLORS.items()}
TILE_ENUM = {"desert": 0, **ENUM_BY_RESOURCE}
PORT_ENUM = {"3:1": 1, "lumber": 2, "brick": 3, "wool": 4, "grain": 5, "ore": 6}
DEV_ENUM = {"knight": 11, "victory_point": 12, "monopoly": 13, "road_building": 14, "year_of_plenty": 15}
PIECE_ENUM = {"road": 0, "settlement": 2, "city": 3}


def enums(cards: dict) -> list[int]:
    return [ENUM_BY_RESOURCE[r] for r, n in cards.items() for _ in range(n)]


def to_colonist(game: dict, perspective: int) -> dict:
    """Encode a simulated game the way Colonist's replay API ships one."""
    board = Board.from_dict(game["board"])
    hexes = sorted(board.tiles)
    corners = sorted(board.corners)
    edges = sorted(board.edges)
    hex_idx = {h: i for i, h in enumerate(hexes)}
    corner_idx = {c: i for i, c in enumerate(corners)}
    edge_idx = {e: i for i, e in enumerate(edges)}
    col = TO_COLONIST.__getitem__
    initial = {
        "mapState": {
            "tileHexStates": {
                str(i): {"x": h[0], "y": h[1], "type": TILE_ENUM[board.tiles[h].resource], "diceNumber": board.tiles[h].number or 0}
                for i, h in enumerate(hexes)
            },
            "tileCornerStates": {str(i): {"x": c[0], "y": c[1], "z": c[2]} for i, c in enumerate(corners)},
            "tileEdgeStates": {str(i): {"x": e[0], "y": e[1], "z": e[2]} for i, e in enumerate(edges)},
            "portEdgeStates": {
                str(i): {"x": e[0], "y": e[1], "z": e[2], "type": PORT_ENUM[k]} for i, (e, k) in enumerate(board.ports.items())
            },
        },
        "mechanicRobberState": {"locationTileIndex": hex_idx[board.robber]},
    }
    out = []
    for ev in game["events"]:
        sc: dict = {}
        p = col(ev["player"]) if "player" in ev else None
        logs = []
        t = ev["t"]
        if t == "place":
            loc = parse_id(ev["loc"])
            if ev["piece"] == "road":
                sc["mapState"] = {"tileEdgeStates": {str(edge_idx[loc]): {"owner": p, "type": 1}}}
            else:
                bt = 1 if ev["piece"] == "settlement" else 2
                sc["mapState"] = {"tileCornerStates": {str(corner_idx[loc]): {"owner": p, "buildingType": bt}}}
            logs.append({"type": 4 if ev.get("setup") else 5, "playerColor": p, "pieceEnum": PIECE_ENUM[ev["piece"]]})
        elif t == "roll":
            sc["currentState"] = {"currentTurnPlayerColor": p}
            logs.append({"type": 10, "playerColor": p, "firstDice": ev["dice"][0], "secondDice": ev["dice"][1]})
        elif t == "gain":
            if ev["source"] == "year_of_plenty":
                logs.append({"type": 21, "playerColor": p, "cardEnums": enums(ev["cards"])})
            elif ev["source"] == "monopoly":
                ((r, n),) = ev["cards"].items()
                logs.append({"type": 86, "playerColor": p, "cardEnum": ENUM_BY_RESOURCE[r], "amountStolen": n})
            else:
                dist = 0 if ev["source"] == "setup" else 1
                logs.append({"type": 47, "playerColor": p, "cardsToBroadcast": enums(ev["cards"]), "distributionType": dist})
        elif t == "discard":
            logs.append({"type": 55, "playerColor": p, "cardEnums": enums(ev["cards"])})
        elif t == "robber":
            sc["mechanicRobberState"] = {"locationTileIndex": hex_idx[parse_id(ev["hex"])]}
            logs.append({"type": 11, "playerColor": p})
        elif t == "steal":
            thief, victim = col(ev["thief"]), col(ev["victim"])
            card = [ENUM_BY_RESOURCE[ev["card"]]] if ev.get("card") else []
            out.append(
                {"stateChange": {"gameLogState": {"0": {"text": {"type": 14, "playerColor": victim, "cardEnums": card}, "from": thief}}}}
            )
            logs.append({"type": 15, "playerColor": thief, "cardEnums": card, "_from": thief, "_to": [victim]})
        elif t == "play_dev":
            logs.append({"type": 20, "playerColor": p, "cardEnum": DEV_ENUM[ev["card"]]})
        elif t == "buy_dev":
            logs.append({"type": 1, "playerColor": p})
        elif t == "trade_bank":
            logs.append({"type": 116, "playerColor": p, "givenCardEnums": enums(ev["give"]), "receivedCardEnums": enums(ev["get"])})
        elif t == "award" and ev["award"] == "longest_road":
            logs.append({"type": 68, "playerColor": p, "playerColorNew": p})
        elif t == "end_turn":
            order = game["play_order"]
            sc["currentState"] = {"currentTurnPlayerColor": col(order[(order.index(ev["player"]) + 1) % len(order)])}
        elif t == "game_end":
            continue
        if logs:
            sc["gameLogState"] = {}
            for i, text in enumerate(logs):
                entry: dict = {"text": text}
                if "_from" in text:
                    entry["from"], entry["specificRecipients"] = text.pop("_from"), text.pop("_to")
                sc["gameLogState"][str(i)] = entry
        if sc:
            out.append({"stateChange": sc})
    winner = col(game["winner"])
    return {
        "data": {
            "databaseGameId": "123456789",
            "playerPerspective": col(perspective),
            "playOrder": [col(c) for c in game["play_order"]],
            "playerUserStates": [{"username": p["name"], "selectedColor": col(p["color"])} for p in game["players"]],
            "gameSettings": {"victoryPointsToWin": game["vp_to_win"]},
            "eventHistory": {
                "initialState": initial,
                "events": out,
                "endGameState": {
                    "players": {
                        str(col(p["color"])): {"rank": 1 if col(p["color"]) == winner else 2, "victoryPoints": game["final_vp"][p["color"]]}
                        for p in game["players"]
                    }
                },
            },
        }
    }


@pytest.fixture(scope="module")
def games():
    return [simulate(SPECS, seed) for seed in range(6)]


def test_round_trip_matches_simulated_analysis(games):
    for g in games:
        imported = replay_to_game(to_colonist(g, 1))
        assert imported["focus"] == 1
        assert imported["winner"] == g["winner"]
        assert imported["board"] == g["board"]
        want, got = analyze_game(g, 1), analyze_game(imported, 1)
        assert {p["color"]: p["final_vp"] for p in got["players"]} == g["final_vp"]
        assert got["dice_histogram"] == want["dice_histogram"]
        assert got["turns"] == want["turns"]
        assert got["stats"] == want["stats"]
        assert Counter(e["t"] for e in imported["events"]) == Counter(e["t"] for e in g["events"] if e["t"] not in ("lose", "end_turn"))
        # Monopoly victims' losses aren't in Colonist's log, so only hand-size-driven win odds may drift.
        vp_cols = [[(k, v) for k, v in row.items() if not k.startswith("wp_")] for row in got["timeline"]]
        assert vp_cols == [[(k, v) for k, v in row.items() if not k.startswith("wp_")] for row in want["timeline"]]


def test_player_names_and_colors(games):
    imported = replay_to_game(to_colonist(games[0], 2))
    assert imported["focus"] == 2
    assert imported["color_names"]["2"] == "Red"
    assert {p["name"] for p in imported["players"]} == {s.name for s in SPECS}


def test_rejects_non_replays():
    with pytest.raises(ReplayError):
        replay_to_game({"hello": "world"})
    with pytest.raises(ReplayError):
        replay_to_game({"data": {"eventHistory": {"initialState": {}, "events": []}}})


def test_analyze_endpoint(games):
    client = TestClient(app)
    r = client.post("/api/replay/analyze", json=to_colonist(games[1], 1))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "colonist-123456789"
    assert body["focus"] == 1 and body["summary"]["analyzed"]
    assert len(body["timeline"]) > 10
    r = client.post("/api/replay/analyze?focus=3", json=to_colonist(games[1], 1))
    assert r.json()["focus"] == 3
    r = client.post("/api/replay/analyze?focus=9", json=to_colonist(games[1], 1))
    assert r.status_code == 422
    r = client.post("/api/replay/analyze", json={"nope": 1})
    assert r.status_code == 422
