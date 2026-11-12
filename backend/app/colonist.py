"""Colonist.io public profile history: fetching, normalizing and aggregating."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import quote

import httpx


def _pct100(x: float) -> int:
    """Percent rounded half-up, matching the frontend's Math.round."""
    return int(x * 100 + 0.5)


USERNAME_RE = re.compile(r"^[\w#.\- ]{1,40}$")
HISTORY_URL = "https://colonist.io/api/profile/{username}/history"
MIN_SAMPLE = 8
# Several slices are tested per profile, so a lone z of 1.5 is too often noise.
SIGNIFICANT_Z = 2.0
MIN_HUMAN_GAMES = 10
DICE_LABELS = {0: "Random dice", 1: "Balanced dice"}


class ColonistError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def valid_username(username: str) -> bool:
    return bool(USERNAME_RE.match(username.strip()))


async def fetch_history(username: str, client: httpx.AsyncClient | None = None) -> dict:
    username = username.strip()
    if not valid_username(username):
        raise ColonistError("That doesn't look like a Colonist.io username.", 400)
    url = HISTORY_URL.format(username=quote(username, safe=""))
    owns = client is None
    client = client or httpx.AsyncClient(timeout=15, headers={"User-Agent": "catan-analyzer/0.1"})
    try:
        resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise ColonistError(f"Couldn't reach Colonist.io: {exc.__class__.__name__}") from exc
    finally:
        if owns:
            await client.aclose()
    if resp.status_code in (400, 404):
        raise ColonistError(f"No Colonist.io profile named '{username}'.", 404)
    if resp.status_code != 200:
        raise ColonistError(f"Colonist.io returned HTTP {resp.status_code}.")
    data = resp.json()
    if not isinstance(data, dict) or "gameDatas" not in data:
        raise ColonistError(f"No Colonist.io profile named '{username}'.", 404)
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
        "game_finished": bool(raw.get("finished", True)),
        "quit": bool(me.get("quitWithPenalty")),
        "bots": sum(1 for p in opponents if not p.get("isHuman")),
        "map": setting.get("mapSetting"),
        "mode": setting.get("modeSetting"),
        "dice": setting.get("diceSetting"),
        "ranked": bool(setting.get("eloType")),
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


def _length_key(games: list[dict]):
    """Short / medium / long by the player's own turn-count terciles (minutes depend on game speed)."""
    turns = sorted(g["turns"] for g in games if g["turns"])
    if len(turns) < 3 * MIN_SAMPLE:
        return (lambda g: None), (lambda k: "")
    lo, hi = turns[len(turns) // 3], turns[2 * len(turns) // 3]
    if lo == hi:
        return (lambda g: None), (lambda k: "")

    def key(g: dict) -> int | None:
        if not g["turns"]:
            return None
        return 0 if g["turns"] < lo else 1 if g["turns"] < hi else 2

    labels = [f"Short (< {lo} turns)", f"Medium ({lo}-{hi - 1} turns)", f"Long ({hi}+ turns)"]
    return key, (lambda k: labels[k])


DURATION_LABELS = ["< 20 min", "20-40 min", "40-60 min", "60+ min"]
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th"}


def _binom_z(hits: int, n: int, p: float) -> float:
    var = n * p * (1 - p)
    return round((hits - n * p) / math.sqrt(var), 2) if var > 0 else 0.0


def _close_margin(g: dict) -> int:
    return max(2, round(0.2 * g["vp_to_win"]))


def _reached_target(g: dict) -> bool:
    """Margins only mean something when the winner actually got to the VP target (no resign / timeout ending)."""
    return g["winner_points"] >= g["vp_to_win"]


def _margin_insights(played: list[dict]) -> tuple[list[dict], int, int]:
    full = [g for g in played if _reached_target(g) and not g["quit"]]
    losses = [g for g in full if not g["won"]]
    if len(losses) < MIN_SAMPLE:
        return [], 0, len(losses)
    gap = lambda g, pts: g["winner_points"] - pts  # noqa: E731
    close = [g for g in losses if gap(g, g["points"]) <= _close_margin(g)]
    blowouts = [g for g in losses if g["points"] <= g["winner_points"] * 0.5]
    # Baseline: every other losing seat in the same games.
    others = [(g, o["points"] or 0) for g in full for o in g["opponents"] if o["rank"] != 1]
    if not others:
        return [], len(close), len(losses)
    table_close = sum(gap(g, pts) <= _close_margin(g) for g, pts in others) / len(others)
    table_blow = sum(pts <= g["winner_points"] * 0.5 for g, pts in others) / len(others)
    n = len(losses)
    blow_rate = len(blowouts) / n
    z_close = _binom_z(len(close), n, table_close)
    z_blow = _binom_z(len(blowouts), n, table_blow)
    margin = _close_margin(losses[0]) if len({_close_margin(g) for g in losses}) == 1 else "2-3"
    close_ev = {"n": n, "close": len(close), "table_rate": round(table_close, 3), "z": z_close}
    title = f"{len(close)} of {n} losses within {margin} VP of the winner"
    if z_close >= SIGNIFICANT_Z:
        kind, detail = (
            "luck",
            (
                f"Other losing players in the same games were that close {_pct100(table_close)}% of the time. "
                "You keep it close, so these games often turn on a few rolls or a late steal; converting more of them is about "
                "endgame timing (holding VP cards, when to go for Longest Road / Largest Army)."
            ),
        )
    elif z_close <= -SIGNIFICANT_Z:
        kind, title, detail = (
            "weakness",
            "Only " + title,
            (
                f"Other losing players in the same games were within {margin} VP {_pct100(table_close)}% of the time. "
                "Your losses are rarely decided by the last few rolls; the game is usually gone earlier."
            ),
        )
    else:
        kind, detail = (
            "info",
            (
                f"About the same as other losing players in these games ({_pct100(table_close)}%), "
                "so nothing here says your losses are unusually close (unlucky) or unusually lopsided."
            ),
        )
    out = [_mk(kind, title, detail, **close_ev)]
    if z_blow >= SIGNIFICANT_Z and blow_rate - table_blow >= 0.1:
        detail = (
            f"{_pct100(blow_rate)}% of your losses vs {_pct100(table_blow)}% for other losing players in the same games. "
            "Falling that far behind usually starts in the opening: low-pip spots, missing ore/wheat, or no expansion room."
        )
        blow_ev = {"n": n, "blowouts": len(blowouts), "table_rate": round(table_blow, 3), "z": z_blow}
        out.append(_mk("weakness", f"{len(blowouts)} losses ended with half the winner's VP or less", detail, **blow_ev))
    return out, len(close), n


def _finish_insight(played: list[dict]) -> dict | None:
    """Where the player finishes when they don't win, vs. a uniform spread over the losing places."""
    losses = [g for g in played if not g["won"] and not g["quit"] and g["players"] >= 3 and g["rank"]]
    if len(losses) < MIN_SAMPLE * 2:
        return None
    second = sum(g["rank"] == 2 for g in losses)
    last = sum(g["rank"] == g["players"] for g in losses)
    p = sum(1 / (g["players"] - 1) for g in losses) / len(losses)
    z2, zl = _binom_z(second, len(losses), p), _binom_z(last, len(losses), p)
    s, lp = _pct100(second / len(losses)), _pct100(last / len(losses))
    base = _pct100(p)
    ev = {"games": len(losses), "second": second, "last": last, "expected_rate": round(p, 3)}
    if zl >= SIGNIFICANT_Z:
        return _mk(
            "weakness",
            f"When you lose, you finish last {lp}% of the time",
            f"{last} of {len(losses)} losses (an even spread would be {base}%). Last place usually means a weak start: check your "
            "opening production and whether you're getting robbed as the early leader.",
            **ev,
        )
    if z2 >= SIGNIFICANT_Z:
        return _mk(
            "strength",
            f"When you lose, you finish 2nd {s}% of the time",
            f"{second} of {len(losses)} losses (an even spread would be {base}%). You're usually in contention; the gap to winning "
            "is closing, not catching up.",
            **ev,
        )
    return _mk(
        "info",
        f"When you lose: 2nd {s}%, last {lp}%",
        f"Close to an even spread ({base}% each) across {len(losses)} losses.",
        **ev,
    )


def _mk(kind: str, title: str, detail: str, **evidence) -> dict:
    return {"kind": kind, "title": title, "detail": detail, "evidence": evidence}


def aggregate(games: list[dict]) -> dict:
    if not games:
        return {"overall": _bucket([]), "breakdowns": {}, "insights": [], "trend": [], "opponents": []}
    # Abandoned games don't count, but leaving or timing out of a game that went on is a loss.
    played = [g for g in games if g.get("game_finished", True) or g["quit"]] or games
    human = [g for g in played if not g["bots"]]
    bot_games = len(played) - len(human)
    scope = human if bot_games and len(human) >= MIN_HUMAN_GAMES else played
    base = _bucket(scope)
    skill = max(0.2, base["wins"] / max(1e-9, base["expected_rate"] * base["games"]))
    length_key, length_label = _length_key(scope)
    dims = {
        "play_order": (lambda g: g["play_order"], lambda k: f"{ORDINAL.get(k, k)} to place"),
        "player_count": (lambda g: g["players"], lambda k: f"{k}-player"),
        "vp_target": (lambda g: g["vp_to_win"], lambda k: f"{k} VP"),
        "opponents": (lambda g: "bots" if g["bots"] else "humans", lambda k: "vs humans only" if k == "humans" else "with bots"),
        "ranked": (lambda g: int(bool(g.get("ranked"))), lambda k: "Ranked" if k else "Casual"),
        "dice": (lambda g: g["dice"], lambda k: DICE_LABELS.get(k, f"Dice setting {k}")),
        "length": (length_key, length_label),
        "duration": (_duration_bucket, lambda k: DURATION_LABELS[k]),
        "map": (lambda g: g["map"], lambda k: f"Map setting {k}"),
    }
    breakdowns = {d: _breakdown(scope, key, label, skill) for d, (key, label) in dims.items()}
    breakdowns["opponents"] = _breakdown(played, *dims["opponents"], skill)
    losses = [g for g in scope if not g["won"]]
    quits = sum(g["quit"] for g in scope)
    left = sum(1 for g in scope if not g["finished"] and not g["quit"] and not g["won"])
    ranked_share = sum(bool(g.get("ranked")) for g in scope) / len(scope)

    overall_kind = "strength" if base["z"] >= SIGNIFICANT_Z else "weakness" if base["z"] <= -SIGNIFICANT_Z else "info"
    who = "vs humans" if scope is human and bot_games else "overall"
    detail = f"{base['wins']}/{base['games']} games, {skill:.2f}x what seat count alone predicts (z = {base['z']:+.1f}). "
    if ranked_share >= 0.5:
        detail += (
            "Most of these are ranked games, where matchmaking pairs you with similar ratings and pulls win rates toward the "
            "seat baseline, so a rate near it is normal even for strong players. "
        )
    if scope is played and bot_games and len(human) < MIN_HUMAN_GAMES:
        overall_kind = "info"
        detail += f"{bot_games} of {len(played)} games had bot opponents, so this overstates your level against people. "
    detail += "Slices below are compared against this level, not the seat baseline."
    title = f"Win rate {who}: {_pct100(base['win_rate'])}% vs {_pct100(base['expected_rate'])}% by seat count"
    insights = [_mk(overall_kind, title, detail, **base)]
    if scope is human and bot_games:
        b = _bucket([g for g in played if g["bots"]])
        insights.append(
            _mk(
                "info",
                f"{b['wins']}/{b['games']} wins in games with bots",
                "Left out of the stats above and below: bots are easier to beat than people, so they would inflate your level.",
                **b,
            )
        )

    for dim, rows in breakdowns.items():
        if dim in ("map", "duration") or len(rows) < 2 or (dim == "opponents" and scope is human):
            continue
        for row in rows:
            if row["games"] < MIN_SAMPLE:
                continue
            delta = row["win_rate"] - row["expected_rate"]
            if row["z"] >= SIGNIFICANT_Z and delta > 0.05:
                insights.append(_insight("strength", dim, row, delta))
            elif row["z"] <= -SIGNIFICANT_Z and delta < -0.05:
                insights.append(_insight("weakness", dim, row, delta))
    margin_insights, close_losses, margin_losses = _margin_insights(scope)
    finish = _finish_insight(scope)
    table_insights = margin_insights + ([finish] if finish else [])
    if any(g["bots"] for g in scope):
        for i in table_insights:
            i["kind"] = "info"
            i["detail"] += " Most of these games had bots, which play differently from people, so read this loosely."
    insights += table_insights
    if quits + left and (quits + left) / len(scope) >= 0.1:
        insights.append(
            _mk(
                "weakness",
                f"Quit or left {quits + left} of {len(scope)} games",
                "Counted as losses. Quitting with a penalty also costs karma; if you were losing anyway, playing it out still "
                "teaches you more about the endgame.",
                games=len(scope),
                quits=quits,
                left=left,
            )
        )
    insights.sort(key=lambda i: {"strength": 0, "weakness": 1, "luck": 2, "info": 3}[i["kind"]])

    chrono = sorted(scope, key=lambda g: g["start_ms"])
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
    for g in scope:
        for o in g["opponents"]:
            if o["human"] and o["name"]:
                opp[o["name"]].append(g)
    rivals = [{"name": k, **_bucket(v, skill)} for k, v in opp.items() if len(v) >= 2]
    rivals.sort(key=lambda r: -r["games"])

    avg_vp_share = sum(min(1.0, g["points"] / g["vp_to_win"]) for g in scope) / len(scope)
    return {
        "overall": {
            **base,
            "skill_ratio": round(skill, 2),
            "avg_vp_share": round(avg_vp_share, 3),
            "quits": quits,
            "left": left,
            "bot_games_excluded": bot_games if scope is human else 0,
            "close_losses": close_losses,
            "losses": len(losses),
            "margin_losses": margin_losses,
            "avg_rank": round(sum(g["rank"] or 0 for g in scope) / len(scope), 2),
            "avg_players": round(sum(g["players"] for g in scope) / len(scope), 2),
            "rank_counts": dict(Counter(g["rank"] for g in scope)),
        },
        "breakdowns": breakdowns,
        "insights": insights,
        "trend": trend,
        "opponents": rivals[:8],
    }


def _insight(kind: str, dim: str, row: dict, delta: float) -> dict:
    pct = _pct100(row["win_rate"])
    base = _pct100(row["expected_rate"])
    titles = {
        "play_order": f"You win {pct}% when you are {row['label']}",
        "player_count": f"{pct}% win rate in {row['label']} games",
        "vp_target": f"{pct}% win rate in {row['label']} games",
        "opponents": f"{pct}% win rate {row['label']}",
        "ranked": f"{pct}% win rate in {row['label'].lower()} games",
        "dice": f"{pct}% win rate with {row['label'].lower()}",
        "length": f"{pct}% win rate in {row['label'].split(' (')[0].lower()} games",
    }
    detail = f"{row['wins']}/{row['games']} games; your usual level predicts about {base}% here (z = {row['z']:+.1f})."
    if dim == "dice" and row["key"] == 1:
        detail += (
            " Balanced dice cut roll variance, so doing better here means your play shows more when luck is reduced."
            if kind == "strength"
            else " Balanced dice cut roll variance; doing worse here suggests random dice have been flattering your results."
        )
    elif dim == "length":
        detail += " Long games reward ore/wheat engines and dev cards; short ones reward fast expansion and early Longest Road."
    elif dim == "play_order" and kind == "weakness" and row["key"] and row["key"] >= 3:
        detail += " Later seats get worse first picks but the snake order gives them back-to-back settlements: use them to pair resources."
    return {
        "kind": kind,
        "title": titles.get(dim, f"{row['label']}: {pct}%"),
        "detail": detail,
        "evidence": {"dimension": dim, **row},
    }


def build_profile(username: str, data: dict) -> dict:
    user_id = data.get("profileUserId")
    games = [g for g in (normalize_game(r, username, user_id) for r in data.get("gameDatas") or []) if g]
    games.sort(key=lambda g: -g["start_ms"])
    return {"username": username, "source": "colonist", "games": games, "stats": aggregate(games)}
