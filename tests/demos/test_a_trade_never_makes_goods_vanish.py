"""取引が成立するとき、品が消えて gold だけ動くことはない (経済統合 Phase 2 の穴)。

`PlayerInventoryAggregate.acquire_item` は所持品が満杯だと**黙って品を捨てる**
(溢れイベントを出して return する)。そのイベントを publish する経路はどこにも
無いので、結果メッセージにも観測にも trace にも残らない。

同席取引の決済はこの `acquire_item` を事前確認なしで呼んでいた。相手が満杯
だと、**渡した側からは品が消え、gold だけが動く**。経済の実験としては結果が
丸ごと嘘になる種類の事故で、しかも当事者の誰にも見えない。

`pickup_item` / `give_item` / `buy_item` / 市場の約定は既に事前に断る形になって
いる。ここだけが残っていた。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.trade.services.player_trade_service import (
    TradeAskNotMetError,
    TradeReceiverInventoryFullError,
    TradeSelfInventoryFullError,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_HERB = "薬草"
_BREAD = "焼きたてのパン"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    """レナとトムが同じ場所に居て、人同士の取引が使える市場町。"""
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["players"].append({
        "id": "tom", "name": "トム",
        "spawn_spot": raw["players"][0]["spawn_spot"],
        "initial_items": [], "initial_gold": 100,
        "persona_prompt": "あなたはトム。",
    })
    raw["player_trade"] = {"enabled": True}
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _spec_id(runtime: Any, label: str) -> int:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id.value


def _held(runtime: Any, player_id: PlayerId, label: str) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    return sum(c for s, c in counts.items() if s.value == _spec_id(runtime, label))


def _give(runtime: Any, player_id: PlayerId, label: str, count: int = 1) -> None:
    grant_item_specs_to_inventory(
        player_id,
        tuple(ItemSpecId.create(_spec_id(runtime, label)) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _fill(runtime: Any, player_id: PlayerId, label: str) -> None:
    """所持品を満杯にする。"""
    while not runtime._player_inventory_repo.find_by_id(player_id).is_inventory_full():
        _give(runtime, player_id, label, 1)


def _gold(runtime: Any, player_id: PlayerId) -> int:
    return runtime._player_status_repo.find_by_id(player_id).gold.value


def _offer_herb_for_gold(runtime: Any) -> Any:
    """レナが薬草 1 つを 5G で買い取る形の提案を、トムへ出す。"""
    return runtime._player_trade_service.offer(
        _LENA,
        target=_TOM,
        gives_items=(),
        gives_gold=5,
        asks_item_labels=({"item_label": _HERB, "quantity": 1},),
        asks_gold=0,
        current_tick=runtime.current_tick(),
    )


class TestTheOffererCannotLoseGoodsIntoAFullInventory:
    """受ける側が満杯なら、取引そのものを断る。"""

    def test_the_trade_is_refused_when_the_receiver_is_full(self, town: Any) -> None:
        """受ける側の所持品に空きが無いと、承諾できない。"""
        _give(town, _LENA, _BREAD, 1)
        _fill(town, _TOM, _HERB)
        town._player_trade_service.offer(
            _LENA,
            target=_TOM,
            gives_items=({"item_spec_id": _spec_id(town, _BREAD), "quantity": 1},),
            gives_gold=0,
            asks_item_labels=(),
            asks_gold=3,
            current_tick=town.current_tick(),
        )

        with pytest.raises(TradeSelfInventoryFullError):
            town._player_trade_service.accept(_TOM, offerer=_LENA)

    def test_nothing_moves_when_the_trade_is_refused(self, town: Any) -> None:
        """断られたとき、品も gold も 1 つも動かない。

        **これが本題**。以前は品が消えたうえで gold だけ動いていた。
        """
        _give(town, _LENA, _BREAD, 1)
        _fill(town, _TOM, _HERB)
        town._player_trade_service.offer(
            _LENA,
            target=_TOM,
            gives_items=({"item_spec_id": _spec_id(town, _BREAD), "quantity": 1},),
            gives_gold=0,
            asks_item_labels=(),
            asks_gold=3,
            current_tick=town.current_tick(),
        )
        lena_bread = _held(town, _LENA, _BREAD)
        lena_gold = _gold(town, _LENA)
        tom_gold = _gold(town, _TOM)

        with pytest.raises(TradeSelfInventoryFullError):
            town._player_trade_service.accept(_TOM, offerer=_LENA)

        assert _held(town, _LENA, _BREAD) == lena_bread
        assert _held(town, _TOM, _BREAD) == 0
        assert _gold(town, _LENA) == lena_gold
        assert _gold(town, _TOM) == tom_gold

    def test_the_offer_survives_the_refusal(self, town: Any) -> None:
        """断られても提案は残る。空きを作ってから受け直せる。

        消すと、受ける側は理由を知らないまま選択肢が消え、持ちかけた側は
        凍結が解けた理由が分からない (承諾できない他の理由と同じ扱い)。
        """
        _give(town, _LENA, _BREAD, 1)
        _fill(town, _TOM, _HERB)
        town._player_trade_service.offer(
            _LENA,
            target=_TOM,
            gives_items=({"item_spec_id": _spec_id(town, _BREAD), "quantity": 1},),
            gives_gold=0,
            asks_item_labels=(),
            asks_gold=3,
            current_tick=town.current_tick(),
        )

        with pytest.raises(TradeSelfInventoryFullError):
            town._player_trade_service.accept(_TOM, offerer=_LENA)

        assert town._pending_trade_offer_store.list_for_target(_TOM)


class TestTheReceiverIsNotBlockedByAFairSwap:
    """出す数と受け取る数が釣り合う取引は、満杯でも成立する。

    **正の対照**。空きだけを見て断ると、1 対 1 の交換ができなくなる。渡すぶんの
    枠が空くので、除去を先に済ませれば入る。ここを取り違えると、事故を塞いだ
    つもりで**普通の取引を塞ぐ**。
    """

    def test_a_one_for_one_swap_succeeds_with_a_full_inventory(self, town: Any) -> None:
        """互いに満杯でも、1 つ渡して 1 つ受け取る交換は成立する。"""
        _give(town, _LENA, _BREAD, 1)
        _fill(town, _LENA, _HERB)
        _give(town, _TOM, _HERB, 1)
        _fill(town, _TOM, _BREAD)
        town._player_trade_service.offer(
            _LENA,
            target=_TOM,
            gives_items=({"item_spec_id": _spec_id(town, _BREAD), "quantity": 1},),
            gives_gold=0,
            asks_item_labels=({"item_label": _HERB, "quantity": 1},),
            asks_gold=0,
            current_tick=town.current_tick(),
        )
        lena_herb = _held(town, _LENA, _HERB)

        town._player_trade_service.accept(_TOM, offerer=_LENA)

        assert _held(town, _LENA, _HERB) == lena_herb + 1


class TestTheOffererMustHaveRoomToo:
    """持ちかけた側に空きが無いときも、取引を断る。"""

    def test_the_trade_is_refused_when_the_offerer_is_full(self, town: Any) -> None:
        """求めたものを受け取る空きが持ちかけた側に無いと、承諾できない。

        受ける側には直せない事情なので、重複や品不足とは別の失敗にする
        (「相手の手が塞がっている」— give_item と同じ形)。
        """
        _fill(town, _LENA, _BREAD)
        _give(town, _TOM, _HERB, 1)
        _offer_herb_for_gold(town)

        with pytest.raises(TradeReceiverInventoryFullError):
            town._player_trade_service.accept(_TOM, offerer=_LENA)

    def test_nothing_moves_when_the_offerer_has_no_room(self, town: Any) -> None:
        """持ちかけた側の空き不足で断られたときも、何も動かない。"""
        _fill(town, _LENA, _BREAD)
        _give(town, _TOM, _HERB, 1)
        _offer_herb_for_gold(town)
        tom_herb = _held(town, _TOM, _HERB)
        tom_gold = _gold(town, _TOM)
        lena_gold = _gold(town, _LENA)

        with pytest.raises(TradeReceiverInventoryFullError):
            town._player_trade_service.accept(_TOM, offerer=_LENA)

        assert _held(town, _TOM, _HERB) == tom_herb
        assert _gold(town, _TOM) == tom_gold
        assert _gold(town, _LENA) == lena_gold


class TestAnOrdinaryTradeStillWorks:
    """空きがある普通の取引は、これまでどおり成立する (正の対照)。"""

    def test_the_goods_and_the_gold_both_move(self, town: Any) -> None:
        """薬草 1 つと 5G が、互いの手を行き来する。"""
        _give(town, _TOM, _HERB, 1)
        _offer_herb_for_gold(town)
        lena_gold = _gold(town, _LENA)
        tom_gold = _gold(town, _TOM)

        town._player_trade_service.accept(_TOM, offerer=_LENA)

        assert _held(town, _LENA, _HERB) == 1
        assert _held(town, _TOM, _HERB) == 0
        assert _gold(town, _LENA) == lena_gold - 5
        assert _gold(town, _TOM) == tom_gold + 5

    def test_a_missing_item_still_fails_for_its_own_reason(self, town: Any) -> None:
        """品を持っていないときの失敗は、空き不足とは別のままになる。

        失敗を 1 つに畳むと、次の一手 (集める / 空ける) が読めなくなる。
        """
        _offer_herb_for_gold(town)

        with pytest.raises(TradeAskNotMetError):
            town._player_trade_service.accept(_TOM, offerer=_LENA)
