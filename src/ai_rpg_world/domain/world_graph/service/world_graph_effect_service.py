from __future__ import annotations

from typing import Iterable, Mapping, Optional, Tuple

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionEffectValidationException,
)
from ai_rpg_world.domain.world_graph.service.effect_application.context import (
    EffectApplicationState,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers import (
    build_effect_handlers,
)
from ai_rpg_world.domain.world_graph.service.effect_application.handlers.messages import (
    SIGN_AUTHOR_STATE_KEY,
    SIGN_HIDDEN_STATE_KEYS,
    SIGN_TEXT_MAX_LENGTH,
    SIGN_TEXT_STATE_KEY,
    SIGN_WRITTEN_TICK_STATE_KEY,
)
from ai_rpg_world.domain.world_graph.service.effect_application.item_transfer import (
    item_removals_for_effect,
)
from ai_rpg_world.domain.world_graph.service.effect_application.registry import (
    dispatch_effect,
)
from ai_rpg_world.domain.world_graph.service.effect_application.visibility import (
    DEFAULT_VISIBILITY as _DEFAULT_VISIBILITY,
    resolve_visibility as _resolve_visibility,
    validate_default_visibility_coverage as _validate_default_visibility_coverage,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.world_graph_effect_result import (
    ItemRemovalRequirements,
    WorldGraphEffectResult,
)

# テスト・呼び出し元が world_graph_effect_service から import している定数を再 export
__all__ = [
    "SIGN_TEXT_MAX_LENGTH",
    "SIGN_TEXT_STATE_KEY",
    "SIGN_AUTHOR_STATE_KEY",
    "SIGN_WRITTEN_TICK_STATE_KEY",
    "SIGN_HIDDEN_STATE_KEYS",
    "WorldGraphEffectService",
]


class WorldGraphEffectService:
    """Interaction / Scenario Event 共通の effect 適用サービス。"""

    def __init__(
        self,
        loot_table_repository: Optional[LootTableRepository] = None,
        ongoing_condition_resolutions: Optional[
            Mapping[str, Tuple[InteractionEffect, ...]]
        ] = None,
    ) -> None:
        # PR #1 動的 loot: GIVE_FROM_LOOT_TABLE effect の抽選で使う repository。
        # None なら GIVE_FROM_LOOT_TABLE は no-op (silent skip ではなく log)。
        # 既存 caller は kwarg 省略で従来挙動を維持する。
        self._loot_table_repository = loot_table_repository
        self._ongoing_condition_resolutions = dict(
            ongoing_condition_resolutions or {}
        )
        self._handlers = build_effect_handlers()

    def _expand_ongoing_condition_resolutions(
        self,
        effects: Iterable[InteractionEffect],
        *,
        resolving: frozenset[str] = frozenset(),
    ) -> Tuple[InteractionEffect, ...]:
        """異常解除の参照を、シナリオが一箇所で宣言した flag 効果へ展開する。"""
        expanded: list[InteractionEffect] = []
        for effect in effects:
            if (
                effect.effect_type
                is not InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION
            ):
                expanded.append(effect)
                continue
            flag = effect.parameters.get("flag")
            if not isinstance(flag, str) or not flag:
                raise InteractionEffectValidationException(
                    "RESOLVE_ONGOING_CONDITION requires parameters.flag"
                )
            resolution = self._ongoing_condition_resolutions.get(flag)
            if not resolution:
                raise InteractionEffectValidationException(
                    "RESOLVE_ONGOING_CONDITION が参照する異常に resolution が"
                    f"ありません: flag={flag!r}"
                )
            if flag in resolving:
                raise InteractionEffectValidationException(
                    "ongoing condition resolution が循環しています: "
                    f"flag={flag!r}"
                )
            expanded.extend(
                self._expand_ongoing_condition_resolutions(
                    resolution,
                    resolving=resolving | {flag},
                )
            )
        return tuple(expanded)

    def plan_item_removals(
        self,
        *,
        interior: SpotInterior,
        acting_object: SpotObject | None,
        effects: Iterable[InteractionEffect],
        interaction_parameters: Optional[dict] = None,
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
        target_player_status: Optional[PlayerStatusAggregate] = None,
    ) -> ItemRemovalRequirements:
        """集約変更や抽選を行わず、効果が要求する品目削除だけを解決する。"""
        actor: list[ItemSpecId] = []
        target: list[ItemSpecId] = []
        for effect in self._expand_ongoing_condition_resolutions(effects):
            actor_items, target_items = item_removals_for_effect(
                interior=interior,
                acting_object=acting_object,
                effect=effect,
                interaction_parameters=interaction_parameters,
                owned_item_spec_counts=owned_item_spec_counts,
                target_player_status=target_player_status,
            )
            actor.extend(actor_items)
            target.extend(target_items)
        return ItemRemovalRequirements(tuple(actor), tuple(target))

    def apply_effects(
        self,
        *,
        interior: SpotInterior,
        acting_object: SpotObject | None,
        effects: Iterable[InteractionEffect],
        world_flags: frozenset[str],
        current_tick: Optional[WorldTick] = None,
        acting_item_aggregate: Optional[ItemAggregate] = None,
        target_item_aggregate: Optional[ItemAggregate] = None,
        acting_player_status: Optional[PlayerStatusAggregate] = None,
        # 対人 interaction の対象プレイヤー。``target=TARGET_PLAYER`` の effect
        # が「誰に」効くかを決める。渡さないまま TARGET_PLAYER の effect が来た
        # ら、行為者へフォールバックせず例外で止める (§静かな失敗の回避)。
        target_player_status: Optional[PlayerStatusAggregate] = None,
        interaction_parameters: Optional[dict] = None,
        acting_player_display_name: Optional[str] = None,
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
    ) -> WorldGraphEffectResult:
        if (
            acting_item_aggregate is not None
            and acting_item_aggregate is target_item_aggregate
        ):
            raise ValueError(
                "acting_item_aggregate and target_item_aggregate must be distinct "
                "instances; passing the same aggregate as both indicates a wiring bug"
            )

        initial_item_state = (
            dict(acting_item_aggregate.state)
            if acting_item_aggregate is not None
            else None
        )
        initial_target_item_state = (
            dict(target_item_aggregate.state)
            if target_item_aggregate is not None
            else None
        )
        initial_player_state = (
            dict(acting_player_status.state)
            if acting_player_status is not None
            else None
        )

        ctx = EffectApplicationState(
            interior=interior,
            acting_object=acting_object,
            flags=set(world_flags),
            current_tick=current_tick,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
            acting_player_status=acting_player_status,
            target_player_status=target_player_status,
            interaction_parameters=interaction_parameters,
            acting_player_display_name=acting_player_display_name,
            owned_item_spec_counts=owned_item_spec_counts,
            loot_table_repository=self._loot_table_repository,
        )

        for effect in self._expand_ongoing_condition_resolutions(effects):
            dispatch_effect(self._handlers, effect, ctx)

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

        actor_direct = tuple(
            s for s in ctx.summaries if s.visibility == EffectVisibility.ACTOR_DIRECT
        )
        public_observable = tuple(
            s
            for s in ctx.summaries
            if s.visibility == EffectVisibility.PUBLIC_OBSERVABLE
        )
        hidden = tuple(
            s for s in ctx.summaries if s.visibility == EffectVisibility.HIDDEN
        )

        return WorldGraphEffectResult(
            new_interior=ctx.interior,
            updated_object_id=(
                ctx.acting_object.object_id.value
                if ctx.acting_object is not None
                else None
            ),
            new_flags=frozenset(ctx.flags),
            messages=tuple(ctx.messages),
            item_spec_ids_to_grant=tuple(ctx.grant),
            item_spec_ids_to_remove=tuple(ctx.remove),
            target_item_spec_ids_to_grant=tuple(ctx.target_grant),
            target_item_spec_ids_to_remove=tuple(ctx.target_remove),
            damage_specs=tuple(ctx.damage_specs),
            target_damage_specs=tuple(ctx.target_damage_specs),
            status_effect_specs=tuple(ctx.status_effect_specs),
            teleport_specs=tuple(ctx.teleport_specs),
            atmosphere_update_specs=tuple(ctx.atmosphere_update_specs),
            create_connection_specs=tuple(ctx.create_connection_specs),
            destroy_connection_specs=tuple(ctx.destroy_connection_specs),
            satisfy_need_specs=tuple(ctx.satisfy_need_specs),
            passage_state_updates=tuple(ctx.passage_specs),
            meeting_call_triggers=tuple(ctx.meeting_calls),
            room_occupancy_display_specs=tuple(ctx.room_occupancy_display_specs),
            item_instance_state_changed=item_instance_state_changed,
            target_item_instance_state_changed=target_item_instance_state_changed,
            acting_player_state_changed=acting_player_state_changed,
            actor_direct_effects=actor_direct,
            public_observable_effects=public_observable,
            hidden_effects=hidden,
        )
