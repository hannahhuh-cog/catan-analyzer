"""Catan board geometry using Colonist.io's coordinate system.

Hexes are axial (x, y). Corners are (x, y, z) with z in {0, 1}; edges are
(x, y, z) with z in {0, 1, 2}. The adjacency formulas below were verified
against a real Colonist.io map state.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

RESOURCES = ("lumber", "brick", "wool", "grain", "ore")
RESOURCE_BY_ENUM = {1: "lumber", 2: "brick", 3: "wool", 4: "grain", 5: "ore"}
ENUM_BY_RESOURCE = {v: k for k, v in RESOURCE_BY_ENUM.items()}

Hex = tuple[int, int]
Corner = tuple[int, int, int]
Edge = tuple[int, int, int]

STANDARD_TILES = ["lumber"] * 4 + ["wool"] * 4 + ["grain"] * 4 + ["brick"] * 3 + ["ore"] * 3 + ["desert"]
STANDARD_NUMBERS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
STANDARD_PORTS = ["3:1"] * 4 + list(RESOURCES)


def pips(number: int | None) -> int:
    if not number or number == 7:
        return 0
    return 6 - abs(7 - number)


def corner_hexes_all(c: Corner) -> list[Hex]:
    x, y, z = c
    if z == 0:
        return [(x, y), (x, y - 1), (x + 1, y - 1)]
    return [(x, y), (x, y + 1), (x - 1, y + 1)]


def hex_corners(h: Hex) -> list[Corner]:
    x, y = h
    return [(x, y, 0), (x, y + 1, 0), (x - 1, y + 1, 0), (x, y, 1), (x, y - 1, 1), (x + 1, y - 1, 1)]


def edge_corners(e: Edge) -> tuple[Corner, Corner]:
    x, y, z = e
    if z == 0:
        return (x, y - 1, 1), (x, y, 0)
    if z == 1:
        return (x - 1, y + 1, 0), (x, y - 1, 1)
    return (x - 1, y + 1, 0), (x, y, 1)


def hex_center(h: Hex) -> tuple[float, float]:
    x, y = h
    return math.sqrt(3) * (x + y / 2), 1.5 * y


def corner_point(c: Corner) -> tuple[float, float]:
    pts = [hex_center(h) for h in corner_hexes_all(c)]
    return sum(p[0] for p in pts) / 3, sum(p[1] for p in pts) / 3


def cid(loc: tuple[int, ...]) -> str:
    return ",".join(str(v) for v in loc)


def parse_id(s: str) -> tuple[int, ...]:
    return tuple(int(v) for v in s.split(","))


@dataclass
class Tile:
    resource: str  # one of RESOURCES or "desert"/"sea"
    number: int | None


@dataclass
class Board:
    tiles: dict[Hex, Tile]
    ports: dict[Edge, str] = field(default_factory=dict)
    robber: Hex | None = None

    def __post_init__(self) -> None:
        land = set(self.tiles)
        self.corners: set[Corner] = {c for h in land for c in hex_corners(h)}
        self._corner_hexes = {c: [h for h in corner_hexes_all(c) if h in land] for c in self.corners}
        self.edges: set[Edge] = set()
        self._corner_edges: dict[Corner, list[Edge]] = {c: [] for c in self.corners}
        for c in self.corners:
            x, y, _ = c
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for z in (0, 1, 2):
                        e = (x + dx, y + dy, z)
                        if e in self.edges:
                            continue
                        a, b = edge_corners(e)
                        if a in self.corners and b in self.corners:
                            self.edges.add(e)
                            self._corner_edges[a].append(e)
                            self._corner_edges[b].append(e)
        self._corner_port: dict[Corner, str] = {}
        for e, kind in self.ports.items():
            for c in edge_corners(e):
                if c in self.corners:
                    self._corner_port[c] = kind
        if self.robber is None:
            self.robber = next((h for h, t in self.tiles.items() if t.resource == "desert"), None)

    def corner_hexes(self, c: Corner) -> list[Hex]:
        return self._corner_hexes.get(c, [])

    def corner_edges(self, c: Corner) -> list[Edge]:
        return self._corner_edges.get(c, [])

    def corner_neighbors(self, c: Corner) -> list[Corner]:
        out = []
        for e in self.corner_edges(c):
            a, b = edge_corners(e)
            out.append(b if a == c else a)
        return out

    def corner_port(self, c: Corner) -> str | None:
        return self._corner_port.get(c)

    def corner_pips(self, c: Corner) -> int:
        return sum(pips(self.tiles[h].number) for h in self.corner_hexes(c))

    def corner_resources(self, c: Corner) -> list[str]:
        return [self.tiles[h].resource for h in self.corner_hexes(c) if self.tiles[h].resource in RESOURCES]

    def coastal_edges(self) -> list[Edge]:
        out = []
        for e in self.edges:
            a, b = edge_corners(e)
            if len(set(self.corner_hexes(a)) & set(self.corner_hexes(b))) == 1:
                out.append(e)
        return out

    def to_dict(self) -> dict:
        return {
            "tiles": [
                {"id": cid(h), "resource": t.resource, "number": t.number, "center": hex_center(h)} for h, t in sorted(self.tiles.items())
            ],
            "corners": [{"id": cid(c), "point": corner_point(c)} for c in sorted(self.corners)],
            "edges": [{"id": cid(e), "a": cid(edge_corners(e)[0]), "b": cid(edge_corners(e)[1])} for e in sorted(self.edges)],
            "ports": [{"edge": cid(e), "kind": k} for e, k in sorted(self.ports.items())],
            "robber": cid(self.robber) if self.robber else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Board:
        tiles = {parse_id(t["id"]): Tile(t["resource"], t["number"]) for t in d["tiles"]}  # type: ignore[misc]
        ports = {parse_id(p["edge"]): p["kind"] for p in d.get("ports", [])}  # type: ignore[misc]
        robber = parse_id(d["robber"]) if d.get("robber") else None
        return cls(tiles=tiles, ports=ports, robber=robber)  # type: ignore[arg-type]


def standard_hexes() -> list[Hex]:
    return [(x, y) for x in range(-2, 3) for y in range(-2, 3) if abs(x + y) <= 2]


def random_board(rng: random.Random) -> Board:
    hexes = standard_hexes()
    while True:
        res = STANDARD_TILES[:]
        rng.shuffle(res)
        nums = STANDARD_NUMBERS[:]
        rng.shuffle(nums)
        tiles: dict[Hex, Tile] = {}
        it = iter(nums)
        for h, r in zip(hexes, res):
            tiles[h] = Tile(r, None if r == "desert" else next(it))
        if not _hot_numbers_adjacent(tiles):
            break
    board = Board(tiles=tiles)
    coast = sorted(board.coastal_edges(), key=lambda e: math.atan2(*_edge_mid(e)[::-1]))
    kinds = STANDARD_PORTS[:]
    rng.shuffle(kinds)
    offset = rng.randrange(len(coast))
    chosen = [coast[(offset + round(i * len(coast) / 9)) % len(coast)] for i in range(9)]
    return Board(tiles=tiles, ports=dict(zip(chosen, kinds)))


def _edge_mid(e: Edge) -> tuple[float, float]:
    a, b = (corner_point(c) for c in edge_corners(e))
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def _hot_numbers_adjacent(tiles: dict[Hex, Tile]) -> bool:
    hot = {h for h, t in tiles.items() if t.number in (6, 8)}
    for x, y in hot:
        for dx, dy in ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)):
            if (x + dx, y + dy) in hot:
                return True
    return False
