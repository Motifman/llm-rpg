"""SATISFY_NEED エフェクトのユニットテスト。

WorldGraphEffectService が SatisfyNeedSpec を正しく生成することを検証する。
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import WorldGraphEffectService
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


class TestSatisfyNeedEffect:
    """SATISFY_NEED エフェクトのテスト"""

    def test_satisfy_need_spec_generated(self) -> None:
        """有効なパラメータで SatisfyNeedSpec が生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
            parameters={"need_type": "HUNGER", "amount": 50},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.satisfy_need_specs) == 1
        spec = result.satisfy_need_specs[0]
        assert spec.need_type_name == "HUNGER"
        assert spec.amount == 50

    def test_fatigue_satisfy(self) -> None:
        """疲労回復のSpecが生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
            parameters={"need_type": "FATIGUE", "amount": 80},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.satisfy_need_specs) == 1
        assert result.satisfy_need_specs[0].need_type_name == "FATIGUE"

    def test_zero_amount_ignored(self) -> None:
        """amount=0 の場合は Spec が生成されないこと"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
            parameters={"need_type": "HUNGER", "amount": 0},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.satisfy_need_specs) == 0

    def test_empty_need_type_ignored(self) -> None:
        """need_type が空の場合は Spec が生成されないこと"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
            parameters={"need_type": "", "amount": 50},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.satisfy_need_specs) == 0

    def test_multiple_satisfy_effects(self) -> None:
        """食事+睡眠の複合効果で複数Specが蓄積されること"""
        svc = WorldGraphEffectService()
        effects = [
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
                parameters={"need_type": "HUNGER", "amount": 40},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
                parameters={"need_type": "FATIGUE", "amount": 30},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                parameters={"message": "温かい食事をとり、少し休んだ。"},
            ),
        ]
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=effects, world_flags=frozenset(),
        )
        assert len(result.satisfy_need_specs) == 2
        assert len(result.messages) == 1
