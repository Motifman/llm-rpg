from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
    UnknownSpotObjectException,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_execution_result import InteractionExecutionResult
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)


class SpotInteractionService:
    """スポット内オブジェクト操作（リポジトリ非依存）"""

    def __init__(self, effect_service: Optional[WorldGraphEffectService] = None) -> None:
        self._effect_service = effect_service or WorldGraphEffectService()

    def find_interaction(self, spot_object: SpotObject, action_name: str) -> Optional[InteractionDef]:
        for idef in spot_object.interactions:
            if idef.action_name == action_name:
                return idef
        return None

    def can_interact(
        self,
        interaction: InteractionDef,
        spot_object: SpotObject,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
    ) -> Tuple[bool, Optional[str]]:
        for cond in interaction.preconditions:
            ok, msg = self._evaluate_condition(
                cond, spot_object, owned_item_spec_ids, world_flags,
                spot_presence_count=spot_presence_count,
                interaction_parameters=interaction_parameters,
            )
            if not ok:
                return False, msg
        return True, None

    def _evaluate_condition(
        self,
        cond: InteractionCondition,
        spot_object: SpotObject,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
    ) -> Tuple[bool, Optional[str]]:
        t = cond.condition_type
        if t == InteractionConditionTypeEnum.ALWAYS:
            return True, None
        if t == InteractionConditionTypeEnum.HAS_ITEM:
            if cond.target_item_spec_id is None:
                return False, cond.failure_message or "HAS_ITEM に target_item_spec_id がありません"
            if cond.target_item_spec_id not in owned_item_spec_ids:
                return False, cond.failure_message or "必要なアイテムを持っていません"
            return True, None
        if t == InteractionConditionTypeEnum.OBJECT_STATE:
            if cond.required_state is None:
                return False, cond.failure_message or "OBJECT_STATE に required_state がありません"
            for k, v in cond.required_state.items():
                if spot_object.state.get(k) != v:
                    return False, cond.failure_message or "オブジェクトの状態が条件を満たしません"
            return True, None
        if t == InteractionConditionTypeEnum.FLAG_SET:
            if not cond.flag_name:
                return False, cond.failure_message or "フラグ名がありません"
            if cond.flag_name not in world_flags:
                return False, cond.failure_message or "必要なフラグが立っていません"
            return True, None

        # --- 脱出ゲーム拡張 ---

        if t == InteractionConditionTypeEnum.PLAYERS_AT_SPOT:
            required = cond.required_player_count if cond.required_player_count is not None else 2
            if spot_presence_count < required:
                return False, cond.failure_message or f"このアクションには{required}人以上が必要です"
            return True, None

        if t == InteractionConditionTypeEnum.PREPARED_ACTION:
            if not cond.prepared_action_id:
                return False, cond.failure_message or "準備アクションIDがありません"
            prefix = f"prepared:{cond.prepared_action_id}:"
            if not any(f.startswith(prefix) for f in world_flags):
                return False, cond.failure_message or "他のプレイヤーがまだ準備していません"
            return True, None

        if t == InteractionConditionTypeEnum.PUZZLE_INPUT_MATCH:
            if not cond.puzzle_input_key:
                return False, cond.failure_message or "パズル入力キーがありません"
            params = interaction_parameters or {}
            user_input = params.get(cond.puzzle_input_key)
            expected = cond.required_state or {}
            if "answer" not in expected:
                return False, cond.failure_message or "パズル答えが設定されていません"
            expected_value = expected["answer"]
            if user_input is None or str(user_input) != str(expected_value):
                return False, cond.failure_message or "入力が正しくありません"
            return True, None

        if t == InteractionConditionTypeEnum.HAS_ITEMS:
            if not cond.required_item_spec_ids:
                return False, cond.failure_message or "HAS_ITEMS に必要アイテムリストがありません"
            for item_id in cond.required_item_spec_ids:
                if item_id not in owned_item_spec_ids:
                    return False, cond.failure_message or "必要なアイテムが揃っていません"
            return True, None

        return False, cond.failure_message or "未対応の前提条件です"

    def execute_interaction(
        self,
        interior: SpotInterior,
        object_id: SpotObjectId,
        action_name: str,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
    ) -> InteractionExecutionResult:
        obj = interior.get_object(object_id)
        if obj is None:
            raise UnknownSpotObjectException(str(object_id))
        idef = self.find_interaction(obj, action_name)
        if idef is None:
            raise InteractionNotFoundException(f"{action_name} on {object_id}")
        ok, reason = self.can_interact(
            idef, obj, owned_item_spec_ids, world_flags,
            spot_presence_count=spot_presence_count,
            interaction_parameters=interaction_parameters,
        )
        if not ok:
            raise InteractionNotAllowedException(reason or "Interaction not allowed")

        effect_result = self._effect_service.apply_effects(
            interior=interior,
            acting_object=obj,
            effects=idef.effects,
            world_flags=world_flags,
        )
        return InteractionExecutionResult(
            new_interior=effect_result.new_interior,
            new_flags=effect_result.new_flags,
            messages=effect_result.messages,
            item_spec_ids_to_grant=effect_result.item_spec_ids_to_grant,
            item_spec_ids_to_remove=effect_result.item_spec_ids_to_remove,
            connection_passability_updates=effect_result.connection_passability_updates,
            damage_specs=effect_result.damage_specs,
            status_effect_specs=effect_result.status_effect_specs,
            teleport_specs=effect_result.teleport_specs,
            atmosphere_update_specs=effect_result.atmosphere_update_specs,
            create_connection_specs=effect_result.create_connection_specs,
            destroy_connection_specs=effect_result.destroy_connection_specs,
            satisfy_need_specs=effect_result.satisfy_need_specs,
            passage_state_updates=effect_result.passage_state_updates,
        )
