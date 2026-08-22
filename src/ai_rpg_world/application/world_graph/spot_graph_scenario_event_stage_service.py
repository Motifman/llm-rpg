from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import CommandPostCommitException

from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
    remove_items_of_specs_from_inventory,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.scenario_predicate_trace_emitter import (
    ScenarioPredicateTraceEmitter,
)
from ai_rpg_world.application.world_graph.spot_object_lookup import (
    find_object_in_graph,
    find_owner_spot_id,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandContext
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.interaction_command_repository_provider import (
        InteractionCommandRepositoryProviderPort,
    )


class _CommandContextEventPublisher:
    """既存publish_all入口をevent commandの収集口へ適合させる。"""

    def __init__(self, context: "CommandContext") -> None:
        self._context = context

    def publish_all(self, events: Iterable[Any]) -> None:
        self._context.collect_all(events)


class SpotGraphScenarioEventStageService:
    """tickごとにシナリオ自律イベントを評価・適用する。"""

    def __init__(
        self,
        *,
        scenario_events: Iterable[ScenarioEventDef],
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        world_flag_state: MutableWorldFlagState,
        progress_store: Optional[InMemorySpotGraphScenarioEventProgressStore] = None,
        effect_service: Optional[WorldGraphEffectService] = None,
        on_message: Optional[Callable[[ScenarioEventDef, str], None]] = None,
        condition_evaluator: Optional[ScenarioConditionEvaluator] = None,
        predicate_trace_emitter: Optional[ScenarioPredicateTraceEmitter] = None,
        overflow_sink: Any = None,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[InteractionCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        self._scenario_events = tuple(scenario_events)
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._world_flag_state = world_flag_state
        self._progress_store = progress_store or InMemorySpotGraphScenarioEventProgressStore()
        self._effect_service = effect_service or WorldGraphEffectService()
        self._on_message = on_message
        self._predicate_trace_emitter = predicate_trace_emitter
        # 評価器は外部注入を許容（reactive_binding_stage と共有するため）。
        # 渡されなければ自前で生成。
        self._condition_evaluator = condition_evaluator or ScenarioConditionEvaluator(
            world_flag_state=world_flag_state,
            spot_interior_repository=spot_interior_repository,
            player_status_repository=player_status_repository,
            player_inventory_repository=player_inventory_repository,
            item_repository=item_repository,
        )
        self._condition_evaluator.validate_dependencies(
            condition
            for event in self._scenario_events
            for condition in event.conditions
        )
        self._overflow_sink = overflow_sink
        self._command_scope_factory = command_scope_factory

    def set_message_callback(self, callback: Optional[Callable[[ScenarioEventDef, str], None]]) -> None:
        self._on_message = callback

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[InteractionCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageをevent定義1件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        if not self._scenario_events:
            return
        events_by_id = {e.event_id: e for e in self._scenario_events}

        # 1. 通常のtick駆動イベント評価（スケジュール済みはスキップ）
        for event in self._scenario_events:
            if event.trigger != "ON_TICK":
                continue
            # スケジュール済みイベントはチェーン経由で発火するためスキップ
            if self._progress_store.is_scheduled(event.event_id):
                continue
            if event.once and self._progress_store.is_fired(event.event_id):
                continue
            if not self._matches_conditions(event, current_tick):
                continue
            self._run_event_command(event, current_tick)

        # 2. スケジュール済みチェーンイベントの発火
        for due_id in self._progress_store.due_event_ids(current_tick.value):
            chained = events_by_id.get(due_id)
            if chained is None:
                self._discard_scheduled_event(due_id)
                continue
            if chained.once and self._progress_store.is_fired(due_id):
                self._discard_scheduled_event(due_id)
                continue
            self._run_event_command(
                chained,
                current_tick,
                scheduled_event_id=due_id,
            )

    def _run_event_command(
        self,
        event: ScenarioEventDef,
        current_tick: WorldTick,
        *,
        scheduled_event_id: str | None = None,
    ) -> None:
        """event定義1件の効果・進捗・eventを一つのscopeで確定する。"""
        if self._command_scope_factory is None:
            if scheduled_event_id is not None:
                self._progress_store.unschedule(scheduled_event_id)
            messages = self._apply_event(
                event,
                current_tick,
                spot_graph_repository=self._spot_graph_repository,
                spot_interior_repository=self._spot_interior_repository,
                player_status_repository=self._player_status_repository,
                player_inventory_repository=self._player_inventory_repository,
                item_repository=self._item_repository,
                item_spec_repository=self._item_spec_repository,
                event_publisher=None,
                overflow_sink=self._overflow_sink,
            )
            self._record_event_progress(event, current_tick)
            self._notify_committed_messages(event, messages)
            return

        messages: tuple[str, ...] = ()
        try:
            with self._command_scope_factory.create() as context:
                repositories = context.repositories
                event_publisher = _CommandContextEventPublisher(context)
                overflow_sink = self._overflow_sink
                if hasattr(overflow_sink, "bind_to_command"):
                    overflow_sink = overflow_sink.bind_to_command(
                        spot_graph_repository=repositories.spot_graph,
                        spot_interior_repository=repositories.spot_interiors,
                        item_repository=repositories.items,
                        item_spec_repository=repositories.item_specs,
                        event_publisher=event_publisher,
                    )
                if scheduled_event_id is not None:
                    self._progress_store.unschedule(scheduled_event_id)
                messages = self._apply_event(
                    event,
                    current_tick,
                    spot_graph_repository=repositories.spot_graph,
                    spot_interior_repository=repositories.spot_interiors,
                    player_status_repository=repositories.player_statuses,
                    player_inventory_repository=repositories.player_inventories,
                    item_repository=repositories.items,
                    item_spec_repository=repositories.item_specs,
                    event_publisher=event_publisher,
                    overflow_sink=overflow_sink,
                )
                self._record_event_progress(event, current_tick)
        except CommandPostCommitException:
            self._notify_committed_messages(event, messages)
            raise
        self._notify_committed_messages(event, messages)

    def _record_event_progress(
        self, event: ScenarioEventDef, current_tick: WorldTick
    ) -> None:
        if event.once:
            self._progress_store.mark_fired(event.event_id)
        self._schedule_next_if_chained(event, current_tick)

    def _discard_scheduled_event(self, event_id: str) -> None:
        """定義なし・発火済みの予約だけを安全に取り除く。"""
        if self._command_scope_factory is None:
            self._progress_store.unschedule(event_id)
            return
        with self._command_scope_factory.create():
            self._progress_store.unschedule(event_id)

    def _notify_committed_messages(
        self, event: ScenarioEventDef, messages: tuple[str, ...]
    ) -> None:
        """確定済みeventのmessageを最善努力で通知する。"""
        if self._on_message is None:
            return
        for message in messages:
            try:
                self._on_message(event, message)
            except Exception:  # noqa: BLE001 - commit済み観測は業務結果を戻さない
                logging.getLogger(__name__).warning(
                    "scenario_event message callback failed after commit: event_id=%s",
                    event.event_id,
                    exc_info=True,
                )

    def _schedule_next_if_chained(
        self, event: ScenarioEventDef, current_tick: WorldTick
    ) -> None:
        """イベントにチェーン設定があれば次のイベントをスケジュールする。

        delay_ticks=0 の場合、次の run() 呼び出しで発火する（同一 run() 内では発火しない）。
        """
        if event.next_event_id:
            fire_at = current_tick.value + event.delay_ticks
            self._progress_store.schedule(event.next_event_id, fire_at)

    def _matches_conditions(
        self,
        event: ScenarioEventDef,
        current_tick: WorldTick,
    ) -> bool:
        """conditions の全てが真なら True（暗黙の AND）。"""
        graph = self._spot_graph_repository.find_graph()
        evaluation = self._condition_evaluator.evaluate_all_diagnostic(
            event.conditions, current_tick, graph,
        )
        result = evaluation.result
        if self._predicate_trace_emitter is not None:
            self._predicate_trace_emitter.emit(
                evaluation=evaluation,
                root_condition_type="IMPLICIT_AND",
                current_tick=current_tick,
                purpose="scenario_event_conditions",
                owner_id=event.event_id,
            )
        return result.is_satisfied

    def _apply_event(
        self,
        event: ScenarioEventDef,
        current_tick: WorldTick,
        *,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        event_publisher: Any | None,
        overflow_sink: Any,
    ) -> tuple[str, ...]:
        acting_object = self._resolve_acting_object(
            event,
            spot_graph_repository=spot_graph_repository,
            spot_interior_repository=spot_interior_repository,
        )
        graph = spot_graph_repository.find_graph()
        if acting_object is None:
            from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior

            base_interior = SpotInterior.empty()
            owner_spot = None
        else:
            base_interior = self._interior_for_object(
                acting_object.object_id,
                spot_graph_repository=spot_graph_repository,
                spot_interior_repository=spot_interior_repository,
            )
            owner_spot = self._find_owner_spot_id(
                acting_object.object_id,
                spot_graph_repository=spot_graph_repository,
                spot_interior_repository=spot_interior_repository,
            )
        effect_result = self._effect_service.apply_effects(
            interior=base_interior,
            acting_object=acting_object,
            effects=event.effects,
            world_flags=self._world_flag_state.as_frozen_set(),
            current_tick=current_tick,
        )
        self._world_flag_state.replace_from_interaction(
            effect_result.new_flags,
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SCENARIO_EVENT,
                actor_player_id=None,
            ),
        )

        if owner_spot is not None:
            spot_interior_repository.save(owner_spot, effect_result.new_interior)
        for spec in effect_result.passage_state_updates:
            graph.set_connection_passage_state(
                ConnectionId.create(spec.connection_id),
                spec.new_state,
                traversable_override=spec.traversable_override,
                sound_permeability_override=spec.sound_permeability_override,
                cause=PassageChangeCauseEnum.SCENARIO_EVENT,
                # Issue #183: scenario_event は世界タイマ / scripted trigger 由来。
                # 起点に明確な actor が居ないため None。
                actor_entity_id=None,
            )

        # CHANGE_ATMOSPHERE: interaction 経由と同じ効果を scenario_event からも
        # 適用する。停電や気温低下は「誰かが操作した結果」だけでなく「時刻や
        # 条件で世界の側が変わる」形でも起きるので、こちらの入口を塞いだままだと
        # ON_TICK で照明を落とす表現が書けない。
        for spec in effect_result.atmosphere_update_specs:
            graph.update_spot_atmosphere(
                SpotId.create(spec.spot_id),
                lighting=(
                    LightingEnum[spec.lighting] if spec.lighting is not None else None
                ),
                temperature=(
                    TemperatureEnum[spec.temperature]
                    if spec.temperature is not None
                    else None
                ),
                hazard_level=spec.hazard_level,
                hazard_description=spec.hazard_description,
            )

        # 未消費の spec を黙って捨てない。scenario_event には行為者が居ないため、
        # TELEPORT_ENTITY (誰を飛ばすのか決まらない) はこの経路では意味を持てない。
        # 書いたのに何も起きないまま気づけない状態を避けるため警告を残す。
        if effect_result.teleport_specs:
            logging.getLogger(__name__).warning(
                "scenario_event %s declares TELEPORT_ENTITY but scenario events have "
                "no acting player; the teleport is ignored "
                "(移動させたい対象が決まらないため、この効果は scenario_events では"
                "使えません。interaction 側に書いてください)",
                getattr(event, "event_id", "<unknown>"),
            )

        for spec in effect_result.destroy_connection_specs:
            graph.remove_connection(ConnectionId.create(spec.connection_id))

        for spec in effect_result.create_connection_specs:
            max_id = graph.max_connection_id_value()
            new_cid = ConnectionId.create(max_id + 1)
            new_conn = SpotConnection(
                connection_id=new_cid,
                from_spot_id=SpotId.create(spec.from_spot_id),
                to_spot_id=SpotId.create(spec.to_spot_id),
                name=spec.connection_name,
                description=spec.description,
                travel_ticks=spec.travel_ticks,
                is_bidirectional=spec.is_bidirectional,
                passage=spec.passage,
            )
            rev_id = ConnectionId.create(max_id + 2) if spec.is_bidirectional else None
            graph.add_connection_dynamic(new_conn, reverse_connection_id=rev_id)

        graph_events: tuple[Any, ...] = ()
        if event_publisher is not None:
            graph_events = tuple(graph.get_events())
            graph.clear_events()
        spot_graph_repository.save(graph)
        if graph_events and event_publisher is not None:
            event_publisher.publish_all(graph_events)

        if effect_result.item_spec_ids_to_grant:
            for status in player_status_repository.find_all():
                grant_item_specs_to_inventory(
                    status.player_id,
                    tuple(effect_result.item_spec_ids_to_grant),
                    item_repository,
                    item_spec_repository,
                    player_inventory_repository,
                    overflow_sink=overflow_sink,
                )
        if effect_result.item_spec_ids_to_remove:
            for status in player_status_repository.find_all():
                inv = player_inventory_repository.find_by_id(status.player_id)
                if inv is None:
                    continue
                remove_items_of_specs_from_inventory(
                    inv,
                    effect_result.item_spec_ids_to_remove,
                    item_repository,
                )
                player_inventory_repository.save(inv)

        return tuple(effect_result.messages)

    def _resolve_acting_object(
        self,
        event: ScenarioEventDef,
        *,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
    ):
        for cond in event.conditions:
            if cond.object_id is not None:
                obj = self._find_object(
                    SpotObjectId.create(cond.object_id),
                    spot_graph_repository=spot_graph_repository,
                    spot_interior_repository=spot_interior_repository,
                )
                if obj is not None:
                    return obj
        for eff in event.effects:
            oid = eff.parameters.get("object_id")
            if oid is None:
                continue
            obj = self._find_object(
                SpotObjectId.create(oid),
                spot_graph_repository=spot_graph_repository,
                spot_interior_repository=spot_interior_repository,
            )
            if obj is not None:
                return obj
        return None

    def _find_owner_spot_id(
        self,
        object_id: SpotObjectId,
        *,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
    ) -> Optional[SpotId]:
        graph = spot_graph_repository.find_graph()
        return find_owner_spot_id(object_id, graph, spot_interior_repository)

    def _interior_for_object(
        self,
        object_id: SpotObjectId,
        *,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
    ):
        owner_spot = self._find_owner_spot_id(
            object_id,
            spot_graph_repository=spot_graph_repository,
            spot_interior_repository=spot_interior_repository,
        )
        if owner_spot is None:
            raise ValueError(f"Object not found in any interior: {object_id}")
        interior = spot_interior_repository.find_by_spot_id(owner_spot)
        if interior is None:
            raise ValueError(f"Interior not found for object: {object_id}")
        return interior

    def _find_object(
        self,
        object_id: SpotObjectId,
        *,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
    ):
        graph = spot_graph_repository.find_graph()
        return find_object_in_graph(object_id, graph, spot_interior_repository)
