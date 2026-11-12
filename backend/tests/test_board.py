import random
from collections import Counter

from app.catan.board import Board, pips, random_board


def test_pips():
    assert [pips(n) for n in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)] == [1, 2, 3, 4, 5, 0, 5, 4, 3, 2, 1]
    assert pips(None) == 0


def test_standard_board_topology():
    b = random_board(random.Random(1))
    assert len(b.tiles) == 19
    assert len(b.corners) == 54
    assert len(b.edges) == 72
    assert len(b.coastal_edges()) == 30
    assert len(b.ports) == 9
    assert Counter(len(b.corner_edges(c)) for c in b.corners) == {3: 36, 2: 18}
    assert b.tiles[b.robber].resource == "desert"


def test_no_adjacent_six_eight():
    for seed in range(20):
        b = random_board(random.Random(seed))
        hot = {h for h, t in b.tiles.items() if t.number in (6, 8)}
        for c in b.corners:
            assert len(hot & set(b.corner_hexes(c))) <= 1


def test_round_trip():
    b = random_board(random.Random(3))
    b2 = Board.from_dict(b.to_dict())
    assert b2.tiles == b.tiles and b2.ports == b.ports and b2.robber == b.robber
