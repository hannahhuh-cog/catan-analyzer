"""Demo profile: simulated games for a player with a known style, fully analyzed."""

from __future__ import annotations

import random
from collections import defaultdict
from functools import lru_cache

from .catan.analyze import STRATEGY_LABELS, analyze_game
from .catan.sim import COLOR_NAMES, PlayerSpec, simulate
from .colonist import ORDINAL, aggregate


def _pct100(x: float) -> int:
    """Percent rounded half-up, matching the frontend's Math.round."""
    return int(x * 100 + 0.5)


DEMO_USER = "DemoPlayer"
OPPONENTS = ["Wheatley", "OreGanizer", "BrickHouse", "SheepThrills", "LongRoadLarry", "KnightRider", "PortAuthority"]
# The demo player is strong at city rush and weak at expansion, so the
# strengths/weaknesses view has a real signal to find.
DEMO_SKILL = {"city_rush": 0.85, "balanced": 0.65, "dev_cards": 0.6, "expansion": 0.35}
N_GAMES = 40


def _game_summary(gid: str, game: dict, analysis: dict, start_ms: int) -> dict:
    focus = analysis["focus"]
    me = next(p for p in analysis["players"] if p["color"] == focus)
    winner = next(p for p in analysis["players"] if p["color"] == analysis["winner"])
    ranks = sorted(analysis["players"], key=lambda p: (p["color"] != analysis["winner"], -p["final_vp"]))
    return {
        "id": gid,
        "start_ms": start_ms,
        "duration_min": round(analysis["turns"] * 0.45, 1),
        "turns": analysis["turns"],
        "players": len(game["players"]),
        "won": analysis["won"],
        "rank": ranks.index(me) + 1,
        "points": me["final_vp"],
        "vp_to_win": game["vp_to_win"],
        "winner_points": winner["final_vp"],
        "play_order": analysis["seat"],
        "finished": True,
        "quit": False,
        "bots": 0,
        "map": None,
        "mode": None,
        "dice": None,
        "ranked": False,
        "has_replay": True,
        "analyzed": True,
        "verdict": analysis["verdict"],
        "luck_index": analysis["luck_index"],
        "decision_score": analysis["decision_score"],
        "decision_edge": analysis["decision_edge"],
        "strategy": analysis["strategy"],
        "opponents": [
            {"name": p["name"], "rank": ranks.index(p) + 1, "points": p["final_vp"], "human": True}
            for p in analysis["players"]
            if p["color"] != focus
        ],
    }


@lru_cache(maxsize=1)
def demo_dataset() -> dict:
    rng = random.Random(2026)
    games: dict[str, dict] = {}
    analyses: dict[str, dict] = {}
    summaries = []
    start = 1_790_000_000_000
    for i in range(N_GAMES):
        n = rng.choice([3, 4, 4, 4])
        style = rng.choices(list(DEMO_SKILL), weights=[3, 3, 2, 2])[0]
        specs = [PlayerSpec(DEMO_USER, style, DEMO_SKILL[style])]
        for name in rng.sample(OPPONENTS, n - 1):
            specs.append(PlayerSpec(name, rng.choice(list(DEMO_SKILL)), round(rng.uniform(0.35, 0.8), 2)))
        seat = rng.randrange(n)
        specs.insert(seat, specs.pop(0))
        game = simulate(specs, seed=1000 + i)
        focus = next(p["color"] for p in game["players"] if p["name"] == DEMO_USER)
        gid = f"demo-{i + 1:03d}"
        analysis = analyze_game(game, focus)
        start += rng.randint(3, 30) * 3_600_000
        games[gid], analyses[gid] = game, analysis
        summaries.append(_game_summary(gid, game, analysis, start))
    summaries.sort(key=lambda g: -g["start_ms"])
    stats = aggregate(summaries)
    stats["deep"] = deep_stats(summaries)
    return {"username": DEMO_USER, "source": "demo", "games": summaries, "stats": stats, "_analyses": analyses}


def deep_stats(games: list[dict]) -> dict:
    """Aggregates that need full replays: luck vs. decisions and strategy."""
    analyzed = [g for g in games if g.get("analyzed")]
    if not analyzed:
        return {}

    def rate(gs: list[dict]) -> dict:
        return {"games": len(gs), "wins": sum(g["won"] for g in gs), "win_rate": round(sum(g["won"] for g in gs) / len(gs), 3) if gs else 0}

    by_strategy = defaultdict(list)
    for g in analyzed:
        by_strategy[g["strategy"]].append(g)
    strategies = [{"key": k, "label": STRATEGY_LABELS[k], **rate(v)} for k, v in by_strategy.items()]
    strategies.sort(key=lambda r: (-r["win_rate"], -r["games"]))

    verdicts: dict[str, int] = defaultdict(int)
    for g in analyzed:
        verdicts[g["verdict"]] += 1
    losses = [g for g in analyzed if not g["won"]]
    wins = [g for g in analyzed if g["won"]]
    rng_losses = [g for g in losses if g["luck_index"] <= -1.0 and g["decision_edge"] >= 0]
    lucky_wins = [g for g in wins if g["luck_index"] >= 0.5 and g["decision_edge"] < 0]
    lucky = [g for g in analyzed if g["luck_index"] >= 0.5]
    unlucky = [g for g in analyzed if g["luck_index"] <= -0.5]
    good_dec = [g for g in analyzed if g["decision_edge"] >= 5]
    bad_dec = [g for g in analyzed if g["decision_edge"] <= -5]

    insights = []
    overall = rate(analyzed)["win_rate"]
    sized = [r for r in strategies if r["games"] >= 5]
    if len(sized) >= 2 and sized[0]["win_rate"] > sized[-1]["win_rate"]:
        top = [r for r in sized if r["win_rate"] == sized[0]["win_rate"]]
        bottom = [r for r in sized if r["win_rate"] == sized[-1]["win_rate"]]
        for kind, rows, word in (("strength", top, "best"), ("weakness", bottom, "weakest")):
            insights.append(
                {
                    "kind": kind,
                    "title": " / ".join(r["label"] for r in rows) + f": {_pct100(rows[0]['win_rate'])}% wins",
                    "detail": f"Your {word} style: "
                    + ", ".join(f"{r['wins']}/{r['games']}" for r in rows)
                    + f" games vs {_pct100(overall)}% overall. Strategy is inferred from what you built.",
                    "evidence": rows[0],
                }
            )
    if losses:
        insights.append(
            {
                "kind": "luck",
                "title": f"{len(rng_losses)} of {len(losses)} losses were mainly RNG",
                "detail": "Losses where you out-decided the table but the dice/robber ran at least 1 SD against you.",
                "evidence": {"losses": len(losses), "rng": len(rng_losses)},
            }
        )
    if wins:
        insights.append(
            {
                "kind": "luck",
                "title": f"{len(lucky_wins)} of {len(wins)} wins were mainly luck",
                "detail": "Wins where the dice ran hot but your decision score trailed the table.",
                "evidence": {"wins": len(wins), "lucky": len(lucky_wins)},
            }
        )
    if good_dec and bad_dec:
        g, b = rate(good_dec), rate(bad_dec)
        insights.append(
            {
                "kind": "info",
                "title": f"Out-deciding the table: {_pct100(g['win_rate'])}% wins vs {_pct100(b['win_rate'])}%",
                "detail": "Win rate when your decision score beat opponents' by 5+ points vs trailed by 5+.",
                "evidence": {"ahead": g, "behind": b},
            }
        )

    def mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    return {
        "games": len(analyzed),
        "verdicts": dict(verdicts),
        "strategies": strategies,
        "luck_split": {
            "lucky": rate(lucky),
            "neutral": rate([g for g in analyzed if g not in lucky and g not in unlucky]),
            "unlucky": rate(unlucky),
        },
        "avg_luck": {"wins": mean([g["luck_index"] for g in wins]), "losses": mean([g["luck_index"] for g in losses])},
        "avg_decision": {"wins": mean([g["decision_score"] for g in wins]), "losses": mean([g["decision_score"] for g in losses])},
        "scatter": [
            {
                "id": g["id"],
                "luck": g["luck_index"],
                "decision": g["decision_edge"],
                "won": g["won"],
                "seat": ORDINAL.get(g["play_order"], "?"),
            }
            for g in analyzed
        ],
        "insights": insights,
    }


def demo_profile() -> dict:
    d = demo_dataset()
    return {k: v for k, v in d.items() if not k.startswith("_")}


def demo_game(gid: str) -> dict | None:
    d = demo_dataset()
    a = d["_analyses"].get(gid)
    if a is None:
        return None
    summary = next(g for g in d["games"] if g["id"] == gid)
    colors = {p["color"]: COLOR_NAMES.get(p["color"], str(p["color"])) for p in a["players"]}
    return {"id": gid, "summary": summary, "color_names": colors, **a}
