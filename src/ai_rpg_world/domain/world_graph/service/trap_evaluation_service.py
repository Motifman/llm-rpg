"""トラップ発動判定のドメインサービス（stateless）。

スポット進入時やオブジェクト操作時に、対象トラップが発動するかを判定する。
発動したトラップの効果は WorldGraphEffectService で処理する。
"""

from __future__ import annotations

from typing import FrozenSet, List, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.trap_trigger_type import TrapTriggerTypeEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef


class TrapEvaluationService:
    """トラップの発動可否を判定し、発動する効果リストを返す。"""

    def evaluate_entry_traps(
        self,
        traps: Tuple[TrapDef, ...],
        world_flags: FrozenSet[str],
        owned_item_spec_ids: FrozenSet[ItemSpecId],
    ) -> Tuple[Tuple[TrapDef, ...], Tuple[InteractionEffect, ...], FrozenSet[str]]:
        """進入トラップを評価し、(発動トラップ群, 統合効果リスト, 追加すべきフラグ) を返す。

        一度きりトラップが発動した場合、``trap_triggered:{trap_id}`` フラグが
        3番目の要素に含まれる。呼び出し側は WorldFlagRegistry に追加する責務を持つ。
        """
        triggered: List[TrapDef] = []
        effects: List[InteractionEffect] = []
        new_flags: set[str] = set()

        for trap in traps:
            if trap.trigger_type != TrapTriggerTypeEnum.ON_ENTRY:
                continue
            if not self._should_trigger(trap, world_flags, owned_item_spec_ids):
                continue
            triggered.append(trap)
            effects.extend(trap.effects)
            if not trap.is_repeating:
                new_flags.add(f"trap_triggered:{trap.trap_id}")

        return tuple(triggered), tuple(effects), frozenset(new_flags)

    def evaluate_interact_trap(
        self,
        trap: TrapDef,
        world_flags: FrozenSet[str],
        owned_item_spec_ids: FrozenSet[ItemSpecId],
    ) -> Tuple[Tuple[InteractionEffect, ...], FrozenSet[str]]:
        """操作トラップを評価し、(効果リスト, 追加すべきフラグ) を返す。効果が空なら不発。"""
        if trap.trigger_type != TrapTriggerTypeEnum.ON_INTERACT:
            return (), frozenset()
        if not self._should_trigger(trap, world_flags, owned_item_spec_ids):
            return (), frozenset()
        new_flags: FrozenSet[str] = frozenset()
        if not trap.is_repeating:
            new_flags = frozenset({f"trap_triggered:{trap.trap_id}"})
        return trap.effects, new_flags

    def _should_trigger(
        self,
        trap: TrapDef,
        world_flags: FrozenSet[str],
        owned_item_spec_ids: FrozenSet[ItemSpecId],
    ) -> bool:
        """トラップが発動すべきかを判定。解除済みなら不発。"""
        # 一度きりのトラップで既に発動済み
        triggered_flag = f"trap_triggered:{trap.trap_id}"
        if not trap.is_repeating and triggered_flag in world_flags:
            return False

        # 解除条件を全て満たしていれば不発（トラップが解除されている）
        if trap.disarm_conditions and self._all_disarm_conditions_met(
            trap.disarm_conditions, world_flags, owned_item_spec_ids
        ):
            return False

        return True

    def _all_disarm_conditions_met(
        self,
        conditions: Tuple[InteractionCondition, ...],
        world_flags: FrozenSet[str],
        owned_item_spec_ids: FrozenSet[ItemSpecId],
    ) -> bool:
        for cond in conditions:
            t = cond.condition_type
            if t == InteractionConditionTypeEnum.ALWAYS:
                continue
            if t == InteractionConditionTypeEnum.HAS_ITEM:
                if cond.target_item_spec_id is None:
                    return False
                if cond.target_item_spec_id not in owned_item_spec_ids:
                    return False
            elif t == InteractionConditionTypeEnum.FLAG_SET:
                if not cond.flag_name or cond.flag_name not in world_flags:
                    return False
            else:
                raise NotImplementedError(
                    f"Unsupported disarm condition type: {t.value}"
                )
        return True
