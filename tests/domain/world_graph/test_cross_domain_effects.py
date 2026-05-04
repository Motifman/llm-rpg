"""WorldGraphEffectService のクロスドメインeffect（APPLY_DAMAGE等）のユニットテスト。

Phase 1 で追加した新effectタイプが正しくspecを生成することを検証する。
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import WorldGraphEffectService
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


class TestApplyDamageEffect:
    """APPLY_DAMAGE effectのテスト"""

    def test_damage_spec_is_generated(self) -> None:
        """ダメージ値が正の場合、DamageSpecが生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
            parameters={"damage": 15, "message": "棘に刺さった"},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.damage_specs) == 1
        assert result.damage_specs[0].damage == 15
        assert result.damage_specs[0].message == "棘に刺さった"

    def test_zero_damage_is_ignored(self) -> None:
        """ダメージ0は無視されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
            parameters={"damage": 0},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.damage_specs) == 0


class TestApplyStatusEffectEffect:
    """APPLY_STATUS_EFFECT effectのテスト"""

    def test_status_effect_spec_is_generated(self) -> None:
        """有効な状態異常パラメータでSpecが生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.APPLY_STATUS_EFFECT,
            parameters={"status_effect_type": "POISON", "value": 3.0, "duration_ticks": 50},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.status_effect_specs) == 1
        spec = result.status_effect_specs[0]
        assert spec.effect_type_name == "POISON"
        assert spec.value == 3.0
        assert spec.duration_ticks == 50

    def test_empty_type_name_is_ignored(self) -> None:
        """空のeffect_type_nameは無視されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.APPLY_STATUS_EFFECT,
            parameters={"status_effect_type": "", "value": 1.0, "duration_ticks": 10},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.status_effect_specs) == 0


class TestTeleportEntityEffect:
    """TELEPORT_ENTITY effectのテスト"""

    def test_teleport_spec_is_generated(self) -> None:
        """TeleportSpecが生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.TELEPORT_ENTITY,
            parameters={"spot_id": 42},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.teleport_specs) == 1
        assert result.teleport_specs[0].target_spot_id == 42


class TestChangeAtmosphereEffect:
    """CHANGE_ATMOSPHERE effectのテスト"""

    def test_atmosphere_update_spec_is_generated(self) -> None:
        """AtmosphereUpdateSpecが生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ATMOSPHERE,
            parameters={
                "spot_id": 3,
                "hazard_level": 2,
                "hazard_description": "水位が上昇している",
            },
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.atmosphere_update_specs) == 1
        spec = result.atmosphere_update_specs[0]
        assert spec.spot_id == 3
        assert spec.hazard_level == 2
        assert spec.hazard_description == "水位が上昇している"


class TestCombineItemsEffect:
    """COMBINE_ITEMS effectのテスト"""

    def test_input_items_removed_and_output_granted(self) -> None:
        """入力アイテムがremoveされ、出力アイテムがgrantされること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.COMBINE_ITEMS,
            parameters={
                "input_item_spec_ids": [1, 2],
                "output_item_spec_id": 99,
            },
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.item_spec_ids_to_remove) == 2
        assert len(result.item_spec_ids_to_grant) == 1


class TestMultipleEffectsAccumulate:
    """複数効果の蓄積テスト"""

    def test_damage_and_teleport_accumulate(self) -> None:
        """ダメージとテレポートが同時に蓄積されること"""
        svc = WorldGraphEffectService()
        effects = [
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
                parameters={"damage": 5},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.TELEPORT_ENTITY,
                parameters={"spot_id": 10},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                parameters={"message": "落とし穴に落ちた！"},
            ),
        ]
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=effects, world_flags=frozenset(),
        )
        assert len(result.damage_specs) == 1
        assert len(result.teleport_specs) == 1
        assert len(result.messages) == 1
