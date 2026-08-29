"""板は、同席取引 (trade_offer) に出して凍結中の gold を使わせない。

market と player_trade が同時に有効な世界は「供物競争」シナリオが初出で、
それまで両者が同じ gold を見る run は存在しなかった。板が所持金を生で読むと、
取引に出している gold で買い注文が出せてしまい、相手が trade_accept した
瞬間に支払いが `InsufficientGoldException` で途中死する。その時点で両者の
品は所持品から除去済み・未配達なので、**品が世界から消える** (ロールバック
は無い)。

商人側 (`spot_graph_merchant_trade_service`) は `TradeFreezeService.
available_gold` を通している。本テストは板側にも同じ規約
「gold を使う経路はこれを先に通す」(trade_freeze_service.py) を守らせる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.trade.services.market_service import (
    MarketGoldNotEnoughError,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_TOWN = Path(__file__).resolve().parents[4] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_HERB = "薬草"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    raw["players"].append({
        "id": "tom", "name": "トム", "spawn_spot": spawn,
        "initial_items": [], "initial_gold": 20,
        "persona_prompt": "あなたはトム。",
    })
    raw["players"][0]["initial_gold"] = 20
    raw["market"] = {"board_spot": "market_square"}
    raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": 24}
    path = tmp_path / "market_and_trade_town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _freeze_gold_by_offering(town: Any, offerer: PlayerId, gold: int) -> None:
    """取引の提案で gold を凍結する (返事が来るまで使えない)。"""
    town._player_trade_service.offer(
        offerer,
        target=_TOM if offerer != _TOM else _LENA,
        gives_items=(),
        gives_gold=gold,
        asks_item_labels=({"item_label": _HERB, "quantity": 1},),
        asks_gold=0,
        current_tick=town.current_tick(),
    )


class TestTheBoardSeesFrozenGold:
    """板の gold 検査が、取引凍結ぶんを差し引いた残りを見る。"""

    def test_a_buy_order_cannot_spend_frozen_gold(self, town: Any) -> None:
        """20G 持ちが 15G を取引に出したら、板の買い注文に使えるのは 5G まで。

        6G の買い注文は MARKET_GOLD_NOT_ENOUGH で断られ、エラーの
        available には凍結を引いた残額 (5G) が入る。所持金を生で見ると
        ここが 20G になり、注文は通ってしまう。
        """
        _freeze_gold_by_offering(town, _LENA, 15)

        with pytest.raises(MarketGoldNotEnoughError) as exc:
            town._market_service.place_buy_order(
                _LENA, item_label=_HERB, quantity=1, unit_price=6,
                current_tick=town.current_tick(),
            )

        assert exc.value.available == 5

    def test_buying_from_the_board_cannot_spend_frozen_gold(self, town: Any) -> None:
        """出品を買うときも、凍結を引いた残りしか使えない。

        トムが薬草を 6G で出品し、レナ (残り 5G) が買おうとすると断られる。
        """
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        spec = town._item_spec_repo.find_by_name(_HERB).item_spec_id
        grant_item_specs_to_inventory(
            _TOM, (ItemSpecId.create(spec.value),),
            town._item_repo, town._item_spec_repo,
            town._player_inventory_repo, overflow_sink=IGNORE_OVERFLOW,
        )
        town._market_service.place_sell_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=6,
            current_tick=town.current_tick(),
        )
        _freeze_gold_by_offering(town, _LENA, 15)

        with pytest.raises(MarketGoldNotEnoughError):
            town._market_service.buy_best(
                _LENA, item_label=_HERB, quantity=1,
                current_tick=town.current_tick(),
            )

    def test_unfrozen_gold_still_buys(self, town: Any) -> None:
        """凍結が無ければ同じ注文は通る (**正の対照**)。

        これが無いと、上の 2 件は「板が壊れて誰も買えない」でも緑になる。
        """
        order = town._market_service.place_buy_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=6,
            current_tick=town.current_tick(),
        )

        assert order.total_gold == 6

    def test_a_frozen_item_cannot_be_listed_on_the_board(self, town: Any) -> None:
        """取引に差し出して凍結中の品は、板に出品できない (**対称の保険**)。

        品側の凍結は inventory の予約で守られていて gold とは機構が違う。
        market × player_trade の相互作用の回帰網として、両側をこの
        ファイルで見張る。
        """
        from ai_rpg_world.application.trade.services.market_service import (
            MarketItemNotOwnedError,
        )
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        spec = town._item_spec_repo.find_by_name(_HERB).item_spec_id
        grant_item_specs_to_inventory(
            _LENA, (ItemSpecId.create(spec.value),),
            town._item_repo, town._item_spec_repo,
            town._player_inventory_repo, overflow_sink=IGNORE_OVERFLOW,
        )
        town._player_trade_service.offer(
            _LENA, target=_TOM,
            gives_items=({"item_spec_id": spec.value, "quantity": 1},),
            gives_gold=0,
            asks_item_labels=(), asks_gold=5,
            current_tick=town.current_tick(),
        )

        with pytest.raises(MarketItemNotOwnedError):
            town._market_service.place_sell_order(
                _LENA, item_label=_HERB, quantity=1, unit_price=6,
                current_tick=town.current_tick(),
            )

    def test_declined_offer_frees_the_gold_for_the_board(self, town: Any) -> None:
        """取引が断られたら、凍結が解けて板で使えるようになる。

        凍結の差し引きが「提案の生死」に追随することを見る。ここが
        追随しないと、一度でも提案した gold が永久に板で使えなくなる。
        """
        _freeze_gold_by_offering(town, _LENA, 15)
        town._player_trade_service.decline(_TOM, offerer=_LENA)

        order = town._market_service.place_buy_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=6,
            current_tick=town.current_tick(),
        )

        assert order.total_gold == 6
