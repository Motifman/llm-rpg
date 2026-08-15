"""買い手が受け取れなかった品は、板の足元に置かれる (経済統合 Phase 3)。

買い注文は「品を待つ」形なので、**売られた瞬間に買い手が居るとは限らない**。
その人の所持品が満杯だったとき、どこへ置くかを決める必要がある。

**買い手の足元ではなく、板の足元**に置く。買い手の足元だと落ちる場所がその人の
居場所に依存し、探しに行く先が決まらない。板の前なら、買い注文を出した場所その
もので、本人が戻る理由も既にある (自分の注文がある)。

板に「引き取り待ち」として預かる案は採らない。`MarketOrder` は数量を 1 つしか
持たないので、**部分約定**のとき「まだ求めている数」と「預かっている数」が同じ
フィールドを奪い合う。売り注文で成立したのは期限切れ後 (注文が終わっていて残数が
そのまま預かり量になる) だから。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.support.overflow_sinks import IGNORE_OVERFLOW

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_HERB = "薬草"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["players"][0]["initial_gold"] = 300
    raw["players"].append({
        "id": "tom", "name": "トム",
        "spawn_spot": raw["players"][0]["spawn_spot"],
        "initial_items": [], "initial_gold": 300,
        "persona_prompt": "あなたはトム。",
    })
    raw["market"] = {"board_spot": "market_square"}
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
    while not runtime._player_inventory_repo.find_by_id(player_id).is_inventory_full():
        _give(runtime, player_id, label, 1)


def _on_the_ground_at(runtime: Any, spot_id: Any, label: str) -> int:
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    return sum(
        1
        for item in interior.ground_items
        if item.item_spec_id.value == _spec_id(runtime, label)
    )


def _board_spot(runtime: Any) -> Any:
    return runtime._market_service.board_spot_id


def _spot_of(runtime: Any, player_id: PlayerId) -> Any:
    graph = runtime._spot_graph_repo.find_graph()
    return graph.get_entity_spot(EntityId.create(int(player_id)))


def _walk_away(runtime: Any, player_id: PlayerId) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    here = graph.get_entity_spot(EntityId.create(int(player_id)))
    elsewhere = next(
        spot for spot in graph.neighbor_spot_ids_for_routing(here) if spot != here
    )
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(EntityId.create(int(player_id)), elsewhere)
    runtime._spot_graph_repo.save(graph)


def _drain(runtime: Any, player_id: PlayerId) -> List[Any]:
    return [entry.output for entry in runtime._obs_buffer.drain(player_id)]


def _undelivered(runtime: Any, player_id: PlayerId) -> List[Any]:
    return [
        o
        for o in _drain(runtime, player_id)
        if (o.structured or {}).get("type") == "market_delivery_left_at_the_board"
    ]


def _sell_into_a_full_buyer(town: Any) -> None:
    """トムが買い注文を出し、満杯のまま、レナが売る。"""
    town._market_service.place_buy_order(
        _TOM, item_label=_HERB, quantity=1, unit_price=8,
        current_tick=town.current_tick(),
    )
    _fill(town, _TOM, _HERB)
    _give(town, _LENA, _HERB, 1)
    town._market_service.sell_best(
        _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
    )


class TestUndeliverableGoodsStayAtTheBoard:
    """受け取れなかった品は、板の足元に置かれる。"""

    def test_it_lands_at_the_board(self, town: Any) -> None:
        """買い手が満杯なら、売られた品は板の足元に置かれる。"""
        before = _on_the_ground_at(town, _board_spot(town), _HERB)

        _sell_into_a_full_buyer(town)

        assert _on_the_ground_at(town, _board_spot(town), _HERB) == before + 1

    def test_it_lands_at_the_board_even_when_the_buyer_is_away(self, town: Any) -> None:
        """買い手が板から離れていても、置かれるのは板の足元。

        **落ちる場所が本人の居場所に依存しない**ので、探しに行く先が決まる。
        """
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        _fill(town, _TOM, _HERB)
        _walk_away(town, _TOM)
        _give(town, _LENA, _HERB, 1)
        elsewhere = _spot_of(town, _TOM)
        before_board = _on_the_ground_at(town, _board_spot(town), _HERB)
        before_elsewhere = _on_the_ground_at(town, elsewhere, _HERB)

        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        assert _on_the_ground_at(town, _board_spot(town), _HERB) == before_board + 1
        assert _on_the_ground_at(town, elsewhere, _HERB) == before_elsewhere

    def test_nothing_is_lost(self, town: Any) -> None:
        """品は世界から消えていない。"""
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        _fill(town, _TOM, _HERB)
        _give(town, _LENA, _HERB, 1)
        before = (
            _held(town, _LENA, _HERB)
            + _held(town, _TOM, _HERB)
            + _on_the_ground_at(town, _board_spot(town), _HERB)
        )

        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        after = (
            _held(town, _LENA, _HERB)
            + _held(town, _TOM, _HERB)
            + _on_the_ground_at(town, _board_spot(town), _HERB)
        )
        assert after == before

    def test_the_seller_is_still_paid(self, town: Any) -> None:
        """受け取り側の事情で、売った人が損することはない。"""
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        _fill(town, _TOM, _HERB)
        _give(town, _LENA, _HERB, 1)
        before = town._player_status_repo.find_by_id(_LENA).gold.value

        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        assert town._player_status_repo.find_by_id(_LENA).gold.value == before + 8

    def test_a_buyer_with_room_receives_it_directly(self, town: Any) -> None:
        """買い手に空きがあれば、地面には置かれない (**正の対照**)。"""
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        _give(town, _LENA, _HERB, 1)
        before = _on_the_ground_at(town, _board_spot(town), _HERB)

        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        assert _held(town, _TOM, _HERB) == 1
        assert _on_the_ground_at(town, _board_spot(town), _HERB) == before


class TestTheBuyerIsToldWhereItIs:
    """置かれたことは、買い手に届く。"""

    def test_the_buyer_hears_about_it(self, town: Any) -> None:
        """買い手に「届いたが受け取れなかった」が届く。

        届かないと、gold は減っているのに品が無い理由が分からない。
        """
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        _fill(town, _TOM, _HERB)
        _walk_away(town, _TOM)
        _give(town, _LENA, _HERB, 1)
        _drain(town, _TOM)

        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        observed = _undelivered(town, _TOM)
        assert len(observed) == 1
        assert _HERB in observed[0].prose

    def test_the_wording_is_not_the_same_as_dropping_it(self, town: Any) -> None:
        """文面が「取り落とした」と別になっている。

        **落としたのは本人の不注意ではない。** 届いた品を受け取れなかっただけ
        なので、混ぜると読み違える。
        """
        town._market_service.place_buy_order(
            _TOM, item_label=_HERB, quantity=1, unit_price=8,
            current_tick=town.current_tick(),
        )
        _fill(town, _TOM, _HERB)
        _give(town, _LENA, _HERB, 1)
        _drain(town, _TOM)

        town._market_service.sell_best(
            _LENA, item_label=_HERB, quantity=1, current_tick=town.current_tick(),
        )

        (observed,) = _undelivered(town, _TOM)
        assert "取り落とした" not in observed.prose
        assert "掲示板" in observed.prose

    def test_it_does_not_wake_the_buyer(self, town: Any) -> None:
        """買い手の手番は起きない。知って、次の自分の手番で取りに行けばよい。"""
        _sell_into_a_full_buyer(town)

        (observed,) = _undelivered(town, _TOM)
        assert observed.schedules_turn is False
