from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional, Tuple

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    UnsupportedInteractionEffectException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.cross_domain_effect_spec import (
    AtmosphereUpdateSpec,
    CreateConnectionSpec,
    DamageSpec,
    DestroyConnectionSpec,
    PassageStateUpdateSpec,
    SatisfyNeedSpec,
    StatusEffectSpec,
    TeleportSpec,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.domain.world_graph.value_object.world_graph_effect_result import (
    WorldGraphEffectResult,
)


_logger = logging.getLogger(__name__)


class WorldGraphEffectService:
    """Interaction / Scenario Event 共通の effect 適用サービス。"""

    def apply_effects(
        self,
        *,
        interior: SpotInterior,
        acting_object: SpotObject | None,
        effects: Iterable[InteractionEffect],
        world_flags: frozenset[str],
        current_tick: Optional[WorldTick] = None,
        acting_item_aggregate: Optional["ItemAggregate"] = None,
        target_item_aggregate: Optional["ItemAggregate"] = None,
        acting_player_status: Optional["PlayerStatusAggregate"] = None,
    ) -> WorldGraphEffectResult:
        # Phase 4-B: 同一 instance を acting と target の両方として渡すのは
        # 作家ミスかコール元の wiring バグ。両側に同じ参照を入れると
        # CHANGE_ITEM_INSTANCE_STATE と CHANGE_TARGET_ITEM_INSTANCE_STATE が
        # 同じ aggregate を二重に変更し、save も二重発火する潜在バグになる。
        # boundary で明示的に拒否する。
        if (
            acting_item_aggregate is not None
            and acting_item_aggregate is target_item_aggregate
        ):
            raise ValueError(
                "acting_item_aggregate and target_item_aggregate must be distinct "
                "instances; passing the same aggregate as both indicates a wiring bug"
            )
        flags: set[str] = set(world_flags)
        messages: List[str] = []
        grant: List[ItemSpecId] = []
        remove: List[ItemSpecId] = []

        damage_specs: List[DamageSpec] = []
        status_effect_specs: List[StatusEffectSpec] = []
        teleport_specs: List[TeleportSpec] = []
        atmosphere_update_specs: List[AtmosphereUpdateSpec] = []
        create_connection_specs: List[CreateConnectionSpec] = []
        destroy_connection_specs: List[DestroyConnectionSpec] = []
        satisfy_need_specs: List[SatisfyNeedSpec] = []
        passage_specs: List[PassageStateUpdateSpec] = []
        current_interior = interior
        current_object = acting_object

        # Phase 4-A: acting_item_aggregate の state は in-place で書き換える。
        # 「変更があったか」を caller (app service の save 判断) に伝えるため、
        # 適用前に snapshot を取り、ループ終了後に diff を取る。
        # 将来的に effect ごとに細かい change tracking が必要になったら、
        # _apply_effect の戻り値を拡張するか、専用 spec を追加する。
        initial_item_state = (
            dict(acting_item_aggregate.state) if acting_item_aggregate is not None else None
        )
        # Phase 4-B: target_item_aggregate も同じく snapshot diff で変更検知。
        initial_target_item_state = (
            dict(target_item_aggregate.state) if target_item_aggregate is not None else None
        )
        # Phase 4-D-2: 行動者プレイヤーの自由 state も同じパターンで diff 検知。
        initial_player_state = (
            dict(acting_player_status.state) if acting_player_status is not None else None
        )

        for effect in effects:
            (
                current_interior,
                current_object,
                flags,
                grant,
                remove,

                messages,
                damage_specs,
                status_effect_specs,
                teleport_specs,
                atmosphere_update_specs,
                create_connection_specs,
                destroy_connection_specs,
                satisfy_need_specs,
                passage_specs,
            ) = self._apply_effect(
                interior=current_interior,
                acting_object=current_object,
                effect=effect,
                flags=flags,
                grant=grant,
                remove=remove,

                messages=messages,
                damage_specs=damage_specs,
                status_effect_specs=status_effect_specs,
                teleport_specs=teleport_specs,
                atmosphere_update_specs=atmosphere_update_specs,
                create_connection_specs=create_connection_specs,
                destroy_connection_specs=destroy_connection_specs,
                satisfy_need_specs=satisfy_need_specs,
                passage_specs=passage_specs,
                current_tick=current_tick,
                acting_item_aggregate=acting_item_aggregate,
                target_item_aggregate=target_item_aggregate,
                acting_player_status=acting_player_status,
            )

        item_instance_state_changed = (
            acting_item_aggregate is not None
            and dict(acting_item_aggregate.state) != initial_item_state
        )
        target_item_instance_state_changed = (
            target_item_aggregate is not None
            and dict(target_item_aggregate.state) != initial_target_item_state
        )
        acting_player_state_changed = (
            acting_player_status is not None
            and dict(acting_player_status.state) != initial_player_state
        )

        return WorldGraphEffectResult(
            new_interior=current_interior,
            updated_object_id=current_object.object_id.value if current_object is not None else None,
            new_flags=frozenset(flags),
            messages=tuple(messages),
            item_spec_ids_to_grant=tuple(grant),
            item_spec_ids_to_remove=tuple(remove),

            damage_specs=tuple(damage_specs),
            status_effect_specs=tuple(status_effect_specs),
            teleport_specs=tuple(teleport_specs),
            atmosphere_update_specs=tuple(atmosphere_update_specs),
            create_connection_specs=tuple(create_connection_specs),
            destroy_connection_specs=tuple(destroy_connection_specs),
            satisfy_need_specs=tuple(satisfy_need_specs),
            passage_state_updates=tuple(passage_specs),
            item_instance_state_changed=item_instance_state_changed,
            target_item_instance_state_changed=target_item_instance_state_changed,
            acting_player_state_changed=acting_player_state_changed,
        )

    def _apply_effect(
        self,
        *,
        interior: SpotInterior,
        acting_object: SpotObject | None,
        effect: InteractionEffect,
        flags: set[str],
        grant: List[ItemSpecId],
        remove: List[ItemSpecId],

        messages: List[str],
        damage_specs: List[DamageSpec],
        status_effect_specs: List[StatusEffectSpec],
        teleport_specs: List[TeleportSpec],
        atmosphere_update_specs: List[AtmosphereUpdateSpec],
        create_connection_specs: List[CreateConnectionSpec],
        destroy_connection_specs: List[DestroyConnectionSpec],
        satisfy_need_specs: List[SatisfyNeedSpec],
        passage_specs: List[PassageStateUpdateSpec],
        current_tick: Optional[WorldTick] = None,
        acting_item_aggregate: Optional[ItemAggregate] = None,
        target_item_aggregate: Optional[ItemAggregate] = None,
        acting_player_status: Optional[PlayerStatusAggregate] = None,
    ) -> Tuple[
        SpotInterior,
        SpotObject | None,
        set[str],
        List[ItemSpecId],
        List[ItemSpecId],

        List[str],
        List[DamageSpec],
        List[StatusEffectSpec],
        List[TeleportSpec],
        List[AtmosphereUpdateSpec],
        List[CreateConnectionSpec],
        List[DestroyConnectionSpec],
        List[SatisfyNeedSpec],
        List[PassageStateUpdateSpec],
    ]:
        p = effect.parameters
        et = effect.effect_type
        _all = (
            interior, acting_object, flags, grant, remove, messages,
            damage_specs, status_effect_specs, teleport_specs, atmosphere_update_specs, create_connection_specs, destroy_connection_specs, satisfy_need_specs, passage_specs,
        )

        if et == InteractionEffectTypeEnum.SET_FLAG:
            name = p.get("flag_name")
            if isinstance(name, str):
                flags.add(name)
            return _all

        if et == InteractionEffectTypeEnum.SHOW_MESSAGE:
            msg = p.get("message")
            if isinstance(msg, str):
                messages.append(msg)
            return _all

        if et == InteractionEffectTypeEnum.GIVE_ITEM:
            sid = self._item_spec_from_param(p.get("item_spec_id"))
            quantity = self._read_quantity(p)
            for _ in range(quantity):
                grant.append(sid)
            return _all

        if et == InteractionEffectTypeEnum.REMOVE_ITEM:
            sid = self._item_spec_from_param(p.get("item_spec_id"))
            quantity = self._read_quantity(p)
            for _ in range(quantity):
                remove.append(sid)
            return _all

        if et == InteractionEffectTypeEnum.CHANGE_OBJECT_STATE:
            updates = p.get("state_updates")
            if isinstance(updates, dict):
                target = self._resolve_target_object(interior, acting_object, p)
                if target is None:
                    return _all
                new_state = dict(target.state)
                for k, v in updates.items():
                    new_state[str(k)] = v
                updated_target = target.with_state(new_state)
                interior = interior.replace_object(updated_target)
                if (
                    acting_object is not None
                    and updated_target.object_id == acting_object.object_id
                ):
                    acting_object = updated_target
                _all = (
                    interior, acting_object, flags, grant, remove, messages,
                    damage_specs, status_effect_specs, teleport_specs, atmosphere_update_specs, create_connection_specs, destroy_connection_specs, satisfy_need_specs, passage_specs,
                )
            return _all

        if et == InteractionEffectTypeEnum.REVEAL_OBJECT:
            oid = self._spot_object_id_from_param(p.get("object_id"))
            target = interior.get_object(oid)
            if target is not None:
                revealed = target.with_visible(True)
                interior = interior.replace_object(revealed)
                if acting_object is not None and revealed.object_id == acting_object.object_id:
                    acting_object = revealed
                _all = (
                    interior, acting_object, flags, grant, remove, messages,
                    damage_specs, status_effect_specs, teleport_specs, atmosphere_update_specs, create_connection_specs, destroy_connection_specs, satisfy_need_specs, passage_specs,
                )
            return _all

        if et == InteractionEffectTypeEnum.REVEAL_SUB_LOCATION:
            slid = self._sub_location_id_from_param(p.get("sub_location_id"))
            for sl in interior.sub_locations:
                if sl.sub_location_id == slid:
                    interior = interior.replace_sub_location(sl.revealed())
                    _all = (
                        interior, acting_object, flags, grant, remove, messages,
                        damage_specs, status_effect_specs, teleport_specs, atmosphere_update_specs, create_connection_specs, destroy_connection_specs, satisfy_need_specs, passage_specs,
                    )
                    break
            return _all

        # --- 脱出ゲーム拡張 ---

        if et == InteractionEffectTypeEnum.APPLY_DAMAGE:
            damage_val = int(p.get("damage", 0))
            msg = str(p.get("message", ""))
            if damage_val > 0:
                damage_specs.append(DamageSpec(damage=damage_val, message=msg))
            return _all

        if et == InteractionEffectTypeEnum.APPLY_STATUS_EFFECT:
            effect_type_name = str(p.get("status_effect_type", ""))
            value = float(p.get("value", 1.0))
            duration_ticks = int(p.get("duration_ticks", 0))
            if effect_type_name and duration_ticks > 0:
                status_effect_specs.append(
                    StatusEffectSpec(
                        effect_type_name=effect_type_name,
                        value=value,
                        duration_ticks=duration_ticks,
                    )
                )
            return _all

        if et == InteractionEffectTypeEnum.TELEPORT_ENTITY:
            target_spot_id = int(p.get("spot_id", 0))
            if target_spot_id > 0:
                teleport_specs.append(TeleportSpec(target_spot_id=target_spot_id))
            return _all

        if et == InteractionEffectTypeEnum.CHANGE_ATMOSPHERE:
            spot_id = int(p.get("spot_id", 0))
            if spot_id > 0:
                atmosphere_update_specs.append(
                    AtmosphereUpdateSpec(
                        spot_id=spot_id,
                        lighting=p.get("lighting"),
                        temperature=p.get("temperature"),
                        hazard_level=p.get("hazard_level"),
                        hazard_description=p.get("hazard_description"),
                    )
                )
            return _all

        if et == InteractionEffectTypeEnum.COMBINE_ITEMS:
            input_ids = p.get("input_item_spec_ids", [])
            output_id = p.get("output_item_spec_id")
            for iid in input_ids:
                remove.append(self._item_spec_from_param(iid))
            if output_id is not None:
                grant.append(self._item_spec_from_param(output_id))
            return _all

        if et == InteractionEffectTypeEnum.CREATE_CONNECTION:
            from_sid = int(p.get("from_spot_id", 0))
            to_sid = int(p.get("to_spot_id", 0))
            conn_name = str(p.get("connection_name", ""))
            if from_sid > 0 and to_sid > 0 and conn_name:
                if "passage" not in p:
                    # 作家が passage ブロックを書き忘れた場合のフォールバック。
                    # 黙って OPEN にすると意図しない接続種別になりうるので警告する。
                    import logging
                    logging.getLogger(__name__).warning(
                        "CREATE_CONNECTION effect for '%s' is missing 'passage' "
                        "block; defaulting to Passage.open()",
                        conn_name,
                    )
                create_connection_specs.append(CreateConnectionSpec(
                    from_spot_id=from_sid,
                    to_spot_id=to_sid,
                    connection_name=conn_name,
                    description=str(p.get("description", "")),
                    travel_ticks=int(p.get("travel_ticks", 1)),
                    is_bidirectional=bool(p.get("is_bidirectional", False)),
                    passage=Passage.from_dict(p.get("passage")),
                ))
            return _all

        if et == InteractionEffectTypeEnum.DESTROY_CONNECTION:
            cid = int(p.get("connection_id", 0))
            if cid > 0:
                destroy_connection_specs.append(DestroyConnectionSpec(connection_id=cid))
            return _all

        if et == InteractionEffectTypeEnum.SATISFY_NEED:
            need_type_name = str(p.get("need_type", ""))
            amount = int(p.get("amount", 0))
            if need_type_name and amount > 0:
                satisfy_need_specs.append(SatisfyNeedSpec(need_type_name=need_type_name, amount=amount))
            return _all

        if et == InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE:
            # Phase 4-A: acting item instance の state を部分マージ更新する。
            # acting_item_aggregate を caller (use_item 経由など) が
            # 渡してこなかった場合は no-op + warn (silent failure 回避)。
            updates = p.get("state_updates")
            if not isinstance(updates, dict):
                _logger.warning(
                    "CHANGE_ITEM_INSTANCE_STATE: parameters.state_updates must be dict (got %s)",
                    type(updates).__name__,
                )
                return _all
            if acting_item_aggregate is None:
                _logger.warning(
                    "CHANGE_ITEM_INSTANCE_STATE: caller did not provide acting_item_aggregate; "
                    "skipping state merge"
                )
                return _all
            acting_item_aggregate.merge_state(updates)
            return _all

        if et == InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK:
            # Phase 4-A: current_tick.value を acting item の state[state_key] に書き込む。
            # 「最後に使った tick」「最後に火を点けた tick」など、後で
            # OBJECT_STATE_TICK_AT_LEAST に相当する item 側 predicate
            # （後続 PR で導入予定）が読む timestamp を生成する。
            state_key = p.get("state_key")
            if not isinstance(state_key, str) or not state_key:
                _logger.warning(
                    "RECORD_ITEM_INSTANCE_STATE_TICK: state_key is required (got %r)",
                    state_key,
                )
                return _all
            if current_tick is None:
                _logger.warning(
                    "RECORD_ITEM_INSTANCE_STATE_TICK: caller did not provide current_tick; "
                    "skipping write to state[%r]",
                    state_key,
                )
                return _all
            if acting_item_aggregate is None:
                _logger.warning(
                    "RECORD_ITEM_INSTANCE_STATE_TICK: caller did not provide "
                    "acting_item_aggregate; skipping write to state[%r]",
                    state_key,
                )
                return _all
            acting_item_aggregate.merge_state({state_key: int(current_tick.value)})
            return _all

        if et == InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE:
            # Phase 4-B: target_item_instance の state を部分マージ更新する。
            # acting 版と semantics は同一で、対象 aggregate が違うだけ。
            updates = p.get("state_updates")
            if not isinstance(updates, dict):
                _logger.warning(
                    "CHANGE_TARGET_ITEM_INSTANCE_STATE: parameters.state_updates must be dict (got %s)",
                    type(updates).__name__,
                )
                return _all
            if target_item_aggregate is None:
                _logger.warning(
                    "CHANGE_TARGET_ITEM_INSTANCE_STATE: caller did not provide target_item_aggregate; "
                    "skipping state merge"
                )
                return _all
            target_item_aggregate.merge_state(updates)
            return _all

        if et == InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK:
            # Phase 4-B: current_tick.value を target item の state[state_key] に書き込む。
            state_key = p.get("state_key")
            if not isinstance(state_key, str) or not state_key:
                _logger.warning(
                    "RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: state_key is required (got %r)",
                    state_key,
                )
                return _all
            if current_tick is None:
                _logger.warning(
                    "RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: caller did not provide current_tick; "
                    "skipping write to state[%r]",
                    state_key,
                )
                return _all
            if target_item_aggregate is None:
                _logger.warning(
                    "RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: caller did not provide "
                    "target_item_aggregate; skipping write to state[%r]",
                    state_key,
                )
                return _all
            target_item_aggregate.merge_state({state_key: int(current_tick.value)})
            return _all

        if et == InteractionEffectTypeEnum.CHANGE_PLAYER_STATE:
            # Phase 4-D-2: 行動者プレイヤーの自由 state に部分マージ更新。
            # acting_player_status を caller が渡してこなかった場合は
            # silent failure を避けるため warn + no-op (item 系と同じ規約)。
            updates = p.get("state_updates")
            if not isinstance(updates, dict):
                _logger.warning(
                    "CHANGE_PLAYER_STATE: parameters.state_updates must be dict (got %s)",
                    type(updates).__name__,
                )
                return _all
            if acting_player_status is None:
                _logger.warning(
                    "CHANGE_PLAYER_STATE: caller did not provide acting_player_status; "
                    "skipping state merge"
                )
                return _all
            acting_player_status.merge_state(updates)
            return _all

        if et == InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK:
            # Phase 4-D-2: current_tick.value を player.state[state_key] に書き込む。
            # 「アイテム使用時刻を記録、N tick 後に reactive binding が解除」用。
            state_key = p.get("state_key")
            if not isinstance(state_key, str) or not state_key:
                _logger.warning(
                    "RECORD_PLAYER_STATE_TICK: state_key is required (got %r)",
                    state_key,
                )
                return _all
            if current_tick is None:
                _logger.warning(
                    "RECORD_PLAYER_STATE_TICK: caller did not provide current_tick; "
                    "skipping write to state[%r]",
                    state_key,
                )
                return _all
            if acting_player_status is None:
                _logger.warning(
                    "RECORD_PLAYER_STATE_TICK: caller did not provide "
                    "acting_player_status; skipping write to state[%r]",
                    state_key,
                )
                return _all
            acting_player_status.merge_state({state_key: int(current_tick.value)})
            return _all

        if et == InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK:
            # current_tick を target object の state[state_key] に書き込む。
            # 経時劣化 (#10) や資源回復 (#12) の reactive binding が
            # OBJECT_STATE_TICK_AT_LEAST predicate で経過 tick を判定するための
            # 「いつ起きたか」を記録するための effect。
            # current_tick が None（caller が tick を渡さなかった）の場合は
            # 黙って書き込まずに警告ログを出して継続する。
            state_key = p.get("state_key")
            if not isinstance(state_key, str) or not state_key:
                _logger.warning(
                    "RECORD_OBJECT_STATE_TICK: state_key is required (got %r)",
                    state_key,
                )
                return _all
            if current_tick is None:
                _logger.warning(
                    "RECORD_OBJECT_STATE_TICK: caller did not provide current_tick; "
                    "skipping write to state[%r]",
                    state_key,
                )
                return _all
            target = self._resolve_target_object(interior, acting_object, p)
            if target is None:
                return _all
            new_state = dict(target.state)
            new_state[state_key] = int(current_tick.value)
            updated_target = target.with_state(new_state)
            interior = interior.replace_object(updated_target)
            if (
                acting_object is not None
                and updated_target.object_id == acting_object.object_id
            ):
                acting_object = updated_target
            _all = (
                interior, acting_object, flags, grant, remove, messages,
                damage_specs, status_effect_specs, teleport_specs, atmosphere_update_specs, create_connection_specs, destroy_connection_specs, satisfy_need_specs, passage_specs,
            )
            return _all

        if et == InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE:
            cid_raw = p.get("connection_id")
            new_state = p.get("new_state")
            if cid_raw is not None and isinstance(new_state, str) and new_state:
                trav = p.get("traversable")
                sound = p.get("sound_permeability")
                passage_specs.append(
                    PassageStateUpdateSpec(
                        connection_id=int(cid_raw),
                        new_state=new_state,
                        traversable_override=bool(trav) if trav is not None else None,
                        sound_permeability_override=float(sound) if sound is not None else None,
                    )
                )
            return _all

        raise UnsupportedInteractionEffectException(f"Unsupported interaction effect: {et.value}")

    @staticmethod
    def _resolve_target_object(
        interior: SpotInterior,
        acting_object: SpotObject | None,
        params: dict[str, Any],
    ) -> SpotObject | None:
        target_raw = params.get("object_id")
        if target_raw is None:
            return acting_object
        target_id = WorldGraphEffectService._spot_object_id_from_param(target_raw)
        target = interior.get_object(target_id)
        return target or acting_object

    @staticmethod
    def _read_quantity(params: dict[str, Any]) -> int:
        """effect parameters から quantity を読む。default=1、負値は 0 にクランプ。

        Phase 2-A の数量セマンティクス。GIVE_ITEM / REMOVE_ITEM が 1 effect で
        複数 instance を扱えるようにするため。シナリオが quantity を書かない
        場合は既存挙動 (1 個) を維持する。
        """
        raw = params.get("quantity", 1)
        try:
            n = int(raw)
        except (TypeError, ValueError):
            return 1
        return max(0, n)

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
