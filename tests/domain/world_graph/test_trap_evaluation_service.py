"""TrapEvaluationService のユニットテスト。

トラップの発動判定、解除条件、繰返し/一度きり、進入/操作トリガーの動作を検証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.trap_trigger_type import TrapTriggerTypeEnum
from ai_rpg_world.domain.world_graph.service.trap_evaluation_service import TrapEvaluationService
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef


def _damage_effect(damage: int = 10) -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
        parameters={"damage": damage, "message": "罠が発動した！"},
    )


def _teleport_effect(spot_id: int = 5) -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.TELEPORT_ENTITY,
        parameters={"spot_id": spot_id},
    )


def _poison_effect() -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.APPLY_STATUS_EFFECT,
        parameters={"status_effect_type": "POISON", "value": 2.0, "duration_ticks": 30},
    )


def _entry_trap(
    trap_id: str = "spike_trap",
    is_repeating: bool = False,
    is_hidden: bool = True,
    disarm_conditions: tuple = (),
    effects: tuple = None,
) -> TrapDef:
    return TrapDef(
        trap_id=trap_id,
        trigger_type=TrapTriggerTypeEnum.ON_ENTRY,
        effects=effects or (_damage_effect(),),
        is_hidden=is_hidden,
        is_repeating=is_repeating,
        disarm_conditions=disarm_conditions,
    )


def _interact_trap(trap_id: str = "chest_trap") -> TrapDef:
    return TrapDef(
        trap_id=trap_id,
        trigger_type=TrapTriggerTypeEnum.ON_INTERACT,
        effects=(_poison_effect(),),
    )


class TestEntryTrapEvaluation:
    """進入トラップの発動判定テスト"""

    def test_basic_entry_trap_triggers(self) -> None:
        """基本的な進入トラップが発動し、効果を返すこと"""
        svc = TrapEvaluationService()
        traps = (_entry_trap(),)
        triggered, effects, new_flags = svc.evaluate_entry_traps(traps, frozenset(), frozenset())
        assert len(triggered) == 1
        assert len(effects) == 1
        assert effects[0].effect_type == InteractionEffectTypeEnum.APPLY_DAMAGE

    def test_one_shot_trap_sets_triggered_flag(self) -> None:
        """一度きりトラップ発動時に trap_triggered フラグが返されること"""
        svc = TrapEvaluationService()
        traps = (_entry_trap(trap_id="spike", is_repeating=False),)
        triggered, effects, new_flags = svc.evaluate_entry_traps(traps, frozenset(), frozenset())
        assert len(triggered) == 1
        assert "trap_triggered:spike" in new_flags

    def test_repeating_trap_does_not_set_triggered_flag(self) -> None:
        """繰返しトラップ発動時には trap_triggered フラグが返されないこと"""
        svc = TrapEvaluationService()
        traps = (_entry_trap(trap_id="fire", is_repeating=True),)
        _, _, new_flags = svc.evaluate_entry_traps(traps, frozenset(), frozenset())
        assert "trap_triggered:fire" not in new_flags

    def test_one_shot_trap_does_not_retrigger(self) -> None:
        """一度きりのトラップは、発動フラグがあると再発動しないこと"""
        svc = TrapEvaluationService()
        traps = (_entry_trap(trap_id="spike", is_repeating=False),)
        flags = frozenset({"trap_triggered:spike"})
        triggered, effects, _ = svc.evaluate_entry_traps(traps, flags, frozenset())
        assert len(triggered) == 0
        assert len(effects) == 0

    def test_repeating_trap_retriggers(self) -> None:
        """繰返しトラップは、発動フラグがあっても再発動すること"""
        svc = TrapEvaluationService()
        traps = (_entry_trap(trap_id="fire", is_repeating=True),)
        flags = frozenset({"trap_triggered:fire"})
        triggered, effects, _ = svc.evaluate_entry_traps(traps, flags, frozenset())
        assert len(triggered) == 1

    def test_disarmed_trap_does_not_trigger(self) -> None:
        """解除条件（フラグ）を満たしたトラップは発動しないこと"""
        svc = TrapEvaluationService()
        disarm = (
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.FLAG_SET,
                flag_name="trap_disarmed",
            ),
        )
        traps = (_entry_trap(disarm_conditions=disarm),)
        flags = frozenset({"trap_disarmed"})
        triggered, effects, _ = svc.evaluate_entry_traps(traps, flags, frozenset())
        assert len(triggered) == 0

    def test_disarm_by_item(self) -> None:
        """解除条件（アイテム所持）を満たしたトラップは発動しないこと"""
        svc = TrapEvaluationService()
        key = ItemSpecId.create(42)
        disarm = (
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                target_item_spec_id=key,
            ),
        )
        traps = (_entry_trap(disarm_conditions=disarm),)
        # アイテムなし → 発動
        triggered1, _, _ = svc.evaluate_entry_traps(traps, frozenset(), frozenset())
        assert len(triggered1) == 1
        # アイテムあり → 不発
        triggered2, _, _ = svc.evaluate_entry_traps(traps, frozenset(), frozenset({key}))
        assert len(triggered2) == 0

    def test_multiple_traps_evaluate_independently(self) -> None:
        """複数トラップがそれぞれ独立に評価されること"""
        svc = TrapEvaluationService()
        traps = (
            _entry_trap(trap_id="a"),
            _entry_trap(trap_id="b"),
        )
        flags = frozenset({"trap_triggered:a"})  # aのみ発動済み
        triggered, effects, _ = svc.evaluate_entry_traps(traps, flags, frozenset())
        assert len(triggered) == 1
        assert triggered[0].trap_id == "b"

    def test_multiple_effects_per_trap(self) -> None:
        """1つのトラップに複数効果がある場合、全て返すこと"""
        svc = TrapEvaluationService()
        traps = (_entry_trap(effects=(_damage_effect(), _teleport_effect())),)
        triggered, effects, _ = svc.evaluate_entry_traps(traps, frozenset(), frozenset())
        assert len(effects) == 2

    def test_on_interact_trap_ignored_by_entry_evaluation(self) -> None:
        """ON_INTERACTトラップは進入評価では無視されること"""
        svc = TrapEvaluationService()
        traps = (_interact_trap(),)
        triggered, effects, _ = svc.evaluate_entry_traps(traps, frozenset(), frozenset())
        assert len(triggered) == 0


class TestInteractTrapEvaluation:
    """操作トラップの発動判定テスト"""

    def test_interact_trap_triggers(self) -> None:
        """操作トラップが発動し、効果を返すこと"""
        svc = TrapEvaluationService()
        trap = _interact_trap()
        effects, new_flags = svc.evaluate_interact_trap(trap, frozenset(), frozenset())
        assert len(effects) == 1
        assert effects[0].effect_type == InteractionEffectTypeEnum.APPLY_STATUS_EFFECT

    def test_entry_trap_ignored_by_interact_evaluation(self) -> None:
        """ON_ENTRYトラップは操作評価では空を返すこと"""
        svc = TrapEvaluationService()
        trap = _entry_trap()
        effects, _ = svc.evaluate_interact_trap(trap, frozenset(), frozenset())
        assert len(effects) == 0

    def test_one_shot_interact_trap_does_not_retrigger(self) -> None:
        """一度きりの操作トラップは再発動しないこと"""
        svc = TrapEvaluationService()
        trap = _interact_trap(trap_id="poison_chest")
        flags = frozenset({"trap_triggered:poison_chest"})
        effects, _ = svc.evaluate_interact_trap(trap, flags, frozenset())
        assert len(effects) == 0

    def test_one_shot_interact_trap_sets_flag(self) -> None:
        """一度きり操作トラップ発動時にフラグが返されること"""
        svc = TrapEvaluationService()
        trap = _interact_trap(trap_id="poison_chest")
        effects, new_flags = svc.evaluate_interact_trap(trap, frozenset(), frozenset())
        assert len(effects) == 1
        assert "trap_triggered:poison_chest" in new_flags


class TestTrapDefValidation:
    """TrapDef のバリデーション・イミュータブル性テスト"""

    def test_trap_def_is_frozen(self) -> None:
        """TrapDefがfrozenであること"""
        trap = _entry_trap()
        with pytest.raises(AttributeError):
            trap.trap_id = "changed"  # type: ignore[misc]

    def test_empty_trap_id_raises(self) -> None:
        """空のtrap_idでValueErrorが発生すること"""
        with pytest.raises(ValueError, match="trap_id cannot be empty"):
            TrapDef(
                trap_id="",
                trigger_type=TrapTriggerTypeEnum.ON_ENTRY,
                effects=(_damage_effect(),),
            )

    def test_no_effects_raises(self) -> None:
        """効果なしのTrapDefでValueErrorが発生すること"""
        with pytest.raises(ValueError, match="must have at least one effect"):
            TrapDef(
                trap_id="empty",
                trigger_type=TrapTriggerTypeEnum.ON_ENTRY,
                effects=(),
            )
