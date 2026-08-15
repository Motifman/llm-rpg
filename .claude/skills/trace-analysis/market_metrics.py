#!/usr/bin/env python3
"""市場 run の分析軸 (G-41〜G-48) を trace から抽出する。

`extract_metrics.py` の市場セクション。**すべての軸に分母を持たせる**のがこの
モジュールの設計方針で、値そのものより優先する。

理由は実際に踏んだから。v3 run で「交差 0 件」と数えて **「誰も裁定に気づか
なかった」と読みかけた**。実際は売り注文と買い注文が同時に板に並んだ瞬間が
一度も無く、**気づく対象が現れなかった**だけだった。分子だけ見るとこの 2 つは
区別がつかない。

なので各軸は「何回起きたか」ではなく「**起こりうる状況が何度あって、そのうち
何回起きたか**」を返す。分母が 0 の軸は ``measurable: False`` を立てる。
0 という数字を「起きなかった」と読ませないため。

軸の一覧は SKILL.md の G 節を参照。gold に依存する G-45 / G-46 はここには
無い — 板を通った gold が trace の所持金記録に残らないため (production 側を
直してから足す)。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

MARKET_TOOLS = frozenset({
    "market_list_item", "market_bid", "market_buy", "market_sell",
    "market_reprice", "market_cancel",
})
"""板を触るツール。G-48 の「呼ばれなかったツール」を絞り込むのに使う。"""

FACE_TO_FACE_TOOLS = frozenset({
    "give_item", "trade_offer", "trade_accept", "trade_decline",
})
"""相手と同席して品を動かす経路。G-47 で板と比べる。"""

_ORDER_APPEARS = ("board_snapshot", "listed")
"""注文が板に現れる出来事。

**両方を見る。** `board_snapshot` は run 開始時の板、`listed` はそのあとの出品で、
片方だけだと初期注文が丸ごと欠ける (PR #1189 で塞いだ穴)。
"""

_ORDER_DISAPPEARS = ("cancelled", "expired")


@dataclass(frozen=True)
class BoardOrder:
    """板に出ている注文 1 件 (trace から再現したもの)。"""

    order_id: int
    item: str
    side: str
    unit_price: int
    quantity: int
    owner: Optional[str]


Board = Dict[int, BoardOrder]


def replay_board(events: Iterable[dict]) -> List[Tuple[Optional[int], Board]]:
    """`market_activity` を順に当てて、各時点の板を再現する。

    返すのは ``(tick, その出来事のあとの板)`` の並び。**実装の板そのものでは
    なく再現**なので、ずれれば数字が静かに嘘になる。既知の並びに対する
    自己点検を ``tests/skills/trace_analysis/test_market_metrics.py`` に
    固定してある。
    """
    orders: Board = {}
    states: List[Tuple[Optional[int], Board]] = []
    for event in events:
        if event.get("kind") != "market_activity":
            continue
        payload = event.get("payload") or {}
        orders = _apply(orders, payload)
        states.append((event.get("tick"), dict(orders)))
    return states


def _apply(orders: Board, payload: dict) -> Board:
    """板に出来事を 1 つ当てて、**新しい板を返す** (元は変えない)。"""
    event = payload.get("market_event")
    order_id = payload.get("order_id")
    if event in _ORDER_APPEARS and order_id is not None:
        return {**orders, order_id: BoardOrder(
            order_id=order_id,
            item=payload.get("item_name"),
            side=payload.get("side"),
            unit_price=payload.get("unit_price"),
            quantity=payload.get("quantity") or 0,
            owner=payload.get("actor_name"),
        )}
    if event == "repriced" and order_id in orders:
        return {**orders, order_id: replace(
            orders[order_id], unit_price=payload.get("unit_price")
        )}
    if event in _ORDER_DISAPPEARS and order_id in orders:
        return {k: v for k, v in orders.items() if k != order_id}
    if event == "settled":
        return _apply_settlement(orders, payload)
    return orders


def _apply_settlement(orders: Board, payload: dict) -> Board:
    """約定したぶんだけ、板に残っている注文の数量を減らす。

    `settled` は `order_id` ではなく **`resting_order_id`** を持つ (取った側の
    注文は板に置かれないため)。ここを取り違えると約定が 1 件も当たらず、
    板が減らないまま残る。
    """
    resting = payload.get("resting_order_id")
    if resting not in orders:
        return orders
    remaining = orders[resting].quantity - (payload.get("quantity") or 0)
    if remaining <= 0:
        return {k: v for k, v in orders.items() if k != resting}
    return {**orders, resting: replace(orders[resting], quantity=remaining)}


def _best_by_side(board: Board, item: str) -> Tuple[Optional[int], Optional[int]]:
    """その品の (売り最安, 買い最高)。

    **売りと買いを混ぜない。** 混ぜると「6G の薬草と 24G のパン」が同じ線に
    乗って無意味になる。再現器の自己点検で実際にここを混ぜていた。
    """
    asks = [o.unit_price for o in board.values()
            if o.item == item and o.side == "sell" and o.unit_price is not None]
    bids = [o.unit_price for o in board.values()
            if o.item == item and o.side == "buy" and o.unit_price is not None]
    return (min(asks) if asks else None, max(bids) if bids else None)


def _price_series(states: List[Tuple[Optional[int], Board]]) -> Dict[str, Any]:
    """G-41: 品ごと・向きごとの最良値の推移。値が変わった時点だけ残す。"""
    series: Dict[str, Dict[str, List[List[Any]]]] = defaultdict(
        lambda: {"sell": [], "buy": []}
    )
    for tick, board in states:
        for item in {o.item for o in board.values()}:
            ask, bid = _best_by_side(board, item)
            for side, price in (("sell", ask), ("buy", bid)):
                if price is None:
                    continue
                points = series[item][side]
                if points and points[-1][1] == price:
                    continue
                points.append([tick, price])
    return {item: sides for item, sides in series.items()}


def _repricing(events: Iterable[dict]) -> List[dict]:
    """G-42: 値を動かした主体と、その前後の値。"""
    out: List[dict] = []
    for event in events:
        if event.get("kind") != "market_activity":
            continue
        payload = event.get("payload") or {}
        if payload.get("market_event") != "repriced":
            continue
        out.append({
            "tick": event.get("tick"),
            "actor": payload.get("actor_name"),
            "item": payload.get("item_name"),
            "side": payload.get("side"),
            "from": payload.get("old_unit_price"),
            "to": payload.get("unit_price"),
        })
    return out


ITEM_MOVING_TOOLS = MARKET_TOOLS | FACE_TO_FACE_TOOLS | frozenset({
    "buy_item", "sell_item", "pickup_item", "drop_item", "use_item",
})
"""品が動くツール。G-43 の分母 (世界で扱われた品) を作るのに使う。"""


def _requested_items(events: Iterable[dict]) -> Dict[Tuple[Any, Any], set]:
    """`action` の引数から、その呼び出しが触ろうとした品名を拾う。

    **`action_result` に `item_name` を入れているのは市場ツールだけ**だった。
    対面の品名はここからしか取れない。合成 trace で書いたテストは全部緑
    だったのに、実 run に当てたら G-43 も G-47 も空振りしていた。
    """
    out: Dict[Tuple[Any, Any], set] = defaultdict(set)
    for event in events:
        if event.get("kind") != "action":
            continue
        payload = event.get("payload") or {}
        args = payload.get("arguments") or {}
        labels = set()
        if args.get("item_label"):
            labels.add(args["item_label"])
        # まとめ渡し (`give_item`) は 1 件目だけ見ると残りが静かに落ちる。
        for gift in args.get("gives") or []:
            if isinstance(gift, dict) and gift.get("item_label"):
                labels.add(gift["item_label"])
        if labels:
            out[(event.get("tick"), event.get("player_id"))] |= labels
    return out


def _items_of(payload: dict, key: Tuple[Any, Any],
              requested: Dict[Tuple[Any, Any], set]) -> set:
    """その呼び出しが扱った品名。結果に無ければ、要求した引数から補う。"""
    if payload.get("item_name"):
        return {payload["item_name"]}
    return set(requested.get(key, ()))


def _item_coverage(events: Iterable[dict],
                   states: List[Tuple[Optional[int], Board]]) -> Dict[str, Any]:
    """G-43: 板が仲介した品と、しなかった品。

    **分母は「その run で誰かが実際に扱った品」**。ここから板に載った品を
    引いた差が、板が素通りされた品になる。

    品名が取れなかった呼び出しは件数として残す。**静かに落とすと「板が全部
    仲介した」ように見える。**
    """
    requested = _requested_items(events)
    in_world: set = set()
    unresolved = 0
    for event in events:
        if event.get("kind") != "action_result":
            continue
        payload = event.get("payload") or {}
        if payload.get("tool") not in ITEM_MOVING_TOOLS:
            continue
        items = _items_of(payload, (event.get("tick"), event.get("player_id")),
                          requested)
        if items:
            in_world |= items
        else:
            unresolved += 1
    on_board = {order.item for _, board in states for order in board.values()}
    in_world |= on_board
    return {
        "seen_in_world": sorted(x for x in in_world if x),
        "on_board": sorted(x for x in on_board if x),
        "never_on_board": sorted(x for x in in_world - on_board if x),
        "unresolved_item_calls": unresolved,
    }


def _crossing(states: List[Tuple[Optional[int], Board]]) -> Dict[str, Any]:
    """G-44: 交差の機会 (分母) と、実際の交差。

    交差 = 買い注文の値 >= 売り注文の値。engine は交差を潰さない設計なので、
    **交差が残っていることは欠陥ではなく、裁定に気づけるかの観測点**になる。

    機会がゼロなら ``measurable: False``。「交差 0 件」とだけ書くと、次に
    読む人が必ず「誰も気づかなかった」と読む。
    """
    opportunity_ticks = set()
    crossings: List[dict] = []
    seen: set = set()
    for tick, board in states:
        for item in {o.item for o in board.values()}:
            pairs = _cross_pairs(board, item)
            if not pairs:
                continue
            opportunity_ticks.add(tick)
            ask, bid = min(a for a, _ in pairs), max(b for _, b in pairs)
            if bid < ask:
                continue
            key = (item, ask, bid)
            if key in seen:
                continue
            seen.add(key)
            crossings.append({"tick": tick, "item": item, "ask": ask,
                              "bid": bid, "gap": bid - ask})
    return {
        "measurable": bool(opportunity_ticks),
        "opportunity_ticks": len(opportunity_ticks),
        "crossings": crossings,
        "note": ("売り注文と買い注文が同じ品に同時に並んだ瞬間が無いので、"
                 "裁定に気づけるかについては何も言えない"
                 if not opportunity_ticks else ""),
    }


def _cross_pairs(board: Board, item: str) -> List[Tuple[int, int]]:
    """その品の (売り値, 買い値) の組。**持ち主が同じ組は除く**。

    自分の注文は自分で取れないので、1 人が両側を出しただけで「裁定機会が
    あった」と数えてはいけない。
    """
    asks = [o for o in board.values()
            if o.item == item and o.side == "sell" and o.unit_price is not None]
    bids = [o for o in board.values()
            if o.item == item and o.side == "buy" and o.unit_price is not None]
    return [
        (ask.unit_price, bid.unit_price)
        for ask in asks for bid in bids
        if ask.owner != bid.owner
    ]


def _route_choice(events: List[dict],
                  states: List[Tuple[Optional[int], Board]]) -> Dict[str, Any]:
    """G-47: 板を選んだか、対面を選んだか。

    **分母は「両方選べた場面」**。板が空なら対面を選ぶのは当たり前で、選好の
    証拠にならない。同じ品が板に出ていたあいだの対面だけを数える。
    """
    requested = _requested_items(events)
    market_calls: Counter = Counter()
    face_calls: Counter = Counter()
    contested = 0
    unresolved = 0
    for event in events:
        if event.get("kind") != "action_result":
            continue
        payload = event.get("payload") or {}
        tool = payload.get("tool")
        if tool in MARKET_TOOLS:
            market_calls[tool] += 1
        elif tool in FACE_TO_FACE_TOOLS:
            face_calls[tool] += 1
            key = (event.get("tick"), event.get("player_id"))
            items = _items_of(payload, key, requested)
            if not items:
                unresolved += 1
            elif any(_was_on_board(states, event.get("tick"), item)
                     for item in items):
                contested += 1
    return {
        "market_calls": sum(market_calls.values()),
        "market_by_tool": dict(market_calls),
        "face_to_face_calls": sum(face_calls.values()),
        "face_to_face_by_tool": dict(face_calls),
        "face_to_face_while_on_board": contested,
        "unresolved_item_calls": unresolved,
    }


def _was_on_board(states: List[Tuple[Optional[int], Board]],
                  tick: Optional[int], item: Optional[str]) -> bool:
    """その手番の時点で、その品が板に出ていたか。"""
    if item is None or tick is None:
        return False
    board: Board = {}
    for state_tick, state in states:
        if state_tick is not None and state_tick > tick:
            break
        board = state
    return any(order.item == item for order in board.values())


def _tool_exposure(events: Iterable[dict]) -> Dict[str, Any]:
    """G-48: 出ていたのに呼ばれなかった市場ツール。

    **0 回のツールは失敗分布に一行も出ない** — 失敗していないので。既存の
    error_code 軸では構造的に見えないため、専用に数える。

    分母は `llm_call.tool_names` (= 実際に LLM へ出ていたツール)。シナリオが
    落としたツールを「使われなかった」と数えないため、既知の一覧ではなく
    trace から取る。
    """
    exposed: set = set()
    called: Counter = Counter()
    errors: Dict[str, Counter] = defaultdict(Counter)
    for event in events:
        kind = event.get("kind")
        payload = event.get("payload") or {}
        if kind == "llm_call":
            exposed |= set(payload.get("tool_names") or [])
        elif kind == "action_result":
            tool = payload.get("tool")
            if tool not in MARKET_TOOLS:
                continue
            called[tool] += 1
            if payload.get("error_code"):
                errors[tool][payload["error_code"]] += 1
    return {
        "exposed_market_tools": sorted(exposed & MARKET_TOOLS),
        "called": dict(called),
        "never_called": sorted((exposed & MARKET_TOOLS) - set(called)),
        "error_codes": {tool: dict(codes) for tool, codes in errors.items()},
    }


def extract_market(events: List[dict]) -> Dict[str, Any]:
    """市場軸 (G-41〜G-44 / G-47 / G-48) をまとめて返す。

    板が一度も動いていない run では ``measurable: False`` を立てる。0 が並んだ
    表を「市場が使われなかった」と読ませないため — その run では市場が
    **試されていない**。
    """
    states = replay_board(events)
    return {
        "measurable": bool(states),
        "g41_price_series": _price_series(states),
        "g42_repricing": _repricing(events),
        "g43_item_coverage": _item_coverage(events, states),
        "g44_crossing": _crossing(states),
        "g47_route_choice": _route_choice(events, states),
        "g48_tool_exposure": _tool_exposure(events),
    }
