import pytest

from app.catan.analyze import _verdict, analyze_game
from app.catan.sim import PlayerSpec, simulate

SPECS = [
    PlayerSpec("You", "city_rush", 0.8),
    PlayerSpec("B", "expansion", 0.5),
    PlayerSpec("C", "balanced", 0.3),
    PlayerSpec("D", "dev_cards", 0.6),
]


@pytest.fixture(scope="module")
def games():
    return [simulate(SPECS, seed) for seed in range(8)]


def test_simulated_games_finish(games):
    for g in games:
        assert g["final_vp"][g["winner"]] >= g["vp_to_win"]
        assert g["events"][-1]["t"] == "game_end"


def test_analysis_replays_final_score(games):
    for g in games:
        a = analyze_game(g, 1)
        assert {p["color"]: p["final_vp"] for p in a["players"]} == g["final_vp"]
        assert a["won"] == (g["winner"] == 1)


def test_analysis_shape(games):
    a = analyze_game(games[0], 1)
    assert 0 <= a["decision_score"] <= 100
    assert a["timeline"][0]["turn"] == 0
    turns = [r["turn"] for r in a["timeline"]]
    assert turns == sorted(turns)
    for row in a["timeline"]:
        assert abs(sum(row[f"wp_{c}"] for c in (1, 2, 3, 5)) - 1) < 0.01
    assert sum(h["count"] for h in a["dice_histogram"]) == sum(1 for e in games[0]["events"] if e["t"] == "roll")
    assert all(m["player"] == 1 for m in a["critical"])
    assert len(a["critical"]) <= 9


def test_swing_attribution_adds_up(games):
    for g in games:
        a = analyze_game(g, 1)
        imp = a["impact"]
        assert abs(imp["start"] + imp["decision"] + imp["luck"] + imp["opponent"] - imp["end"]) < 0.01
        assert imp["end"] == float(a["won"])
        wp = {r["turn"]: r["wp_1"] for r in a["timeline"]}
        for s in a["swings"]:
            assert s["kind"] in ("decision", "luck", "opponent")
            assert abs(sum(s["parts"].values()) - s["wp_delta"]) < 0.01
            assert abs(wp[s["turn"]] - s["wp_after"]) < 0.01
            assert abs(s["wp_delta"]) >= 0.12
        assert not any(k.startswith("_") for m in a["moments"] for k in m)


def test_expected_income_tracks_actual(games):
    # Over many games, dice luck should average out near zero.
    zs = [analyze_game(g, c)["luck"]["dice_z"] for g in games for c in (1, 2, 3, 5)]
    assert abs(sum(zs) / len(zs)) < 0.75


def test_verdicts():
    assert _verdict(False, -1.5, 10)[0] == "Lost to RNG"
    assert _verdict(False, 0.8, -5)[0] == "Outplayed"
    assert _verdict(False, 0.8, 10)[0] == "Close call"
    assert _verdict(False, -0.7, 10)[0] == "Unlucky loss"
    assert _verdict(False, -0.7, -10)[0] == "Unlucky and outplayed"
    assert _verdict(True, 1.2, -10)[0] == "Lucky win"
    assert _verdict(True, 0.0, 10)[0] == "Earned win"
