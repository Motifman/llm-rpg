"""持ちきれなかった品は、足元に落ちて見える (経済統合 Phase 3 の後始末)。

実 run (`var/runs/m7_v3coop_001`) では、ノアが「乾いた流木を一本拾い上げた」で
36 回成功しながら手放したのは 6 回で、20 枠に収まっていなかった。本人は
「流木はもう十八本ある」と信じたまま拾い続けていた。**拾っても増えないから
拾い直していた**可能性が高い。

採取そのものは成功しているので、行動全体を失敗にすると意味が変わる。品は
足元に落とし、**本人にも同席者にも**そのことを届ける。届かないと、採取の結果が
手元に無い理由が本人にも分からない。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.world_graph.overflow_sinks import (
    OverflowShouldNotHappenError,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.support.overflow_sinks import IGNORE_OVERFLOW

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_HERB = "薬草"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    """市場町に 2 人。薬草を摘める。"""
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    raw["players"].append({
        "id": "tom", "name": "トム",
        "spawn_spot": raw["players"][0]["spawn_spot"],
        "initial_items": [], "initial_gold": 50,
        "persona_prompt": "あなたはトム。",
    })
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _spec_id(runtime: Any, label: str) -> int:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id.value


def _held(runtime: Any, player_id: PlayerId, label: str) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    return sum(c for s, c in counts.items() if s.value == _spec_id(runtime, label))


def _on_the_ground(runtime: Any, player_id: PlayerId, label: str) -> int:
    from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

    graph = runtime._spot_graph_repo.find_graph()
    spot_id = graph.get_entity_spot(EntityId.create(int(player_id)))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    return sum(
        1
        for item in interior.ground_items
        if item.item_spec_id.value == _spec_id(runtime, label)
    )


def _give(runtime: Any, player_id: PlayerId, label: str, count: int = 1) -> None:
    """テストの下ごしらえ。溢れはここでは見ない。"""
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


def _grant_through_the_world(runtime: Any, player_id: PlayerId, label: str) -> None:
    """効果として品を与える (採取・報酬と同じ経路)。"""
    grant_item_specs_to_inventory(
        player_id,
        (ItemSpecId.create(_spec_id(runtime, label)),),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=runtime._ground_overflow_sink,
    )


def _drain(runtime: Any, player_id: PlayerId) -> List[Any]:
    return [entry.output for entry in runtime._obs_buffer.drain(player_id)]


def _overflow_observations(runtime: Any, player_id: PlayerId) -> List[Any]:
    return [
        o
        for o in _drain(runtime, player_id)
        if (o.structured or {}).get("type") == "player_overflowed_item"
    ]


class TestNothingIsLostWhenYourHandsAreFull:
    """持ちきれなかった品は、消えずに足元へ行く。"""

    def test_it_lands_on_the_ground(self, town: Any) -> None:
        """所持品が満杯のとき与えられた品は、その場の地面に落ちる。"""
        _fill(town, _LENA, _HERB)

        _grant_through_the_world(town, _LENA, _HERB)

        assert _on_the_ground(town, _LENA, _HERB) == 1

    def test_the_total_does_not_change(self, town: Any) -> None:
        """所持品と地面を合わせた数は、与えたぶんだけ増える。

        **これが本題**。以前はここで 1 つ消えていた。
        """
        _fill(town, _LENA, _HERB)
        before = _held(town, _LENA, _HERB) + _on_the_ground(town, _LENA, _HERB)

        _grant_through_the_world(town, _LENA, _HERB)

        after = _held(town, _LENA, _HERB) + _on_the_ground(town, _LENA, _HERB)
        assert after == before + 1

    def test_it_goes_into_the_pack_when_there_is_room(self, town: Any) -> None:
        """空きがあるときは地面に落ちない (**正の対照**)。

        いつでも地面に落ちる実装になっていないことを見る。
        """
        _grant_through_the_world(town, _LENA, _HERB)

        assert _held(town, _LENA, _HERB) == 1
        assert _on_the_ground(town, _LENA, _HERB) == 0


class TestTheOneWhoDroppedItIsTold:
    """落としたことは、本人に届く。"""

    def test_the_owner_hears_about_it(self, town: Any) -> None:
        """本人に「取り落とした」が届く。

        届かないと、**採取の結果が手元に無い理由が本人にも分からない**。
        実 run のノアは「十八本ある」と信じたまま拾い続けていた。
        """
        _fill(town, _LENA, _HERB)
        _drain(town, _LENA)

        _grant_through_the_world(town, _LENA, _HERB)

        observed = _overflow_observations(town, _LENA)
        assert len(observed) == 1
        assert _HERB in observed[0].prose

    def test_the_wording_is_not_the_same_as_putting_it_down(self, town: Any) -> None:
        """文面が「置いた」と別になっている。

        地面に物が増えるのは同じでも、**拾ってよいかの読みが変わる**。置いた
        ものは誰かのための置き方かもしれないが、取り落としたものは本人が拾い
        直したいはず。
        """
        _fill(town, _LENA, _HERB)
        _drain(town, _LENA)

        _grant_through_the_world(town, _LENA, _HERB)

        (observed,) = _overflow_observations(town, _LENA)
        assert "取り落とした" in observed.prose
        assert "地面に置いた" not in observed.prose

    def test_a_bystander_sees_it_too(self, town: Any) -> None:
        """同席者にも届く。地面に物が増えるのは場の変化で、拾える人が居る。"""
        _fill(town, _LENA, _HERB)
        _drain(town, _TOM)

        _grant_through_the_world(town, _LENA, _HERB)

        observed = _overflow_observations(town, _TOM)
        assert len(observed) == 1
        assert "レナ" in observed[0].prose

    def test_it_does_not_wake_anyone(self, town: Any) -> None:
        """取り落としで手番は起きない。

        採取のたびに同席者全員が動くと行動密度が跳ね上がる。落ちたことを
        知って、次の自分の手番で拾い直すか決めればよい。
        """
        _fill(town, _LENA, _HERB)
        _drain(town, _TOM)

        _grant_through_the_world(town, _LENA, _HERB)

        (observed,) = _overflow_observations(town, _TOM)
        assert observed.schedules_turn is False
        assert observed.observation_category == "social"


class TestWhatFellIsAnOrdinaryGroundItem:
    """落ちた品は、置かれた品と同じように扱える。"""

    def test_anyone_can_pick_it_up(self, town: Any) -> None:
        """同席している他人が拾える。

        協力にも略奪にもなるが、**どちらに転ぶかはエージェントの選択**で、
        engine が決める話ではない。「落とし主だけが拾える地面アイテム」を
        作ると、拾う側から見て同じに見えるのに拾えない物が生まれる。
        """
        _fill(town, _LENA, _HERB)
        _grant_through_the_world(town, _LENA, _HERB)
        interior_before = _on_the_ground(town, _LENA, _HERB)

        town._item_transfer_service.pickup_item(
            _TOM, _ground_instance_id(town, _LENA, _HERB),
        )

        assert _held(town, _TOM, _HERB) == 1
        assert _on_the_ground(town, _LENA, _HERB) == interior_before - 1

    def test_the_owner_can_take_it_back(self, town: Any) -> None:
        """空きを作れば、落とした本人も拾い直せる。"""
        _fill(town, _LENA, _HERB)
        _grant_through_the_world(town, _LENA, _HERB)
        town._item_transfer_service.drop_item(_LENA, _first_occupied_slot(town, _LENA))

        town._item_transfer_service.pickup_item(
            _LENA, _ground_instance_id(town, _LENA, _HERB),
        )

        assert _on_the_ground(town, _LENA, _HERB) >= 1


class TestThePathsThatPromisedToRefuseStillRefuse:
    """事前に断る経路で溢れが起きたら、黙って落とさずに落ちる。"""

    def test_the_market_sink_raises(self, town: Any) -> None:
        """市場の sink は、呼ばれたら例外になる。

        市場の約定は受け取る空きを**動かす前に**確かめている。それでもここへ
        来たなら、その確認が壊れている。黙って地面に落とすと、破れが
        「なぜか品が地面にある」という読みにくい形でしか現れない。
        """
        from ai_rpg_world.application.world_graph.overflow_sinks import refuse_overflow

        sink = refuse_overflow("市場の約定")

        with pytest.raises(OverflowShouldNotHappenError) as exc:
            sink(_LENA, (ItemSpecId.create(1),))

        assert "市場の約定" in str(exc.value)

    def test_the_market_service_is_wired_to_that_sink(self, town: Any) -> None:
        """市場サービスに渡っている sink が、実際に落ちる sink である。

        **正の対照**。sink を差し替えただけで配線を忘れると、事前拒否が壊れた
        ときに黙って地面へ落ちる。
        """
        with pytest.raises(OverflowShouldNotHappenError):
            town._market_service._overflow_sink(_LENA, (ItemSpecId.create(1),))

    def test_the_trade_service_is_wired_to_that_sink(self, town: Any) -> None:
        """同席取引も同じ。"""
        with pytest.raises(OverflowShouldNotHappenError):
            town._player_trade_service._overflow_sink(_LENA, (ItemSpecId.create(1),))


def _ground_instance_id(runtime: Any, player_id: PlayerId, label: str):
    from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

    graph = runtime._spot_graph_repo.find_graph()
    spot_id = graph.get_entity_spot(EntityId.create(int(player_id)))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    return next(
        item.item_instance_id
        for item in interior.ground_items
        if item.item_spec_id.value == _spec_id(runtime, label)
    )


def _first_occupied_slot(runtime: Any, player_id: PlayerId):
    from ai_rpg_world.domain.player.value_object.slot_id import SlotId

    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    for i in range(inventory.max_slots):
        if inventory.get_item_instance_id_by_slot(SlotId(i)) is not None:
            return SlotId(i)
    raise AssertionError("所持品が空です")
