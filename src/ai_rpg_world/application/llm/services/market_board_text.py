"""板を、読む人が打てる手の言葉に整える (経済統合 Phase 3)。

**同じ板を 2 か所が出す。** ツール (`market_view`) の戻り値と、プロンプトに
常駐する「自分の注文」。文言が割れると、引いた板と自分の欄で同じ注文が別の
書かれ方をする。整形をここ 1 か所に集めて、割れる道を無くす。

言葉は**見る人が次に打てる手**で書く。「売り 3 件 (最安 18G)」ではなく
「18G で買える (出品 3件)」。板の売り注文は、見る人にとっては「買える」で、
注文の向きと打てる手は逆になる。向きのまま出すと、読む側が毎回変換する。
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence, Tuple

from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphMarketOwnOrderEntry,
    SpotGraphMarketRowEntry,
)

#: 板に相手が居ないときの表示。**「できない」と書かない。**
#:
#: 以前は「売れない (買い注文なし)」「買えない (出品なし)」と書いていた。実 run で
#: 焼き手が「掲示板にはパンの買い注文がないから、手持ちのパンを売っても買い手が
#: つかない」と**売る可能性を検討したうえで棄却**している。しかし出品は買い注文の
#: 有無と関係なく、**買い手を待つ行為**である。66 手番にわたり全員へ「売れない」と
#: 表示し続け、板の前でパンを 2 つ以上持っていた手番が 16 回あった。**出品は
#: 起こりえた。起きなかったのは表示のせい。**
_NO_BIDS = "買い注文なし (出品して待てる)"
_NO_LISTINGS = "出品なし (買い注文を出して待てる)"

_NOTHING_AT_ALL = "  (いま出ているものは無い)"
#: 自分の注文だけがある状態。**「無い」だけだと預けた品が消えたと読める。**
_NOTHING_BUT_YOURS = "  (他に出ているものは無い)"

_UNKNOWN_ITEM = "(名前不明のもの)"


def market_entries_from_view(
    view: Any, item_display_name: Callable[[int], str]
) -> Tuple[
    Tuple[SpotGraphMarketRowEntry, ...], Tuple[SpotGraphMarketOwnOrderEntry, ...]
]:
    """板の読み出し結果を、品名を引いた表示用の行へ変換する。

    打てる手が 1 つも無い品目の行は落とす。ただし**直近に成立した値がある品目は
    残す** — 板が空でも「直近 9G で成立した」は次に打てる手 (その値で出す) を
    作るので、打てない手を並べることにはならない。
    """
    rows = []
    for row in view.rows:
        if (
            row.buy_price_gold is None
            and row.sell_price_gold is None
            and row.last_trade_price_gold is None
        ):
            continue
        rows.append(SpotGraphMarketRowEntry(
            item_name=item_display_name(row.item_spec_id),
            buy_price_gold=row.buy_price_gold,
            listing_count=row.listing_count,
            buyable_quantity=row.buyable_quantity,
            sell_price_gold=row.sell_price_gold,
            bid_count=row.bid_count,
            sellable_quantity=row.sellable_quantity,
            last_trade_price_gold=row.last_trade_price_gold,
        ))
    own = tuple(
        SpotGraphMarketOwnOrderEntry(
            item_name=item_display_name(order.item_spec_id),
            side=order.side.value,
            quantity=order.quantity,
            unit_price_gold=order.unit_price_gold,
            is_awaiting_collection=order.is_awaiting_collection,
        )
        for order in view.own_orders
    )
    return tuple(rows), own


def market_board_text(view: Any, item_display_name: Callable[[int], str]) -> str:
    """板を読んだ結果の全文を組み立てる。

    見出し・需給の行・自分の注文の順。**組み立てをここ 1 か所に置く**ので、
    ツールの戻り値と、文言を確かめる試験が同じ文を見る。
    """
    rows, own_orders = market_entries_from_view(view, item_display_name)
    lines = ["市場の掲示板:"]
    lines.extend(board_rows_lines(rows, has_own_orders=bool(own_orders)))
    lines.extend(own_order_lines(own_orders))
    return "\n".join(lines)


def board_rows_lines(
    rows: Sequence[SpotGraphMarketRowEntry], *, has_own_orders: bool = False
) -> Tuple[str, ...]:
    """板の需給を 1 品目 1 行で整える。

    空のときも 1 行出す。黙って何も返さないと「引けなかった」と区別がつかない。
    自分の注文だけがあるときは「他に」と書く — 自分の注文は需給の集約から外れる
    ので、「無い」とだけ書くと**預けた品が消えた**と読める。
    """
    if not rows:
        return (_NOTHING_BUT_YOURS if has_own_orders else _NOTHING_AT_ALL,)
    return tuple(f"  \"{row.item_name}\" {_row_text(row)}" for row in rows)


def own_order_lines(
    own_orders: Sequence[SpotGraphMarketOwnOrderEntry],
) -> Tuple[str, ...]:
    """自分が板に出している注文を 1 件 1 行で整える。

    売りと買いでラベルを分ける。同じ品目に両方出していると 2 行並ぶので、
    同じラベルだと「自分で自分に売れる」と読める。
    """
    lines = []
    for order in own_orders:
        if order.side == "buy":
            label = "あなたの買い注文"
            state = (
                "引き取り待ち"
                if order.is_awaiting_collection
                else "まだ受けられていない"
            )
        else:
            label = "あなたの出品"
            state = (
                "引き取り待ち" if order.is_awaiting_collection else "まだ売れていない"
            )
        lines.append(
            f"  {label}: \"{order.item_name}\" ×{order.quantity} "
            f"@{order.unit_price_gold}G ({state})"
        )
    return tuple(lines)


def _row_text(row: SpotGraphMarketRowEntry) -> str:
    buy_side = (
        f"{row.buy_price_gold}G で買える "
        f"(出品 {row.listing_count}件 / 計 {row.buyable_quantity}つ)"
        if row.buy_price_gold is not None
        else _NO_LISTINGS
    )
    sell_side = (
        f"{row.sell_price_gold}G で売れる "
        f"(買い注文 {row.bid_count}件 / 計 {row.sellable_quantity}つ)"
        if row.sell_price_gold is not None
        else _NO_BIDS
    )
    return f"{buy_side}   {sell_side}{_settled_text(row.last_trade_price_gold)}"


def _settled_text(last_trade_price_gold: Optional[int]) -> str:
    """直近に成立した単価。一度も成立していないなら欄ごと出さない。

    0G と書くと「0G で成立した」と読める。**無いことは無いと言う。**
    """
    if last_trade_price_gold is None:
        return ""
    return f"   直近 {last_trade_price_gold}G で成立"


__all__ = [
    "board_rows_lines",
    "market_board_text",
    "market_entries_from_view",
    "own_order_lines",
]
