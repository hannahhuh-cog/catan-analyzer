"""A compact heuristic Catan simulator used to generate demo games.

It emits games in the normalized event format consumed by the analyzer, so
the demo exercises the same code path as imported Colonist.io replays.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from .board import RESOURCES, Board, Corner, Edge, cid, edge_corners, random_board

COSTS = {
    "road": {"lumber": 1, "brick": 1},
    "settlement": {"lumber": 1, "brick": 1, "wool": 1, "grain": 1},
    "city": {"grain": 2, "ore": 3},
    "dev": {"wool": 1, "grain": 1, "ore": 1},
}
DEV_DECK = ["knight"] * 14 + ["victory_point"] * 5 + ["road_building"] * 2 + ["year_of_plenty"] * 2 + ["monopoly"] * 2

STRATEGIES = {
    "balanced": {"lumber": 1.0, "brick": 1.0, "wool": 1.0, "grain": 1.1, "ore": 1.0},
    "city_rush": {"lumber": 0.7, "brick": 0.7, "wool": 0.9, "grain": 1.4, "ore": 1.5},
    "expansion": {"lumber": 1.5, "brick": 1.5, "wool": 1.0, "grain": 0.9, "ore": 0.6},
    "dev_cards": {"lumber": 0.7, "brick": 0.7, "wool": 1.3, "grain": 1.3, "ore": 1.3},
}
COLORS = [1, 2, 3, 5]
COLOR_NAMES = {1: "Blue", 2: "Red", 3: "Orange", 4: "Brown", 5: "White"}


@dataclass
class PlayerSpec:
    name: str
    strategy: str = "balanced"
    skill: float = 0.6  # 0..1: placement accuracy, build discipline, trading


@dataclass
class _P:
    color: int
    spec: PlayerSpec
    hand: Counter = field(default_factory=Counter)
    settlements: set = field(default_factory=set)
    cities: set = field(default_factory=set)
    roads: set = field(default_factory=set)
    dev_hand: list = field(default_factory=list)
    dev_bought_this_turn: list = field(default_factory=list)
    knights: int = 0
    vp_cards: int = 0

    def cards(self) -> int:
        return sum(self.hand.values())


class Game:
    def __init__(self, specs: list[PlayerSpec], seed: int, vp_to_win: int = 10, max_turns: int = 400):
        self.rng = random.Random(seed)
        self.board: Board = random_board(self.rng)
        self.initial_board = self.board.to_dict()
        self.players = [_P(COLORS[i], s) for i, s in enumerate(specs)]
        self.vp_to_win = vp_to_win
        self.max_turns = max_turns
        self.deck = DEV_DECK[:]
        self.rng.shuffle(self.deck)
        self.events: list[dict] = []
        self.turn = 0
        self.longest_road: int | None = None
        self.largest_army: int | None = None
        self.occupied: dict[Corner, int] = {}
        self.road_owner: dict[Edge, int] = {}

    # ----- helpers -------------------------------------------------------------
    def emit(self, **ev) -> None:
        ev["turn"] = self.turn
        self.events.append(ev)

    def vp(self, p: _P, hidden: bool = False) -> int:
        v = len(p.settlements) + 2 * len(p.cities)
        v += 2 if self.longest_road == p.color else 0
        v += 2 if self.largest_army == p.color else 0
        return v + (p.vp_cards if hidden else 0)  # hidden=True counts unrevealed VP cards

    def can_afford(self, p: _P, item: str) -> bool:
        return all(p.hand[r] >= n for r, n in COSTS[item].items())

    def pay(self, p: _P, item: str) -> None:
        for r, n in COSTS[item].items():
            p.hand[r] -= n

    def legal_corner(self, c: Corner) -> bool:
        return c not in self.occupied and all(n not in self.occupied for n in self.board.corner_neighbors(c))

    def corner_value(self, p: _P, c: Corner, noise: float = 0.0) -> float:
        w = STRATEGIES[p.spec.strategy]
        have = {r for s in p.settlements | p.cities for r in self.board.corner_resources(s)}
        v = 0.0
        for h in self.board.corner_hexes(c):
            t = self.board.tiles[h]
            if t.resource in RESOURCES:
                from .board import pips

                v += pips(t.number) * w[t.resource]
                if t.resource not in have:
                    v += 1.2
        port = self.board.corner_port(c)
        if port:
            v += 1.5 if port == "3:1" else (2.0 if w.get(port, 1) > 1.1 else 0.8)
        return v + self.rng.gauss(0, noise)

    def reachable_corners(self, p: _P) -> list[Corner]:
        out = set()
        for e in p.roads:
            for c in edge_corners(e):
                if c in self.board.corners and self.legal_corner(c):
                    out.add(c)
        return list(out)

    def road_candidates(self, p: _P) -> list[Edge]:
        ends = set()
        for e in p.roads:
            for c in edge_corners(e):
                if self.occupied.get(c, p.color) == p.color:
                    ends.add(c)
        ends |= p.settlements | p.cities
        out = set()
        for c in ends:
            for e in self.board.corner_edges(c):
                if e not in self.road_owner:
                    out.add(e)
        return list(out)

    def best_road(self, p: _P) -> Edge | None:
        cands = self.road_candidates(p)
        if not cands:
            return None
        noise = (1 - p.spec.skill) * 4

        def score(e: Edge) -> float:
            best = 0.0
            for c in edge_corners(e):
                if self.legal_corner(c):
                    best = max(best, self.corner_value(p, c))
                for n in self.board.corner_neighbors(c):
                    if self.legal_corner(n):
                        best = max(best, 0.7 * self.corner_value(p, n))
            return best + self.rng.gauss(0, noise)

        return max(cands, key=score)

    def longest_road_len(self, p: _P) -> int:
        adj: dict[Corner, list[tuple[Edge, Corner]]] = {}
        for e in p.roads:
            a, b = edge_corners(e)
            adj.setdefault(a, []).append((e, b))
            adj.setdefault(b, []).append((e, a))
        best = 0

        def dfs(c: Corner, used: set) -> int:
            owner = self.occupied.get(c)
            if used and owner is not None and owner != p.color:
                return 0
            m = 0
            for e, n in adj.get(c, []):
                if e not in used:
                    used.add(e)
                    m = max(m, 1 + dfs(n, used))
                    used.discard(e)
            return m

        for c in adj:
            best = max(best, dfs(c, set()))
        return best

    def update_awards(self) -> None:
        lens = {p.color: self.longest_road_len(p) for p in self.players}
        cur = self.longest_road
        cur_len = lens.get(cur, 0) if cur else 4
        for p in self.players:
            if lens[p.color] >= 5 and lens[p.color] > cur_len and p.color != cur:
                self.longest_road, cur_len = p.color, lens[p.color]
        if self.longest_road != cur and self.longest_road is not None:
            self.emit(t="award", player=self.longest_road, award="longest_road")
        cur = self.largest_army
        cur_k = next((p.knights for p in self.players if p.color == cur), 2)
        for p in self.players:
            if p.knights >= 3 and p.knights > cur_k and p.color != cur:
                self.largest_army, cur_k = p.color, p.knights
        if self.largest_army != cur and self.largest_army is not None:
            self.emit(t="award", player=self.largest_army, award="largest_army")

    def gain(self, p: _P, cards: Counter, source: str) -> None:
        cards = +cards
        if cards:
            p.hand.update(cards)
            self.emit(t="gain", player=p.color, cards=dict(cards), source=source)

    # ----- setup --------------------------------------------------------------
    def place_setup(self, p: _P, second: bool) -> None:
        legal = [c for c in self.board.corners if self.legal_corner(c)]
        noise = (1 - p.spec.skill) * 6
        c = max(legal, key=lambda c: self.corner_value(p, c, noise))
        self.occupied[c] = p.color
        p.settlements.add(c)
        self.emit(t="place", player=p.color, piece="settlement", loc=cid(c), setup=True)
        e = self.best_road_from(p, c)
        p.roads.add(e)
        self.road_owner[e] = p.color
        self.emit(t="place", player=p.color, piece="road", loc=cid(e), setup=True)
        if second:
            got = Counter(self.board.corner_resources(c))
            self.gain(p, got, "setup")

    def best_road_from(self, p: _P, c: Corner) -> Edge:
        cands = [e for e in self.board.corner_edges(c) if e not in self.road_owner]

        def score(e: Edge) -> float:
            a, b = edge_corners(e)
            other = b if a == c else a
            return max([self.corner_value(p, n) for n in self.board.corner_neighbors(other) if self.legal_corner(n)] or [0])

        return max(cands, key=score)

    # ----- turn ---------------------------------------------------------------
    def roll(self, p: _P) -> None:
        d1, d2 = self.rng.randint(1, 6), self.rng.randint(1, 6)
        total = d1 + d2
        self.emit(t="roll", player=p.color, dice=[d1, d2])
        if total == 7:
            for q in self.players:
                n = q.cards()
                if n > 7:
                    drop: Counter = Counter()
                    for _ in range(n // 2):
                        r = max(RESOURCES, key=lambda r: q.hand[r] - drop[r])
                        drop[r] += 1
                    q.hand.subtract(drop)
                    self.emit(t="discard", player=q.color, cards=dict(+drop))
            self.move_robber(p)
            return
        for q in self.players:
            got: Counter = Counter()
            for c in q.settlements | q.cities:
                mult = 2 if c in q.cities else 1
                for h in self.board.corner_hexes(c):
                    t = self.board.tiles[h]
                    if t.number == total and h != self.board.robber:
                        got[t.resource] += mult
            self.gain(q, got, "roll")

    def move_robber(self, p: _P) -> None:
        leader_vp = {q.color: self.vp(q) for q in self.players}

        def harm(h) -> float:
            from .board import pips

            t = self.board.tiles[h]
            if h == self.board.robber:
                return -99
            score = 0.0
            for c in [c for c in self.occupied if h in self.board.corner_hexes(c)]:
                owner = self.occupied[c]
                mult = 2 if any(c in q.cities for q in self.players if q.color == owner) else 1
                if owner == p.color:
                    score -= 10
                else:
                    score += pips(t.number) * mult * (1 + leader_vp[owner] / 5)
            return score + self.rng.gauss(0, (1 - p.spec.skill) * 6)

        h = max(self.board.tiles, key=harm)
        self.board.robber = h
        self.emit(t="robber", player=p.color, hex=cid(h))
        victims = {self.occupied[c] for c in self.occupied if h in self.board.corner_hexes(c)} - {p.color}
        victims = [q for q in self.players if q.color in victims and q.cards() > 0]
        if victims:
            v = max(victims, key=lambda q: (self.vp(q), q.cards()))
            card = self.rng.choice(list(v.hand.elements()))
            v.hand[card] -= 1
            p.hand[card] += 1
            self.emit(t="steal", thief=p.color, victim=v.color, card=card)

    def maybe_play_dev(self, p: _P) -> None:
        playable = [c for c in p.dev_hand if c not in p.dev_bought_this_turn or p.dev_bought_this_turn.count(c) < p.dev_hand.count(c)]
        if not playable:
            return
        on_me = any(self.board.robber in self.board.corner_hexes(c) for c in p.settlements | p.cities)
        if "knight" in playable and (on_me or p.knights >= 1 or self.rng.random() < 0.3 + 0.4 * p.spec.skill):
            p.dev_hand.remove("knight")
            p.knights += 1
            self.emit(t="play_dev", player=p.color, card="knight")
            self.move_robber(p)
            self.update_awards()
        elif "monopoly" in playable:
            r = max(RESOURCES, key=lambda r: sum(q.hand[r] for q in self.players if q is not p))
            total = 0
            for q in self.players:
                if q is not p and q.hand[r]:
                    n = q.hand[r]
                    q.hand[r] = 0
                    total += n
                    self.emit(t="lose", player=q.color, cards={r: n}, source="monopoly")
            p.dev_hand.remove("monopoly")
            self.emit(t="play_dev", player=p.color, card="monopoly")
            self.gain(p, Counter({r: total}), "monopoly")
        elif "year_of_plenty" in playable:
            p.dev_hand.remove("year_of_plenty")
            self.emit(t="play_dev", player=p.color, card="year_of_plenty")
            target = "city" if p.settlements else "settlement"
            need = Counter({r: max(0, n - p.hand[r]) for r, n in COSTS[target].items()})
            picks = list((+need).elements())[:2]
            while len(picks) < 2:
                picks.append(self.rng.choice(RESOURCES))
            self.gain(p, Counter(picks), "year_of_plenty")
        elif "road_building" in playable:
            p.dev_hand.remove("road_building")
            self.emit(t="play_dev", player=p.color, card="road_building")
            for _ in range(2):
                e = self.best_road(p)
                if e is None or len(p.roads) >= 15:
                    break
                p.roads.add(e)
                self.road_owner[e] = p.color
                self.emit(t="place", player=p.color, piece="road", loc=cid(e), setup=False, free=True)
            self.update_awards()

    def trade_ratio(self, p: _P, r: str) -> int:
        ports = {self.board.corner_port(c) for c in p.settlements | p.cities}
        return 2 if r in ports else 3 if "3:1" in ports else 4

    def try_bank_trade(self, p: _P, target: str) -> bool:
        traded = False
        for _ in range(2):
            need = +Counter({r: max(0, n - p.hand[r]) for r, n in COSTS[target].items()})
            if not need or sum(need.values()) > 2:
                return traded
            want = next(iter(need))
            spare = {r: p.hand[r] - COSTS[target].get(r, 0) for r in RESOURCES if r not in need}
            options = [r for r in spare if spare[r] >= self.trade_ratio(p, r)]
            if not options:
                return traded
            r = min(options, key=lambda r: (self.trade_ratio(p, r), -spare[r]))
            ratio = self.trade_ratio(p, r)
            p.hand[r] -= ratio
            p.hand[want] += 1
            self.emit(t="trade_bank", player=p.color, give={r: ratio}, get={want: 1})
            traded = True
        return traded

    def build_phase(self, p: _P) -> None:
        skill = p.spec.skill
        strat = p.spec.strategy
        for _ in range(12):
            if self.vp(p, hidden=True) >= self.vp_to_win:
                return
            # Low-skill players sometimes stall and sit on cards.
            if self.rng.random() > 0.7 + 0.3 * skill:
                return
            spots = self.reachable_corners(p)
            options: list[str] = []
            if p.settlements and len(p.cities) < 4:
                options.append("city")
            if spots and len(p.settlements) < 5:
                options.append("settlement")
            if self.deck:
                options.append("dev")
            if len(p.roads) < 15 and (not spots or self.rng.random() < 0.3):
                options.append("road")
            order = {
                "city_rush": ["city", "settlement", "dev", "road"],
                "expansion": ["settlement", "road", "city", "dev"],
                "dev_cards": ["dev", "city", "settlement", "road"],
                "balanced": ["city", "settlement", "road", "dev"],
            }[strat]
            options.sort(key=order.index)
            built = False
            for item in options:
                if not self.can_afford(p, item) and self.rng.random() < 0.2 + 0.7 * skill:
                    self.try_bank_trade(p, item)
                if not self.can_afford(p, item):
                    continue
                if item == "city":
                    c = max(p.settlements, key=lambda c: self.board.corner_pips(c))
                    self.pay(p, item)
                    p.settlements.discard(c)
                    p.cities.add(c)
                    self.emit(t="place", player=p.color, piece="city", loc=cid(c), setup=False)
                elif item == "settlement":
                    c = max(spots, key=lambda c: self.corner_value(p, c, (1 - skill) * 4))
                    self.pay(p, item)
                    self.occupied[c] = p.color
                    p.settlements.add(c)
                    self.emit(t="place", player=p.color, piece="settlement", loc=cid(c), setup=False)
                    self.update_awards()
                elif item == "road":
                    e = self.best_road(p)
                    if e is None:
                        continue
                    self.pay(p, item)
                    p.roads.add(e)
                    self.road_owner[e] = p.color
                    self.emit(t="place", player=p.color, piece="road", loc=cid(e), setup=False)
                    self.update_awards()
                elif item == "dev":
                    self.pay(p, item)
                    card = self.deck.pop()
                    p.dev_hand.append(card)
                    p.dev_bought_this_turn.append(card)
                    if card == "victory_point":
                        p.vp_cards += 1
                        p.dev_hand.remove(card)
                    self.emit(t="buy_dev", player=p.color)
                built = True
                break
            if not built:
                return

    def play(self) -> dict:
        order = self.players[:]
        for p in order:
            self.place_setup(p, second=False)
        for p in reversed(order):
            self.place_setup(p, second=True)
        winner = None
        while self.turn < self.max_turns and winner is None:
            for p in order:
                self.turn += 1
                p.dev_bought_this_turn = []
                if self.rng.random() < 0.5:
                    self.maybe_play_dev(p)
                self.roll(p)
                self.maybe_play_dev(p)
                self.build_phase(p)
                self.emit(t="end_turn", player=p.color)
                if self.vp(p, hidden=True) >= self.vp_to_win:
                    winner = p.color
                    break
        final = {p.color: self.vp(p, hidden=True) for p in self.players}
        if winner is None:
            winner = max(final, key=final.get)
        for p in self.players:
            if p.vp_cards:
                self.emit(t="reveal_vp", player=p.color, count=p.vp_cards)
        self.emit(t="game_end", player=winner)
        return {
            "board": self.initial_board,
            "players": [{"color": p.color, "name": p.spec.name, "strategy": p.spec.strategy} for p in self.players],
            "play_order": [p.color for p in order],
            "vp_to_win": self.vp_to_win,
            "events": self.events,
            "winner": winner,
            "final_vp": final,
        }


def simulate(specs: list[PlayerSpec], seed: int) -> dict:
    return Game(specs, seed).play()
