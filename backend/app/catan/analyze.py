"""Per-game luck vs. decision analysis on the normalized event format.

Event types (``t``): place, gain, lose, roll, discard, robber, steal,
play_dev, buy_dev, trade_bank, award, reveal_vp, end_turn, game_end.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .board import RESOURCES, Board, Corner, Hex, cid, edge_corners, parse_id, pips

DICE_P = {t: (6 - abs(7 - t)) / 36 for t in range(2, 13)}
STRATEGY_LABELS = {
    "city_rush": "Ore/Wheat city rush",
    "expansion": "Road & settlement expansion",
    "dev_cards": "Development cards",
    "balanced": "Balanced",
}


@dataclass
class _PS:
    color: int
    settlements: set = field(default_factory=set)
    cities: set = field(default_factory=set)
    roads: set = field(default_factory=set)
    hand: int = 0
    knights: int = 0
    dev_bought: int = 0
    vp_cards: int = 0
    awards: set = field(default_factory=set)
    roll_income: float = 0.0
    roll_expected: float = 0.0
    roll_var: float = 0.0
    blocked: float = 0.0
    stolen_from: int = 0
    stole: int = 0
    discarded: int = 0
    sevens_discards: int = 0
    bank_trades: int = 0
    bank_given: int = 0
    mono_gain: int = 0
    setup_pcts: list = field(default_factory=list)
    setup_regret: list = field(default_factory=list)
    robber_moves: int = 0
    robber_on_leader: int = 0
    first_city: int | None = None
    first_settlement: int | None = None
    mid_settlements: int = 0
    pieces: Counter = field(default_factory=Counter)

    def vp(self) -> int:
        return len(self.settlements) + 2 * len(self.cities) + 2 * len(self.awards)


class Analyzer:
    def __init__(self, game: dict):
        self.game = game
        self.board = Board.from_dict(game["board"])
        self.colors = [p["color"] for p in game["players"]]
        self.names = {p["color"]: p["name"] for p in game["players"]}
        self.ps = {c: _PS(c) for c in self.colors}
        self.vp_to_win = game.get("vp_to_win", 10)
        self.occupied: dict[Corner, int] = {}
        self.turn = 0
        self.timeline: list[dict] = []
        self.moments: list[dict] = []
        self.robber_since: dict[int, int] = {}
        self.rolls: list[dict] = []

    # ----- production model ----------------------------------------------------
    def income_by_total(self, ps: _PS, robber: bool = True) -> dict[int, int]:
        out: dict[int, int] = defaultdict(int)
        for c in ps.settlements | ps.cities:
            mult = 2 if c in ps.cities else 1
            for h in self.board.corner_hexes(c):
                t = self.board.tiles[h]
                if t.number and (not robber or h != self.board.robber):
                    out[t.number] += mult
        return out

    def expected_per_roll(self, ps: _PS, robber: bool = True) -> float:
        return sum(DICE_P[t] * n for t, n in self.income_by_total(ps, robber).items())

    def strength(self, ps: _PS) -> float:
        lead = max(p.vp() for p in self.ps.values())
        late = max(0.0, 1 - lead / self.vp_to_win)
        n = len(self.colors)
        prod_round = self.expected_per_roll(ps) * n
        return ps.vp() + (0.55 + 1.4 * late) * prod_round + 0.12 * min(ps.hand, 8) + 0.35 * ps.knights + 0.25 * ps.dev_bought

    def win_probs(self) -> dict[int, float]:
        s = {c: self.strength(p) for c, p in self.ps.items()}
        lead = max(p.vp() for p in self.ps.values())
        k = 0.55 + 1.6 * (lead / self.vp_to_win) ** 2
        m = max(s.values())
        e = {c: math.exp(k * (v - m)) for c, v in s.items()}
        z = sum(e.values())
        return {c: v / z for c, v in e.items()}

    # ----- placement quality --------------------------------------------------
    def legal(self, c: Corner) -> bool:
        return c not in self.occupied and all(n not in self.occupied for n in self.board.corner_neighbors(c))

    def spot_value(self, ps: _PS, c: Corner) -> float:
        have = {r for s in ps.settlements | ps.cities for r in self.board.corner_resources(s)}
        v = float(self.board.corner_pips(c))
        new = {r for r in self.board.corner_resources(c) if r in RESOURCES} - have
        v += 0.8 * len(new)
        if self.board.corner_port(c):
            v += 0.6
        return v

    def rate_spot(self, ps: _PS, c: Corner, candidates: list[Corner]) -> tuple[float, float, Corner | None]:
        vals = sorted(((self.spot_value(ps, x), x) for x in candidates), key=lambda t: t[0])
        if not vals:
            return 1.0, 0.0, None
        mine = self.spot_value(ps, c)
        below = sum(1 for v, _ in vals if v < mine)
        equal = sum(1 for v, _ in vals if v == mine)
        pct = (below + 0.5 * equal) / len(vals)
        best_v, best_c = vals[-1]
        return pct, best_v - mine, best_c

    # ----- event processing ---------------------------------------------------
    def leader(self, exclude: int | None = None) -> int | None:
        cands = [p for c, p in self.ps.items() if c != exclude]
        if not cands:
            return None
        return max(cands, key=lambda p: (p.vp(), self.expected_per_roll(p))).color

    def moment(self, kind: str, player: int, polarity: int, magnitude: float, title: str, detail: str, **extra) -> None:
        self.moments.append(
            {
                "turn": self.turn,
                "kind": kind,
                "player": player,
                "polarity": polarity,
                "magnitude": round(min(1.0, max(0.0, magnitude)), 3),
                "title": title,
                "detail": detail,
                **extra,
            }
        )

    def run(self) -> None:
        setup = True
        self.snapshot()
        for ev in self.game["events"]:
            t = ev["t"]
            prev_turn = self.turn
            self.turn = ev.get("turn", self.turn)
            if self.turn != prev_turn and prev_turn > 0:
                self.snapshot(prev_turn)
            if self.turn > 0 and setup:
                setup = False
                self.snapshot(0)
            p = self.ps.get(ev.get("player")) if "player" in ev else None
            getattr(self, f"on_{t}", lambda e, p: None)(ev, p)
        self.snapshot(self.turn)

    def snapshot(self, turn: int | None = None) -> None:
        turn = self.turn if turn is None else turn
        wp = self.win_probs()
        row = {"turn": turn}
        for c, ps in self.ps.items():
            row[f"vp_{c}"] = ps.vp()
            row[f"wp_{c}"] = round(wp[c], 4)
            row[f"luck_{c}"] = round(ps.roll_income - ps.roll_expected, 2)
            row[f"prod_{c}"] = round(self.expected_per_roll(ps), 3)
        if self.timeline and self.timeline[-1]["turn"] == turn:
            self.timeline[-1] = row
        else:
            self.timeline.append(row)

    def on_place(self, ev: dict, p: _PS) -> None:
        loc = parse_id(ev["loc"])
        piece = ev["piece"]
        p.pieces[piece] += 1 if not ev.get("setup") else 0
        if piece == "road":
            p.roads.add(loc)
            return
        if piece == "city":
            p.settlements.discard(loc)
            p.cities.add(loc)
            if p.first_city is None:
                p.first_city = self.turn
            return
        c: Corner = loc  # type: ignore[assignment]
        if ev.get("setup"):
            cands = [x for x in self.board.corners if self.legal(x)]
            pct, regret, best = self.rate_spot(p, c, cands)
            p.setup_pcts.append(pct)
            p.setup_regret.append(regret)
            nth = len(p.setup_pcts)
            res = ", ".join(
                f"{self.board.tiles[h].number} {self.board.tiles[h].resource}"
                for h in self.board.corner_hexes(c)
                if self.board.tiles[h].number
            )
            info = dict(loc=cid(c), best=cid(best) if best else None)
            if pct >= 0.9:
                self.moment(
                    "decision",
                    p.color,
                    1,
                    0.35 + 0.4 * (pct - 0.9) * 10,
                    f"Strong opening settlement #{nth}",
                    f"Took {res or 'this spot'} - better than {round(pct * 100)}% of open spots.",
                    **info,
                )
            elif pct < 0.6 or regret >= 3:
                self.moment(
                    "decision",
                    p.color,
                    -1,
                    min(1.0, 0.25 + regret / 8),
                    f"Weak opening settlement #{nth}",
                    f"Took {res or 'this spot'} ({round(pct * 100)}th percentile); the best open spot was worth "
                    f"~{regret:.1f} more pips/diversity.",
                    **info,
                )
        else:
            cands = [x for e in p.roads for x in edge_corners(e) if x in self.board.corners and self.legal(x)] or [c]
            pct, regret, _ = self.rate_spot(p, c, list(set(cands) | {c}))
            p.mid_settlements += 1
            if p.first_settlement is None:
                p.first_settlement = self.turn
            if regret >= 3:
                self.moment(
                    "decision",
                    p.color,
                    -1,
                    0.2 + regret / 10,
                    "Settled a weaker spot",
                    f"A reachable spot was worth ~{regret:.1f} more.",
                    loc=cid(c),
                )
        self.occupied[c] = p.color
        p.settlements.add(c)

    def on_gain(self, ev: dict, p: _PS) -> None:
        n = sum(ev["cards"].values())
        p.hand += n
        if ev.get("source") == "monopoly":
            p.mono_gain += n
            if n >= 4:
                self.moment(
                    "decision", p.color, 1, 0.2 + n / 15, f"Monopoly for {n} cards", f"Took {n} {next(iter(ev['cards']))} from the table."
                )

    def on_lose(self, ev: dict, p: _PS) -> None:
        p.hand = max(0, p.hand - sum(ev["cards"].values()))

    def on_roll(self, ev: dict, p: _PS) -> None:
        total = sum(ev["dice"])
        self.rolls.append({"turn": self.turn, "player": ev["player"], "total": total})
        for ps in self.ps.values():
            inc = self.income_by_total(ps)
            inc_free = self.income_by_total(ps, robber=False)
            mean = sum(DICE_P[t] * n for t, n in inc.items())
            sq = sum(DICE_P[t] * n * n for t, n in inc.items())
            ps.roll_expected += mean
            ps.roll_var += sq - mean * mean
            ps.roll_income += inc.get(total, 0) if total != 7 else 0
            ps.blocked += sum(DICE_P[t] * n for t, n in inc_free.items()) - mean
            ps.hand += inc.get(total, 0) if total != 7 else 0

    def on_discard(self, ev: dict, p: _PS) -> None:
        n = sum(ev["cards"].values())
        p.hand = max(0, p.hand - n)
        p.discarded += n
        p.sevens_discards += 1
        self.moment(
            "decision",
            p.color,
            -1,
            0.15 + n / 10,
            f"Discarded {n} cards to a 7",
            f"Holding {n * 2}+ cards into a 7 cost {n} cards. Spending or trading earlier avoids this.",
        )

    def on_robber(self, ev: dict, p: _PS) -> None:
        h: Hex = parse_id(ev["hex"])  # type: ignore[assignment]
        self.board.robber = h
        p.robber_moves += 1
        tile = self.board.tiles[h]
        hit = {self.occupied[c] for c in self.occupied if h in self.board.corner_hexes(c)} - {p.color}
        lead = self.leader(exclude=p.color)
        if lead in hit:
            p.robber_on_leader += 1
        for c in hit:
            victim = self.ps[c]
            mult = sum(2 if x in victim.cities else 1 for x in victim.settlements | victim.cities if h in self.board.corner_hexes(x))
            loss = pips(tile.number) * mult
            recent = next(
                (
                    m
                    for m in reversed(self.moments)
                    if m.get("hex") == cid(h) and m["player"] == c and m["kind"] == "luck" and self.turn - m["last_turn"] <= 12
                ),
                None,
            )
            if loss >= 5 and recent:
                recent["count"] += 1
                recent["last_turn"] = self.turn
                recent["magnitude"] = round(min(1.0, recent["magnitude"] + 0.08), 3)
                recent["title"] = f"Robber camped on your {tile.number} {tile.resource} ({recent['count']}x)"
            elif loss >= 5:
                self.moment(
                    "luck",
                    c,
                    -1,
                    0.15 + loss / 20,
                    f"Robber on your {tile.number} {tile.resource}",
                    f"{self.names[p.color]} blocked ~{loss} pips of your production.",
                    hex=cid(h),
                    by=p.color,
                    count=1,
                    last_turn=self.turn,
                )
        if not hit:
            self.moment("decision", p.color, -1, 0.2, "Robber hit nobody", "Moved the robber to a hex with no opponents.", hex=cid(h))
        elif lead not in hit and lead is not None and self.ps[lead].vp() - max(self.ps[c].vp() for c in hit) >= 2:
            self.moment(
                "decision",
                p.color,
                -1,
                0.2,
                "Robbed a trailing player",
                f"{self.names[lead]} was leading by 2+ VP and wasn't touched.",
                hex=cid(h),
            )

    def on_steal(self, ev: dict, _p: _PS) -> None:
        thief, victim = self.ps[ev["thief"]], self.ps[ev["victim"]]
        thief.stole += 1
        thief.hand += 1
        victim.stolen_from += 1
        victim.hand = max(0, victim.hand - 1)

    def on_buy_dev(self, ev: dict, p: _PS) -> None:
        p.dev_bought += 1
        p.hand = max(0, p.hand - 3)

    def on_play_dev(self, ev: dict, p: _PS) -> None:
        if ev["card"] == "knight":
            p.knights += 1

    def on_trade_bank(self, ev: dict, p: _PS) -> None:
        given = sum(ev["give"].values())
        p.bank_trades += 1
        p.bank_given += given
        p.hand += sum(ev["get"].values()) - given

    def on_award(self, ev: dict, p: _PS) -> None:
        award = ev["award"]
        label = "Longest Road" if award == "longest_road" else "Largest Army"
        for other in self.ps.values():
            if award in other.awards and other is not p:
                other.awards.discard(award)
                self.moment("decision", other.color, -1, 0.45, f"Lost {label}", f"{self.names[p.color]} took it (-2 VP).")
        p.awards.add(award)
        self.moment("decision", p.color, 1, 0.5, f"Took {label}", "+2 VP.")

    def on_reveal_vp(self, ev: dict, p: _PS) -> None:
        p.vp_cards = ev["count"]

    # ----- spend tracking for build events -------------------------------------
    def on_end_turn(self, ev: dict, p: _PS) -> None:
        pass


def _hand_spend(game: dict) -> None:
    """Builds don't carry costs in the event log; subtract them here."""
    cost = {"road": 2, "settlement": 4, "city": 5}
    for ev in game["events"]:
        if ev["t"] == "place" and not ev.get("setup") and not ev.get("free"):
            ev["_spend"] = cost[ev["piece"]]


def classify_strategy(ps: _PS, board: Board) -> str:
    setup_res: Counter = Counter()
    for c in list(ps.settlements | ps.cities):
        for h in board.corner_hexes(c):
            t = board.tiles[h]
            if t.resource in RESOURCES:
                setup_res[t.resource] += pips(t.number)
    ow = setup_res["ore"] + setup_res["grain"]
    lb = setup_res["lumber"] + setup_res["brick"]
    scores = {
        "city_rush": 2.0 * len(ps.cities) + (ow - lb) / 4,
        "expansion": 2.0 * ps.mid_settlements + ps.pieces["road"] / 3 + (2 if "longest_road" in ps.awards else 0),
        "dev_cards": 0.9 * ps.dev_bought + (2 if "largest_army" in ps.awards else 0),
    }
    top = sorted(scores.items(), key=lambda kv: -kv[1])
    if top[0][1] < 4 or top[0][1] - top[1][1] < 1.5:
        return "balanced"
    return top[0][0]


def analyze_game(game: dict, focus: int) -> dict:
    game = {**game, "events": [dict(e) for e in game["events"]]}
    _hand_spend(game)
    a = Analyzer(game)
    for ev in game["events"]:
        if "_spend" in ev:
            ev.setdefault("_player_spend", True)
    _patch_spend(a)
    a.run()
    me = a.ps[focus]
    opps = [p for c, p in a.ps.items() if c != focus]
    winner = game["winner"]
    won = winner == focus

    def luck_z(ps: _PS) -> float:
        return (ps.roll_income - ps.roll_expected) / math.sqrt(ps.roll_var) if ps.roll_var > 0 else 0.0

    # Dice streak moments for the focus player (windows of one round per player).
    _dice_streaks(a, focus)

    my_z = luck_z(me)
    opp_z = sum(luck_z(p) for p in opps) / len(opps)
    rel_luck = my_z - opp_z
    robber_cost = me.blocked - sum(p.blocked for p in opps) / len(opps)
    steal_net = me.stole - me.stolen_from
    # Luck index: positive = RNG favored you. Roughly a z-score.
    luck_index = rel_luck - 0.08 * robber_cost + 0.04 * steal_net

    scores = {c: _decision(a, c) for c in a.colors}
    components, decision_score = scores[focus]
    opp_decision = sum(scores[p.color][1] for p in opps) / len(opps)
    decision_edge = round(decision_score - opp_decision)
    opp_setup = sum(scores[p.color][0]["opening"] for p in opps) / len(opps)

    verdict, verdict_detail = _verdict(won, luck_index, decision_edge)
    final_vp = {c: p.vp() + p.vp_cards for c, p in a.ps.items()}

    moments = sorted(a.moments, key=lambda m: (m["turn"], -m["magnitude"]))
    for m in moments:
        m["mine"] = m["player"] == focus
    mine = [m for m in moments if m["mine"]]
    dec = sorted((m for m in mine if m["kind"] == "decision"), key=lambda m: -m["magnitude"])[:5]
    luck = sorted((m for m in mine if m["kind"] == "luck"), key=lambda m: -m["magnitude"])[:4]
    critical = sorted(dec + luck, key=lambda m: m["turn"])

    return {
        "focus": focus,
        "won": won,
        "winner": winner,
        "players": [
            {
                **p,
                "final_vp": final_vp[p["color"]],
                "strategy": classify_strategy(a.ps[p["color"]], a.board),
                "luck_z": round(luck_z(a.ps[p["color"]]), 2),
                "decision_score": scores[p["color"]][1],
                "setup_pct": scores[p["color"]][0]["opening"],
            }
            for p in game["players"]
        ],
        "play_order": game["play_order"],
        "seat": game["play_order"].index(focus) + 1,
        "turns": a.turn,
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "luck_index": round(luck_index, 2),
        "decision_score": decision_score,
        "opp_decision_score": round(opp_decision),
        "decision_edge": round(decision_edge),
        "components": components,
        "opp_setup_pct": round(opp_setup, 3),
        "luck": {
            "dice_z": round(my_z, 2),
            "opp_dice_z": round(opp_z, 2),
            "roll_income": round(me.roll_income),
            "roll_expected": round(me.roll_expected, 1),
            "robber_blocked": round(me.blocked, 1),
            "stolen_from": me.stolen_from,
            "stole": me.stole,
            "sevens": sum(1 for r in a.rolls if r["total"] == 7),
        },
        "stats": {
            "discarded": me.discarded,
            "bank_trades": me.bank_trades,
            "dev_bought": me.dev_bought,
            "knights": me.knights,
            "first_city": me.first_city,
            "first_settlement": me.first_settlement,
            "cities": len(me.cities),
            "settlements": len(me.settlements),
            "awards": sorted(me.awards),
            "vp_cards": me.vp_cards,
        },
        "strategy": classify_strategy(me, a.board),
        "dice_histogram": _dice_hist(a.rolls),
        "timeline": a.timeline,
        "moments": moments,
        "critical": critical,
        "board": game["board"],
        "buildings": {
            str(c): {
                "settlements": [cid(x) for x in p.settlements],
                "cities": [cid(x) for x in p.cities],
                "roads": [cid(x) for x in p.roads],
            }
            for c, p in a.ps.items()
        },
    }


def _patch_spend(a: Analyzer) -> None:
    orig = a.on_place

    def on_place(ev: dict, p: _PS) -> None:
        if "_spend" in ev:
            p.hand = max(0, p.hand - ev["_spend"])
        orig(ev, p)

    a.on_place = on_place  # type: ignore[method-assign]


def _tempo(a: Analyzer, focus: int) -> float:
    """Share of the game the player spent at or above the median VP, adjusted for VP at the midpoint."""
    rows = a.timeline[1:]
    if not rows:
        return 0.5
    ahead = 0
    for r in rows:
        vps = sorted(r[f"vp_{c}"] for c in a.colors)
        med = vps[len(vps) // 2]
        ahead += r[f"vp_{focus}"] >= med
    mid = rows[len(rows) // 2]
    best = max(mid[f"vp_{c}"] for c in a.colors) or 1
    return 0.6 * ahead / len(rows) + 0.4 * mid[f"vp_{focus}"] / best


def _dice_streaks(a: Analyzer, focus: int) -> None:
    """Flag stretches where the focus player's roll income ran far from expectation."""
    n = len(a.colors)
    window = 3 * n  # three rounds of rolls
    rows = a.timeline
    i = 1
    while i + window < len(rows):
        a0, a1 = rows[i], rows[i + window]
        d = a1[f"luck_{focus}"] - a0[f"luck_{focus}"]
        if abs(d) >= 4:
            a.moments.append(
                {
                    "turn": a1["turn"],
                    "kind": "luck",
                    "player": focus,
                    "polarity": 1 if d > 0 else -1,
                    "magnitude": round(min(1.0, 0.2 + abs(d) / 14), 3),
                    "title": "Hot dice streak" if d > 0 else "Cold dice streak",
                    "detail": f"Turns {a0['turn']}-{a1['turn']}: {abs(d):.0f} cards {'above' if d > 0 else 'below'} what your "
                    "buildings should have produced.",
                }
            )
            i += window
        else:
            i += 1


def _dice_hist(rolls: list[dict]) -> list[dict]:
    c = Counter(r["total"] for r in rolls)
    n = len(rolls)
    return [{"total": t, "count": c.get(t, 0), "expected": round(DICE_P[t] * n, 2)} for t in range(2, 13)]


def _decision(a: Analyzer, color: int) -> tuple[dict, int]:
    ps = a.ps[color]
    robber_acc = ps.robber_on_leader / ps.robber_moves if ps.robber_moves else None
    components = {
        "opening": round(sum(ps.setup_pcts) / len(ps.setup_pcts), 3) if ps.setup_pcts else 0.5,
        "tempo": round(_tempo(a, color), 3),
        "robber": round(robber_acc, 3) if robber_acc is not None else None,
        "hand_management": round(1 - min(1.0, ps.discarded / 10), 3),
        "awards": round(min(1.0, len(ps.awards) / 2), 3),
    }
    # Tempo (being ahead on VP) is shown but not scored: it is an outcome that good dice produce too,
    # so scoring it would count luck as good decisions.
    weights = {"opening": 0.45, "robber": 0.2, "hand_management": 0.15, "awards": 0.2}
    tot = sum(w for k, w in weights.items() if components[k] is not None)
    score = round(100 * sum(components[k] * w for k, w in weights.items() if components[k] is not None) / tot)
    return components, score


def _verdict(won: bool, luck: float, edge: float) -> tuple[str, str]:
    """luck: relative dice/robber z-score; edge: decision score minus opponents' average."""
    if won:
        if luck >= 0.5 and edge < 0:
            return "Lucky win", "The dice carried this one more than your decisions did."
        if luck >= 0.5:
            return "Good play, good dice", "You outplayed the table, and the dice also leaned your way."
        if edge >= 0:
            return "Earned win", "You won on decisions without help from the dice."
        return "Scrappy win", "Neither the dice nor your decision metrics stood out; you found a way."
    if luck <= -1.0 and edge >= 0:
        return "Lost to RNG", "You matched or out-decided the table; the dice and robber cost you this one."
    if luck <= -0.5 and edge < 0:
        return "Unlucky and outplayed", "Bad dice made it harder, but opponents also made better decisions."
    if luck <= -0.5:
        return "Unlucky loss", "Dice ran a bit cold; your decisions matched or beat the table."
    if edge < 0 and luck >= 0.5:
        return "Outplayed", "The dice were on your side; the gap came from decisions."
    if edge < 0:
        return "Strategic loss", "Fair dice; opponents made better decisions."
    return "Close call", "Your decision metrics matched or beat the table; small edges or timing decided it."
