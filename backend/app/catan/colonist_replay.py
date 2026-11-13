"""Map a Colonist.io replay into the normalized event format consumed by ``analyze_game``.

The input is the JSON returned by Colonist's ``/api/replay/data-from-game-id`` (or
``data-from-slug``): ``eventHistory.initialState`` holds the full starting state and each
``eventHistory.events[i].stateChange`` is a partial state diff. Placements are read from
map-state diffs (they carry coordinates); everything else comes from the game-log
entries each diff appends (``gameLogState``).
"""

from __future__ import annotations

import copy
from typing import Any

from .board import RESOURCE_BY_ENUM, Board, Tile, cid

TILE_TYPES = {0: "desert", **RESOURCE_BY_ENUM}
PORT_TYPES = {1: "3:1", 2: "lumber", 3: "brick", 4: "wool", 5: "grain", 6: "ore"}
DEV_CARDS = {11: "knight", 12: "victory_point", 13: "monopoly", 14: "road_building", 15: "year_of_plenty"}
# Colonist color enum -> (name, the analyzer UI's color slot showing that color).
COLONIST_COLORS = {1: ("Red", 2), 2: ("Blue", 1), 3: ("Orange", 3), 4: ("White", 5), 5: ("Green", 6)}

LOG_DEV_BOUGHT = 1
LOG_SETUP_PLACE = 4
LOG_BUILD = 5
LOG_ROLL = 10
LOG_ROBBER = 11
LOG_STOLEN_FROM = 14
LOG_STOLE = (15, 139)
LOG_DEV_PLAYED = 20
LOG_YEAR_OF_PLENTY = 21
LOG_GOT_RESOURCES = 47
LOG_DISCARD = 55
LOG_LONGEST_ROAD = 66
LOG_LONGEST_ROAD_CHANGED = 68
LOG_MONOPOLY = 86
LOG_BANK_TRADE = 116
PIECES = {0: "road", 2: "settlement", 3: "city"}


class ReplayError(ValueError):
    pass


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _cards(enums: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in enums or []:
        r = RESOURCE_BY_ENUM.get(_int(c) or 0)
        if r:
            out[r] = out.get(r, 0) + 1
    return out


def _sorted_items(d: Any) -> list[tuple[Any, Any]]:
    if isinstance(d, list):
        return list(enumerate(d))
    if not isinstance(d, dict):
        return []
    return sorted(d.items(), key=lambda kv: (_int(kv[0]) is None, _int(kv[0]) or 0, str(kv[0])))


def unwrap(replay: Any) -> dict:
    """Accept the API response (``{"data": {...}}``) or its ``data`` object."""
    if isinstance(replay, dict) and isinstance(replay.get("data"), dict):
        replay = replay["data"]
    if not isinstance(replay, dict) or not isinstance(replay.get("eventHistory"), dict):
        raise ReplayError("This doesn't look like a Colonist.io replay (no eventHistory).")
    return replay


def _board(map_state: dict, robber_idx: int | None) -> Board:
    tiles: dict[tuple[int, int], Tile] = {}
    robber = None
    for idx, t in _sorted_items(map_state.get("tileHexStates")):
        res = TILE_TYPES.get(_int(t.get("type")))
        x, y = _int(t.get("x")), _int(t.get("y"))
        if res is None or x is None or y is None:
            continue
        n = _int(t.get("diceNumber"))
        tiles[(x, y)] = Tile(res, n if n and res != "desert" else None)
        if robber_idx is not None and _int(idx) == robber_idx:
            robber = (x, y)
    if not tiles:
        raise ReplayError("The replay has no board (mapState.tileHexStates is empty).")
    ports = {}
    for _, p in _sorted_items(map_state.get("portEdgeStates")):
        kind = PORT_TYPES.get(_int(p.get("type")))
        loc = tuple(_int(p.get(k)) for k in ("x", "y", "z"))
        if kind and None not in loc:
            ports[loc] = kind
    return Board(tiles=tiles, ports=ports, robber=robber)  # type: ignore[arg-type]


def _hex_at(map_state: dict, idx: int | None) -> str | None:
    t = (map_state.get("tileHexStates") or {}).get(str(idx)) if idx is not None else None
    if t is None and isinstance(map_state.get("tileHexStates"), list) and idx is not None:
        hexes = map_state["tileHexStates"]
        t = hexes[idx] if 0 <= idx < len(hexes) else None
    return cid((_int(t["x"]), _int(t["y"]))) if t else None  # type: ignore[arg-type]


def _winner(eh: dict, vps: dict[int, int]) -> int | None:
    """The winner from endGameState when it names one, else the leader on visible VP."""
    end = eh.get("endGameState")
    stack = [end] if isinstance(end, dict) else []
    while stack:
        node = stack.pop()
        for k, v in node.items():
            if isinstance(v, dict):
                color = _int(v.get("color", v.get("playerColor", k)))
                if color in vps and (v.get("winningPlayer") is True or v.get("isWinner") is True or _int(v.get("rank")) == 1):
                    return color
                stack.append(v)
        color = _int(node.get("winningPlayerColor", node.get("winnerColor")))
        if color in vps:
            return color
    return max(vps, key=lambda c: vps[c]) if vps else None


def _final_vp(eh: dict, visible: dict[int, int]) -> dict[int, int]:
    """Per-player final VP when endGameState lists it (it reveals hidden VP cards)."""
    out: dict[int, int] = {}
    end = eh.get("endGameState")
    stack = [end] if isinstance(end, dict) else []
    while stack:
        node = stack.pop()
        for k, v in node.items():
            if isinstance(v, dict):
                color = _int(v.get("color", v.get("playerColor", k)))
                n = _int(v.get("victoryPoints", v.get("totalVictoryPoints")))
                if color in visible and n is not None:
                    out[color] = n
                else:
                    stack.append(v)
    return out


def replay_to_game(replay: Any) -> dict:
    data = unwrap(replay)
    eh = data["eventHistory"]
    state = copy.deepcopy(eh.get("initialState") or {})
    map_state = state.get("mapState") or {}
    robber_idx = _int((state.get("mechanicRobberState") or {}).get("locationTileIndex"))
    board = _board(map_state, robber_idx)

    users = [u for u in data.get("playerUserStates") or [] if _int(u.get("selectedColor")) is not None]
    order = [c for c in (_int(c) for c in data.get("playOrder") or []) if c is not None]
    raw_colors = list(dict.fromkeys(order + [_int(u["selectedColor"]) for u in users]))
    if len(raw_colors) < 2:
        raise ReplayError("The replay doesn't list its players.")
    used = {slot for _, slot in COLONIST_COLORS.values()}
    spare = iter(c for c in range(1, 12) if c not in used)
    slot = {c: COLONIST_COLORS[c][1] if c in COLONIST_COLORS else next(spare) for c in raw_colors}
    names = {_int(u["selectedColor"]): str(u.get("username") or "") for u in users}
    for c in raw_colors:
        names[c] = names.get(c) or (data.get("botUserNames") or {}).get(str(c)) or f"{COLONIST_COLORS.get(c, ('Player',))[0]} bot"

    events: list[dict] = []
    turn = 0
    turn_player: int | None = None
    rolled = False
    pending: int | None = None
    free_roads = 0
    stole_since_robber = True
    knights: dict[int, int] = {}
    army: int | None = None
    vp = dict.fromkeys(raw_colors, 0)

    def emit(t: str, **ev: Any) -> None:
        if pending is not None and t not in ("reveal_vp", "game_end"):
            new_turn(pending)
        for k in ("player", "thief", "victim"):
            if k in ev:
                ev[k] = slot[ev[k]]
        events.append({"t": t, "turn": turn, **ev})

    def new_turn(player: int | None) -> None:
        nonlocal turn, turn_player, rolled, pending
        turn += 1
        turn_player, rolled, pending = player, False, None

    placed: list[tuple[int, str, str]] = []
    robber_hex: str | None = None

    def place(owner: int, piece: str, loc: str) -> None:
        nonlocal free_roads
        setup = turn == 0
        free = piece == "road" and not setup and free_roads > 0
        if free:
            free_roads -= 1
        vp[owner] += {"settlement": 1, "city": 1}.get(piece, 0)
        emit("place", player=owner, piece=piece, loc=loc, setup=setup, **({"free": True} if free else {}))

    def take_placement(player: int | None, piece: str | None) -> None:
        for i, (o, p, loc) in enumerate(placed):
            if (player is None or o == player) and (piece is None or p == piece):
                placed.pop(i)
                place(o, p, loc)
                return

    def move_robber(player: int | None) -> None:
        nonlocal robber_hex, stole_since_robber
        if robber_hex is not None and (player or turn_player) in slot:
            emit("robber", player=player or turn_player, hex=robber_hex)
            robber_hex, stole_since_robber = None, False

    for raw in eh.get("events") or []:
        sc = raw.get("stateChange") if isinstance(raw, dict) else None
        if not isinstance(sc, dict):
            continue
        cur = sc.get("currentState") or {}
        ctp = _int(cur.get("currentTurnPlayerColor"))
        if turn > 0 and ctp in slot and ctp != (pending or turn_player):
            pending = ctp
        elif turn == 0 and ctp in slot:
            turn_player = ctp

        placed.clear()
        ms = sc.get("mapState") or {}
        corners = map_state.setdefault("tileCornerStates", {})
        for k, diff in _sorted_items(ms.get("tileCornerStates")):
            before = dict(corners.get(str(k)) or corners.get(k) or {})
            after = {**before, **(diff or {})}
            bt, owner = _int(after.get("buildingType")), _int(after.get("owner"))
            if owner in slot and bt in (1, 2) and bt != _int(before.get("buildingType")):
                loc = tuple(_int(after.get(a)) for a in ("x", "y", "z"))
                if None not in loc:
                    placed.append((owner, "settlement" if bt == 1 else "city", cid(loc)))  # type: ignore[arg-type]
        edges = map_state.setdefault("tileEdgeStates", {})
        for k, diff in _sorted_items(ms.get("tileEdgeStates")):
            before = dict(edges.get(str(k)) or edges.get(k) or {})
            after = {**before, **(diff or {})}
            owner = _int(after.get("owner"))
            if owner in slot and _int(after.get("type")) == 1 and _int(before.get("owner")) != owner:
                loc = tuple(_int(after.get(a)) for a in ("x", "y", "z"))
                if None not in loc:
                    placed.append((owner, "road", cid(loc)))  # type: ignore[arg-type]
        new_robber = _int((sc.get("mechanicRobberState") or {}).get("locationTileIndex"))
        robber_hex = _hex_at(map_state, new_robber) if new_robber is not None and new_robber != robber_idx else None
        if new_robber is not None:
            robber_idx = new_robber

        for _, entry in _sorted_items(sc.get("gameLogState")):
            if not isinstance(entry, dict) or not isinstance(entry.get("text"), dict):
                continue
            text = entry["text"]
            kind, player = _int(text.get("type")), _int(text.get("playerColor"))
            if kind in (LOG_SETUP_PLACE, LOG_BUILD):
                take_placement(player, PIECES.get(_int(text.get("pieceEnum")) or -1))
            elif kind == LOG_ROLL and player in slot:
                d1, d2 = _int(text.get("firstDice")), _int(text.get("secondDice"))
                if d1 is None or d2 is None:
                    continue
                if pending is not None or turn == 0 or player != turn_player or rolled:
                    new_turn(player)
                rolled = True
                emit("roll", player=player, dice=[d1, d2])
            elif kind == LOG_GOT_RESOURCES and player in slot:
                cards = _cards(text.get("cardsToBroadcast"))
                if cards:
                    src = "setup" if _int(text.get("distributionType")) == 0 else "roll"
                    emit("gain", player=player, cards=cards, source=src)
            elif kind == LOG_ROBBER:
                move_robber(player)
            elif kind == LOG_STOLEN_FROM or kind in LOG_STOLE:
                thief = _int(entry.get("from"))
                if kind == LOG_STOLEN_FROM:
                    victim = player
                else:
                    rec = entry.get("specificRecipients") or []
                    victim = _int(rec[0]) if rec else None
                move_robber(thief)
                if thief in slot and victim in slot and thief != victim and not stole_since_robber:
                    stole_since_robber = True
                    cards = _cards(text.get("cardEnums"))
                    emit("steal", thief=thief, victim=victim, **({"card": next(iter(cards))} if cards else {}))
            elif kind == LOG_DEV_PLAYED and player in slot:
                card = DEV_CARDS.get(_int(text.get("cardEnum")) or 0)
                if card is None or card == "victory_point":
                    continue
                emit("play_dev", player=player, card=card)
                if card == "road_building":
                    free_roads = 2
                if card == "knight":
                    knights[player] = knights.get(player, 0) + 1
                    if knights[player] >= 3 and army != player and knights[player] > knights.get(army, 0):  # type: ignore[arg-type]
                        army = player
                        emit("award", player=player, award="largest_army")
            elif kind == LOG_YEAR_OF_PLENTY and player in slot:
                emit("gain", player=player, cards=_cards(text.get("cardEnums")), source="year_of_plenty")
            elif kind == LOG_MONOPOLY and player in slot:
                res = RESOURCE_BY_ENUM.get(_int(text.get("cardEnum")) or 0)
                n = _int(text.get("amountStolen")) or 0
                if res and n:
                    emit("gain", player=player, cards={res: n}, source="monopoly")
            elif kind == LOG_DEV_BOUGHT and player in slot:
                emit("buy_dev", player=player)
            elif kind == LOG_BANK_TRADE and player in slot:
                give, get = _cards(text.get("givenCardEnums")), _cards(text.get("receivedCardEnums"))
                if give and get:
                    emit("trade_bank", player=player, give=give, get=get)
            elif kind == LOG_DISCARD and player in slot:
                cards = _cards(text.get("cardEnums"))
                if cards:
                    emit("discard", player=player, cards=cards)
            elif kind in (LOG_LONGEST_ROAD, LOG_LONGEST_ROAD_CHANGED):
                to = _int(text.get("playerColorNew")) if kind == LOG_LONGEST_ROAD_CHANGED else player
                if to in slot:
                    emit("award", player=to, award="longest_road")
        for owner, piece, loc in placed:
            place(owner, piece, loc)
        move_robber(None)
        _merge(state, {k: v for k, v in sc.items() if k != "gameLogState"})
        map_state = state.get("mapState") or map_state

    if not any(e["t"] == "roll" for e in events):
        raise ReplayError("The replay has no dice rolls, so there is nothing to analyze yet.")

    holders: dict[str, int] = {}
    for e in events:
        if e["t"] == "award":
            holders[e["award"]] = e["player"]
    by_slot = {slot[c]: c for c in raw_colors}
    visible = {c: vp[c] + 2 * sum(1 for h in holders.values() if h == slot[c]) for c in raw_colors}
    winner = _winner(eh, visible)
    vp_to_win = _int((data.get("gameSettings") or {}).get("victoryPointsToWin")) or 10
    final = _final_vp(eh, visible)
    if winner is not None and winner not in final and visible[winner] < vp_to_win:
        final[winner] = vp_to_win
    for c in raw_colors:
        hidden = final.get(c, 0) - visible[c]
        if 0 < hidden <= 5:
            emit("reveal_vp", player=c, count=hidden)
    if winner is not None:
        emit("game_end", player=winner)
    perspective = _int(data.get("playerPerspective"))
    return {
        "id": str(data.get("databaseGameId") or data.get("gameId") or ""),
        "board": board.to_dict(),
        "players": [{"color": slot[c], "name": names[c]} for c in raw_colors],
        "play_order": [slot[c] for c in raw_colors],
        "vp_to_win": vp_to_win,
        "events": events,
        "winner": slot[winner] if winner is not None else None,
        "focus": slot[perspective] if perspective in slot else slot[raw_colors[0]],
        "color_names": {str(slot[c]): COLONIST_COLORS.get(c, ("Player",))[0] for c in raw_colors},
        "colonist_colors": {str(s): c for s, c in by_slot.items()},
        "start_time": eh.get("startTime"),
    }
