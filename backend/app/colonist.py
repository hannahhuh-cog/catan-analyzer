"""Colonist.io public profile history: fetching, normalizing and aggregating."""

from __future__ import annotations

import math
import os
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import quote

import httpx

USERNAME_RE = re.compile(r"^[\w#.\- ]{1,40}$")
HISTORY_URL = os.environ.get("COLONIST_HISTORY_URL", "https://colonist.io/api/profile/{username}/history")
MIN_SAMPLE = 5


class ColonistError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def valid_username(username: str) -> bool:
    username = username.strip()
    return bool(USERNAME_RE.match(username)) and any(c.isalnum() for c in username)


async def fetch_history(username: str, client: httpx.AsyncClient | None = None) -> dict:
    username = username.strip()
    if not valid_username(username):
        raise ColonistError("That doesn't look like a Colonist.io username.", 400)
    url = HISTORY_URL.format(username=quote(username, safe=""))
    owns = client is None
    client = client or httpx.AsyncClient(timeout=15, headers={"User-Agent": "catan-analyzer/0.1"})
    try:
        resp = await client.get(url)
    except httpx.TimeoutException as exc:
        raise ColonistError("Colonist.io took too long to respond. Try again in a minute.", 504) from exc
    except httpx.HTTPError as exc:
        raise ColonistError("Couldn't reach Colonist.io right now. Try again in a minute.") from exc
    finally:
        if owns:
            await client.aclose()
    not_found = ColonistError(f"No Colonist.io player named '{username}'. Check the spelling, including any spaces or symbols.", 404)
    if resp.status_code in (400, 404):
        raise not_found
    if resp.status_code == 429:
        raise ColonistError("Colonist.io is limiting lookups right now. Wait a minute and try again.", 503)
    if resp.status_code != 200:
        raise ColonistError(f"Colonist.io is having problems (HTTP {resp.status_code}). Try again later.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ColonistError("Colonist.io sent an unexpected response. Try again later.") from exc
    if isinstance(data, dict) and "error" in data:
        raise not_found
    if not isinstance(data, dict) or "gameDatas" not in data:
        raise ColonistError("Colonist.io sent an unexpected response. Try again later.")
    return data


def normalize_game(raw: dict, username: str, user_id: str | None) -> dict | None:
    players = raw.get("players") or []
    me = next((p for p in players if user_id and str(p.get("userId")) == str(user_id)), None)
    if me is None:
        me = next((p for p in players if str(p.get("username", "")).lower() == username.lower()), None)
    if me is None:
        return None
    setting = raw.get("setting") or {}
    n = len(players)
    opponents = [p for p in players if p is not me]
    vp_to_win = setting.get("victoryPointsToWin") or 10
    try:
        start_ms = int(raw.get("startTime") or 0)
        duration_ms = int(raw.get("duration") or 0)
    except ValueError:
        start_ms = duration_ms = 0
    winner = min(players, key=lambda p: p.get("rank") or 99)
    return {
        "id": str(raw.get("id")),
        "start_ms": start_ms,
        "duration_min": round(duration_ms / 60000, 1),
        "turns": raw.get("turnCount") or 0,
        "players": n,
        "won": me.get("rank") == 1,
        "rank": me.get("rank"),
        "points": me.get("points") or 0,
        "vp_to_win": vp_to_win,
        "winner_points": winner.get("points") or 0,
        "play_order": me.get("playOrder"),
        "finished": bool(me.get("finished")),
        "quit": bool(me.get("quitWithPenalty")),
        "bots": sum(1 for p in opponents if not p.get("isHuman")),
        "map": setting.get("mapSetting"),
        "mode": setting.get("modeSetting"),
        "dice": setting.get("diceSetting"),
        "ranked": setting.get("eloType", 0) != 0 or not setting.get("privateGame", False),
        "has_replay": bool(raw.get("hasReplay")),
        "opponents": [
            {"name": p.get("username"), "rank": p.get("rank"), "points": p.get("points"), "human": bool(p.get("isHuman"))}
            for p in opponents
        ],
    }


def _bucket(games: list[dict], skill: float = 1.0) -> dict:
    """Win stats vs. an expectation of skill / n_players per game.

    `skill` = 1 compares to seat luck alone; passing the player's overall
    wins/expected ratio compares a slice to the player's own usual level.
    """
    wins = sum(g["won"] for g in games)
    probs = [min(0.95, skill / g["players"]) for g in games]
    expected = sum(probs)
    var = sum(q * (1 - q) for q in probs)
    return {
        "games": len(games),
        "wins": wins,
        "win_rate": round(wins / len(games), 3) if games else 0,
        "expected_rate": round(expected / len(games), 3) if games else 0,
        "z": round((wins - expected) / math.sqrt(var), 2) if var > 0 else 0.0,
    }


def _breakdown(games: list[dict], key, label, skill: float = 1.0) -> list[dict]:
    groups: dict[Any, list[dict]] = defaultdict(list)
    for g in games:
        k = key(g)
        if k is not None:
            groups[k].append(g)
    return [{"key": k, "label": label(k), **_bucket(v, skill)} for k, v in sorted(groups.items(), key=lambda kv: kv[0])]


def _duration_bucket(g: dict) -> int | None:
    if not g["duration_min"]:
        return None
    return 0 if g["duration_min"] < 20 else 1 if g["duration_min"] < 40 else 2 if g["duration_min"] < 60 else 3


DURATION_LABELS = ["< 20 min", "20-40 min", "40-60 min", "60+ min"]
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th"}


def aggregate(games: list[dict]) -> dict:
    if not games:
        return {"overall": _bucket([]), "breakdowns": {}, "insights": [], "trend": [], "opponents": []}
    played = [g for g in games if g["finished"] or g["quit"]] or games
    base = _bucket(played)
    skill = max(0.2, base["wins"] / max(1e-9, base["expected_rate"] * base["games"]))
    dims = {
        "play_order": (lambda g: g["play_order"], lambda k: f"{ORDINAL.get(k, k)} to place"),
        "player_count": (lambda g: g["players"], lambda k: f"{k}-player"),
        "vp_target": (lambda g: g["vp_to_win"], lambda k: f"{k} VP"),
        "opponents": (lambda g: "bots" if g["bots"] else "humans", lambda k: "vs humans only" if k == "humans" else "with bots"),
        "duration": (_duration_bucket, lambda k: DURATION_LABELS[k]),
        "map": (lambda g: g["map"], lambda k: f"Map setting {k}"),
        "dice": (lambda g: g["dice"], lambda k: f"Dice setting {k}"),
    }
    breakdowns = {d: _breakdown(played, key, label, skill) for d, (key, label) in dims.items()}
    losses = [g for g in played if not g["won"]]
    close = [g for g in losses if g["winner_points"] - g["points"] <= 2]
    blowouts = [g for g in losses if g["points"] <= g["winner_points"] * 0.5]
    quits = sum(g["quit"] for g in played)

    insights = [
        {
            "kind": "strength" if base["z"] >= 1.5 else "weakness" if base["z"] <= -1.5 else "info",
            "title": f"Overall: {round(base['win_rate'] * 100)}% wins vs {round(base['expected_rate'] * 100)}% expected by seat count",
            "detail": f"{skill:.2f}x the win rate of an average player across {base['games']} game{'' if base['games'] == 1 else 's'} "
            f"(z = {base['z']:+.1f}). "
            "Slices below are compared against your own level, not the seat baseline.",
            "evidence": base,
        }
    ]
    for dim, rows in breakdowns.items():
        if dim in ("map", "dice"):
            continue
        for row in rows:
            if row["games"] < MIN_SAMPLE:
                continue
            delta = row["win_rate"] - row["expected_rate"]
            if row["z"] >= 1.5 and delta > 0.05:
                insights.append(_insight("strength", dim, row, delta))
            elif row["z"] <= -1.5 and delta < -0.05:
                insights.append(_insight("weakness", dim, row, delta))
    if losses:
        insights.append(
            {
                "kind": "luck" if len(close) / len(losses) >= 0.4 else "info",
                "title": f"{len(close)} of {len(losses)} losses were within 2 VP of the winner",
                "detail": "Close losses are where dice variance most often decides the game."
                if len(close) / len(losses) >= 0.4
                else "Most losses were not close: that points more to tempo/strategy than to a single bad roll.",
                "evidence": {"games": len(losses), "close": len(close)},
            }
        )
    if blowouts and losses and len(blowouts) / len(losses) >= 0.3:
        insights.append(
            {
                "kind": "weakness",
                "title": f"{len(blowouts)} losses finished with half the winner's VP or less",
                "detail": "Falling far behind usually starts with weak opening placements or an early robber war.",
                "evidence": {"games": len(losses), "blowouts": len(blowouts)},
            }
        )
    if quits and quits / len(played) >= 0.1:
        insights.append(
            {
                "kind": "weakness",
                "title": f"Quit {quits} of {len(played)} games",
                "detail": "Quitting with a penalty counts as a loss and costs karma.",
                "evidence": {"games": len(played), "quits": quits},
            }
        )
    insights.sort(key=lambda i: {"strength": 0, "weakness": 1, "luck": 2, "info": 3}[i["kind"]])

    chrono = sorted(played, key=lambda g: g["start_ms"])
    trend, window = [], 10
    for i in range(len(chrono)):
        w = chrono[max(0, i - window + 1) : i + 1]
        trend.append(
            {
                "index": i + 1,
                "id": chrono[i]["id"],
                "won": chrono[i]["won"],
                "rolling_win_rate": round(sum(g["won"] for g in w) / len(w), 3),
                "rolling_expected": round(sum(1 / g["players"] for g in w) / len(w), 3),
            }
        )

    opp: dict[str, list[dict]] = defaultdict(list)
    for g in played:
        for o in g["opponents"]:
            if o["human"] and o["name"]:
                opp[o["name"]].append(g)
    rivals = [{"name": k, **_bucket(v, skill)} for k, v in opp.items() if len(v) >= 2]
    rivals.sort(key=lambda r: -r["games"])

    avg_vp_share = sum(min(1.0, g["points"] / g["vp_to_win"]) for g in played) / len(played)
    return {
        "overall": {
            **base,
            "skill_ratio": round(skill, 2),
            "avg_vp_share": round(avg_vp_share, 3),
            "quits": quits,
            "close_losses": len(close),
            "losses": len(losses),
            "avg_rank": round(sum(g["rank"] or 0 for g in played) / len(played), 2),
            "rank_counts": dict(Counter(g["rank"] for g in played)),
        },
        "breakdowns": breakdowns,
        "insights": insights,
        "trend": trend,
        "opponents": rivals[:8],
    }


def _insight(kind: str, dim: str, row: dict, delta: float) -> dict:
    pct = round(row["win_rate"] * 100)
    base = round(row["expected_rate"] * 100)
    titles = {
        "play_order": f"You win {pct}% when you are {row['label']}",
        "player_count": f"{pct}% win rate in {row['label']} games",
        "vp_target": f"{pct}% win rate in {row['label']} games",
        "opponents": f"{pct}% win rate {row['label']}",
        "duration": f"{pct}% win rate in {row['label']} games",
    }
    return {
        "kind": kind,
        "title": titles.get(dim, f"{row['label']}: {pct}%"),
        "detail": f"Your usual level predicts about {base}% here ({row['wins']}/{row['games']} games, z = {row['z']:+.1f}).",
        "evidence": {"dimension": dim, **row},
    }


def _safe_normalize(raw: Any, username: str, user_id: str | None) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("players"), list):
        return None
    if not all(isinstance(p, dict) for p in raw["players"]):
        return None
    try:
        return normalize_game(raw, username, user_id)
    except (TypeError, ValueError, AttributeError, KeyError):
        return None


def _display_name(username: str, raws: list, user_id: str | None) -> str:
    for raw in raws:
        players = raw.get("players") if isinstance(raw, dict) else None
        for p in players if isinstance(players, list) else []:
            if not isinstance(p, dict) or not isinstance(p.get("username"), str):
                continue
            if (user_id and str(p.get("userId")) == str(user_id)) or p["username"].lower() == username.lower():
                return p["username"]
    return username


def build_profile(username: str, data: dict) -> dict:
    user_id = data.get("profileUserId")
    raws = data.get("gameDatas") if isinstance(data.get("gameDatas"), list) else []
    games = [g for g in (_safe_normalize(r, username, user_id) for r in raws) if g]
    games.sort(key=lambda g: -g["start_ms"])
    return {
        "username": _display_name(username, raws, user_id),
        "source": "colonist",
        "games": games,
        "stats": aggregate(games),
    }
