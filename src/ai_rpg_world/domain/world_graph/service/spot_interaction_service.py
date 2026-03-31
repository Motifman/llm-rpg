from __future__ import annotations

from typing import Any, FrozenSet, List, Optional, Tuple

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
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.interaction_execution_result import InteractionExecutionResult
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


class SpotInteractionService:
    """スポット内オブジェクト操作（リポジトリ非依存）"""

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
    ) -> Tuple[bool, Optional[str]]:
        for cond in interaction.preconditions:
            ok, msg = self._evaluate_condition(cond, spot_object, owned_item_spec_ids, world_flags)
            if not ok:
                return False, msg
        return True, None

    def _evaluate_condition(
        self,
        cond: InteractionCondition,
        spot_object: SpotObject,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
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
        return False, cond.failure_message or "未対応の前提条件です"

    def execute_interaction(
        self,
        interior: SpotInterior,
        object_id: SpotObjectId,
        action_name: str,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> InteractionExecutionResult:
        obj = interior.get_object(object_id)
        if obj is None:
            raise UnknownSpotObjectException(str(object_id))
        idef = self.find_interaction(obj, action_name)
        if idef is None:
            raise InteractionNotFoundException(f"{action_name} on {object_id}")
        ok, reason = self.can_interact(idef, obj, owned_item_spec_ids, world_flags)
        if not ok:
            raise InteractionNotAllowedException(reason or "Interaction not allowed")

        flags: set[str] = set(world_flags)
        messages: List[str] = []
        grant: List[ItemSpecId] = []
        remove: List[ItemSpecId] = []
        conn_updates: List[Tuple[ConnectionId, bool]] = []
        current_interior = interior
        current_obj = obj

        for effect in idef.effects:
            current_interior, current_obj, flags, grant, remove, conn_updates, messages = (
                self._apply_effect(
                    current_interior,
                    current_obj,
                    effect,
                    flags,
                    grant,
                    remove,
                    conn_updates,
                    messages,
                )
            )
        return InteractionExecutionResult(
            new_interior=current_interior,
            new_flags=frozenset(flags),
            messages=tuple(messages),
            item_spec_ids_to_grant=tuple(grant),
            item_spec_ids_to_remove=tuple(remove),
            connection_passability_updates=tuple(conn_updates),
        )

    def _apply_effect(
        self,
        interior: SpotInterior,
        spot_object: SpotObject,
        effect: InteractionEffect,
        flags: set[str],
        grant: List[ItemSpecId],
        remove: List[ItemSpecId],
        conn_updates: List[Tuple[ConnectionId, bool]],
        messages: List[str],
    ) -> Tuple[SpotInterior, SpotObject, set[str], List[ItemSpecId], List[ItemSpecId], List[Tuple[ConnectionId, bool]], List[str]]:
        p = effect.parameters
        et = effect.effect_type

        if et == InteractionEffectTypeEnum.SET_FLAG:
            name = p.get("flag_name")
            if isinstance(name, str):
                flags.add(name)
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        if et == InteractionEffectTypeEnum.SHOW_MESSAGE:
            msg = p.get("message")
            if isinstance(msg, str):
                messages.append(msg)
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        if et == InteractionEffectTypeEnum.GIVE_ITEM:
            sid = self._item_spec_from_param(p.get("item_spec_id"))
            grant.append(sid)
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        if et == InteractionEffectTypeEnum.REMOVE_ITEM:
            sid = self._item_spec_from_param(p.get("item_spec_id"))
            remove.append(sid)
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        if et == InteractionEffectTypeEnum.CHANGE_OBJECT_STATE:
            updates = p.get("state_updates")
            if isinstance(updates, dict):
                new_state = dict(spot_object.state)
                for k, v in updates.items():
                    new_state[str(k)] = v
                new_obj = spot_object.with_state(new_state)
                interior = interior.replace_object(new_obj)
                return interior, new_obj, flags, grant, remove, conn_updates, messages
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        if et == InteractionEffectTypeEnum.REVEAL_OBJECT:
            oid = self._spot_object_id_from_param(p.get("object_id"))
            target = interior.get_object(oid)
            if target is not None:
                revealed = target.with_visible(True)
                interior = interior.replace_object(revealed)
                if revealed.object_id == spot_object.object_id:
                    spot_object = revealed
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        if et == InteractionEffectTypeEnum.REVEAL_SUB_LOCATION:
            slid = self._sub_location_id_from_param(p.get("sub_location_id"))
            for sl in interior.sub_locations:
                if sl.sub_location_id == slid:
                    interior = interior.replace_sub_location(sl.revealed())
                    break
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        if et == InteractionEffectTypeEnum.CHANGE_CONNECTION_STATE:
            cid_raw = p.get("connection_id")
            is_passable = bool(p.get("is_passable", True))
            if cid_raw is not None:
                cid = ConnectionId.create(cid_raw)
                conn_updates.append((cid, is_passable))
            return interior, spot_object, flags, grant, remove, conn_updates, messages

        return interior, spot_object, flags, grant, remove, conn_updates, messages

    @staticmethod
    def _item_spec_from_param(val: Any) -> ItemSpecId:
        if isinstance(val, ItemSpecId):
            return val
        return ItemSpecId.create(val)

    @staticmethod
    def _spot_object_id_from_param(val: Any) -> SpotObjectId:
        if isinstance(val, SpotObjectId):
            return val
        return SpotObjectId.create(val)

    @staticmethod
    def _sub_location_id_from_param(val: Any) -> SubLocationId:
        if isinstance(val, SubLocationId):
            return val
        return SubLocationId.create(val)
