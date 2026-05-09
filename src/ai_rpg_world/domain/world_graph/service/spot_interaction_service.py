from __future__ import annotations

from typing import FrozenSet, Mapping, Optional, Tuple

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType


def _hp_ratio(status: "PlayerStatusAggregate") -> Optional[float]:
    """`PlayerStatusAggregate` から現在の HP の充足率 (0.0..1.0) を計算する。

    max_hp が 0 のときは判定不能として None を返す (precondition 側で
    not None チェックで弾く)。
    """
    hp = status.hp
    if hp.max_hp <= 0:
        return None
    return hp.value / hp.max_hp
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
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
        acting_item_aggregate: Optional["ItemAggregate"] = None,
        target_item_aggregate: Optional["ItemAggregate"] = None,
        acting_player_status: Optional["PlayerStatusAggregate"] = None,
    ) -> Tuple[bool, Optional[str]]:
        # Phase 4-B: 同一 instance を acting / target 両方として渡すのは
        # wiring バグ。precondition 段階で弾く（apply_effects と同じガード）。
        if (
            acting_item_aggregate is not None
            and acting_item_aggregate is target_item_aggregate
        ):
            raise ValueError(
                "acting_item_aggregate and target_item_aggregate must be distinct "
                "instances; passing the same aggregate as both indicates a wiring bug"
            )
        # `owned_item_spec_counts` が渡されない場合は「frozenset から各 1 個」
        # でフォールバックする（required_quantity=1 の既存挙動と互換）。
        # ただし precondition のいずれかが required_quantity > 1 を要求する
        # のに counts が無いと silent wrong answer になるので、その場合は
        # 早期に明示的なエラーで弾く（pre-release のため後方互換は不要）。
        if owned_item_spec_counts is None:
            needs_counts = any(
                c.required_quantity > 1 for c in interaction.preconditions
            )
            if needs_counts:
                raise ValueError(
                    "owned_item_spec_counts is required when any precondition has "
                    "required_quantity > 1; pass count_owned_item_instances_by_spec(...)"
                )
            counts: Mapping[ItemSpecId, int] = {sid: 1 for sid in owned_item_spec_ids}
        else:
            counts = owned_item_spec_counts
        for cond in interaction.preconditions:
            ok, msg = self._evaluate_condition(
                cond, spot_object, world_flags,
                spot_presence_count=spot_presence_count,
                interaction_parameters=interaction_parameters,
                owned_item_spec_counts=counts,
                acting_item_aggregate=acting_item_aggregate,
                target_item_aggregate=target_item_aggregate,
                acting_player_status=acting_player_status,
            )
            if not ok:
                return False, msg
        return True, None

    def _evaluate_condition(
        self,
        cond: InteractionCondition,
        spot_object: SpotObject,
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
        owned_item_spec_counts: Mapping[ItemSpecId, int],
        acting_item_aggregate: Optional["ItemAggregate"] = None,
        target_item_aggregate: Optional["ItemAggregate"] = None,
        acting_player_status: Optional["PlayerStatusAggregate"] = None,
    ) -> Tuple[bool, Optional[str]]:
        t = cond.condition_type
        if t == InteractionConditionTypeEnum.ALWAYS:
            return True, None
        if t == InteractionConditionTypeEnum.HAS_ITEM:
            if cond.target_item_spec_id is None:
                return False, cond.failure_message or "HAS_ITEM に target_item_spec_id がありません"
            required = max(1, int(cond.required_quantity))
            owned = owned_item_spec_counts.get(cond.target_item_spec_id, 0)
            if owned < required:
                return False, cond.failure_message or (
                    f"必要なアイテムが足りません (必要: {required}, 所持: {owned})"
                    if required > 1
                    else "必要なアイテムを持っていません"
                )
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

        if t == InteractionConditionTypeEnum.ITEM_INSTANCE_STATE:
            # Phase 4-A: acting item instance の state[k] が required_state の
            # 全キー/値と一致しているかを判定する。
            # acting_item_aggregate を渡してこなかった場合は precondition
            # 失敗 (作家ミスを silent にしないため)。
            if cond.required_state is None:
                return False, cond.failure_message or "ITEM_INSTANCE_STATE に required_state がありません"
            if acting_item_aggregate is None:
                return False, (
                    cond.failure_message
                    or "ITEM_INSTANCE_STATE は acting item instance を必要とします (use_item 経路で評価される想定)"
                )
            for k, v in cond.required_state.items():
                if acting_item_aggregate.state.get(k) != v:
                    return False, cond.failure_message or "アイテムの状態が条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE:
            # Phase 4-B: target item instance (cross-instance interaction の作用先)
            # の state を判定する。acting 版と semantics は同じで対象だけが違う。
            if cond.required_state is None:
                return False, cond.failure_message or "TARGET_ITEM_INSTANCE_STATE に required_state がありません"
            if target_item_aggregate is None:
                return False, (
                    cond.failure_message
                    or "TARGET_ITEM_INSTANCE_STATE は target item instance を必要とします"
                )
            for k, v in cond.required_state.items():
                if target_item_aggregate.state.get(k) != v:
                    return False, cond.failure_message or "対象アイテムの状態が条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.HAS_ITEMS:
            if not cond.required_item_spec_ids:
                return False, cond.failure_message or "HAS_ITEMS に必要アイテムリストがありません"
            # required_quantity は各 spec に同じ値を適用する。
            # 種別ごとに別々の数量を要求したい場合は HAS_ITEM を複数回列挙する。
            required = max(1, int(cond.required_quantity))
            for item_id in cond.required_item_spec_ids:
                if owned_item_spec_counts.get(item_id, 0) < required:
                    return False, cond.failure_message or "必要なアイテムが揃っていません"
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST:
            # Phase 4-D-1: プレイヤーの欲求 (HUNGER / FATIGUE 等) が threshold
            # 以上なら成立。「空腹なときだけ食物が効く」のような表現に使う。
            if cond.need_type is None or cond.need_threshold is None:
                return False, cond.failure_message or (
                    "PLAYER_NEED_AT_LEAST には need_type と need_threshold が必要です"
                )
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_NEED_AT_LEAST は acting player status を必要とします"
                )
            try:
                need_type = NeedType(cond.need_type)
            except ValueError:
                return False, cond.failure_message or (
                    f"PLAYER_NEED_AT_LEAST の need_type が不正: {cond.need_type!r}"
                )
            need = acting_player_status.needs.get(need_type)
            if need is None:
                # プレイヤーがその need を持たない (= 0 とみなす)
                return False, cond.failure_message or "対応する need が登録されていません"
            if need.value < int(cond.need_threshold):
                return False, cond.failure_message or "プレイヤーの状態が条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW:
            # 「HP が hp_ratio 未満なら成立」。「HP 半分以下のときだけ強い薬草」
            # のような表現用。
            if cond.hp_ratio is None:
                return False, cond.failure_message or "PLAYER_HP_RATIO_BELOW には hp_ratio が必要です"
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_HP_RATIO_BELOW は acting player status を必要とします"
                )
            ratio = _hp_ratio(acting_player_status)
            if ratio is None or ratio >= float(cond.hp_ratio):
                return False, cond.failure_message or "プレイヤーの HP 条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST:
            # 「HP が hp_ratio 以上なら成立」。「HP 満タンに近いときだけ強行突破」
            # のような表現用。BELOW の鏡像。
            if cond.hp_ratio is None:
                return False, cond.failure_message or "PLAYER_HP_RATIO_AT_LEAST には hp_ratio が必要です"
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_HP_RATIO_AT_LEAST は acting player status を必要とします"
                )
            ratio = _hp_ratio(acting_player_status)
            if ratio is None or ratio < float(cond.hp_ratio):
                return False, cond.failure_message or "プレイヤーの HP 条件を満たしません"
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
        current_tick: Optional[WorldTick] = None,
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
        acting_item_aggregate: Optional[ItemAggregate] = None,
        target_item_aggregate: Optional[ItemAggregate] = None,
        acting_player_status: Optional[PlayerStatusAggregate] = None,
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
            owned_item_spec_counts=owned_item_spec_counts,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
            acting_player_status=acting_player_status,
        )
        if not ok:
            raise InteractionNotAllowedException(reason or "Interaction not allowed")

        effect_result = self._effect_service.apply_effects(
            interior=interior,
            acting_object=obj,
            effects=idef.effects,
            world_flags=world_flags,
            current_tick=current_tick,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
        )
        return InteractionExecutionResult(
            new_interior=effect_result.new_interior,
            new_flags=effect_result.new_flags,
            messages=effect_result.messages,
            item_spec_ids_to_grant=effect_result.item_spec_ids_to_grant,
            item_spec_ids_to_remove=effect_result.item_spec_ids_to_remove,
            damage_specs=effect_result.damage_specs,
            status_effect_specs=effect_result.status_effect_specs,
            teleport_specs=effect_result.teleport_specs,
            atmosphere_update_specs=effect_result.atmosphere_update_specs,
            create_connection_specs=effect_result.create_connection_specs,
            destroy_connection_specs=effect_result.destroy_connection_specs,
            satisfy_need_specs=effect_result.satisfy_need_specs,
            passage_state_updates=effect_result.passage_state_updates,
            item_instance_state_changed=effect_result.item_instance_state_changed,
            target_item_instance_state_changed=effect_result.target_item_instance_state_changed,
        )
