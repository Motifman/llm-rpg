"""TELEPORT_ENTITY が宣言された観測文を TeleportSpec へ運ぶことを保証する。

## なぜ engine 側に「ベント」を知らせないか

通気口・隠し通路・魔法陣は「接続を辿らない移動」という 1 つの仕組みの別名でしかない。
engine が action 名や語彙を知ると、新しい言い換えのたびに engine を触ることになる。
**観測される文面はシナリオの宣言として持つ。**

出発側と到着側で明るさが違いうるので、文面は 4 つに分かれる。どれを選ぶかは
実行時に**それぞれの spot の実効照明**で決める (この試験は運搬だけを見る)。
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


def _teleport_effect(**parameters) -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.TELEPORT_ENTITY,
        parameters={"spot_id": 7, **parameters},
    )


def _apply(effect: InteractionEffect):
    return WorldGraphEffectService().apply_effects(
        interior=_empty_interior(),
        acting_object=None,
        effects=[effect],
        world_flags=frozenset(),
    )


class TestTeleportCarriesDeclaredObservations:
    """宣言された 4 つの観測文が TeleportSpec に載る。"""

    def test_all_four_declared_messages_reach_the_spec(self) -> None:
        """出発・到着それぞれの明所文と暗所文が、そのまま spec に載る。"""
        result = _apply(
            _teleport_effect(
                departure_observation_message="{actor}がベントを開けて中に入った。",
                departure_observation_message_in_dark="ベントが開いて誰かが入った音がした。",
                arrival_observation_message="ベントが開いて{actor}が中から出てきた。",
                arrival_observation_message_in_dark="ベントが開いて誰かが出てきた音がした。",
            )
        )

        assert len(result.teleport_specs) == 1
        spec = result.teleport_specs[0]
        assert spec.target_spot_id == 7
        assert spec.departure_observation_message == "{actor}がベントを開けて中に入った。"
        assert (
            spec.departure_observation_message_in_dark
            == "ベントが開いて誰かが入った音がした。"
        )
        assert spec.arrival_observation_message == "ベントが開いて{actor}が中から出てきた。"
        assert (
            spec.arrival_observation_message_in_dark
            == "ベントが開いて誰かが出てきた音がした。"
        )

    def test_teleport_without_declared_messages_keeps_working(self) -> None:
        """観測文を書かない宣言でも移動先は運ばれ、文面は未指定のままになる。"""
        result = _apply(_teleport_effect())

        assert len(result.teleport_specs) == 1
        spec = result.teleport_specs[0]
        assert spec.target_spot_id == 7
        assert spec.departure_observation_message is None
        assert spec.departure_observation_message_in_dark is None
        assert spec.arrival_observation_message is None
        assert spec.arrival_observation_message_in_dark is None
