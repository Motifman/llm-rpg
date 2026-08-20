"""板の表示が、打てる手を塞いで見せないことを保証する。

## なぜこの試験が要るか

実 run で、焼き手がパンを 1 つ持ち、空腹 88 の状態でこう考えている。

> 掲示板にはパンの買い注文がないから、手持ちのパンを売っても買い手がつかない
> ——となると、自分で薬草を摘めるようになるのが一番確実な道だ。

**彼女は板で売る可能性を検討したうえで棄却している。** 棄却の根拠は「買い注文が
ない」。しかし**出品は買い注文の有無と関係ない** — 出品は買い手を待つ行為である。

原因は表示文面だった。

    "焼きたてのパン" 20G で買える (出品 2件)   売れない (買い注文なし)

**「売れない」が、売り側の口を塞がれたと読ませた。** 実際には「いま即座に売れる
買い注文は無い」だけで、出品はできる。買い注文が尽きた t14 以降、この行は
**66 手番にわたり全員に「パンは売れない」と表示し続けた**。板の前に立ち、パンを
2 つ以上持っていた手番が 16 回あった。**出品は起こりえた。**

買い側も同じ形をしている (「買えない (出品なし)」)。実際は買い注文を出して待てる。
`market_bid` は 2 つの run で 1 度も呼ばれていない。**同じ理由の可能性が高いので、
同時に直す。**
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)

_VIEWER = 1


def _board_lines(runtime: Any) -> str:
    text = runtime.build_llm_context(PlayerId(_VIEWER)).current_state_text
    return "\n".join(
        line for line in text.splitlines() if "G で" in line or "なし" in line
    )


def _town(tmp_path: Path, orders: list) -> Any:
    raw: Dict[str, Any] = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    raw["market"]["initial_orders"] = orders
    path = tmp_path / "town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


_BREAD_FOR_SALE = [
    {"merchant": "gustav", "side": "sell", "item_spec": "bread",
     "quantity": 1, "unit_price": 20},
]
_HERB_WANTED = [
    {"merchant": "gustav", "side": "buy", "item_spec": "herb",
     "quantity": 2, "unit_price": 11},
]


class TestTheBoardNeverSaysYouCannot:
    """相手が居ないことと、自分が動けないことを混同しない。"""

    def test_no_bids_still_invites_listing(self, tmp_path: Path) -> None:
        """買い注文が無いとき、「売れない」ではなく「出品して待てる」と出る。

        **打てる手を塞いで見せる方が、冗長より悪い。**
        """
        runtime = _town(tmp_path, _BREAD_FOR_SALE)

        lines = _board_lines(runtime)

        assert "売れない" not in lines
        assert "出品して待てる" in lines

    def test_no_listings_still_invites_bidding(self, tmp_path: Path) -> None:
        """出品が無いとき、「買えない」ではなく「買い注文を出して待てる」と出る。

        売り側と同じ形の誤読が、買い側にもある。
        """
        runtime = _town(tmp_path, _HERB_WANTED)

        lines = _board_lines(runtime)

        assert "買えない" not in lines
        assert "買い注文を出して待てる" in lines


class TestThePricesAreStillShown:
    """相手が居るときは、これまでどおり値が出る (**正の対照**)。"""

    def test_a_price_to_buy_at_is_shown(self, tmp_path: Path) -> None:
        """出品があれば、買える値が出る。

        これが無いと、上の 2 件は「板の行が丸ごと消えた」でも緑になる。
        """
        runtime = _town(tmp_path, _BREAD_FOR_SALE)

        assert "20G で買える" in _board_lines(runtime)

    def test_a_price_to_sell_at_is_shown(self, tmp_path: Path) -> None:
        """買い注文があれば、売れる値が出る。"""
        runtime = _town(tmp_path, _HERB_WANTED)

        assert "11G で売れる" in _board_lines(runtime)
