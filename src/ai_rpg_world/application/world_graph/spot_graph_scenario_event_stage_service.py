from __future__ import annotations

from typing import Callable, Iterable, Optional

from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    grant_item_specs_to_inventory,
    remove_one_item_of_spec_from_inventory,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository


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
        self._condition_evaluator = ScenarioConditionEvaluator(
            world_flag_state=world_flag_state,
            spot_interior_repository=spot_interior_repository,
            player_status_repository=player_status_repository,
            player_inventory_repository=player_inventory_repository,
            item_repository=item_repository,
        )

    def set_message_callback(self, callback: Optional[Callable[[ScenarioEventDef, str], None]]) -> None:
        self._on_message = callback

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
            if not self._matches_conditions(event.conditions, current_tick):
                continue
            self._apply_event(event)
            if event.once:
                self._progress_store.mark_fired(event.event_id)
            self._schedule_next_if_chained(event, current_tick)

        # 2. スケジュール済みチェーンイベントの発火
        for due_id in self._progress_store.due_event_ids(current_tick.value):
            self._progress_store.unschedule(due_id)
            chained = events_by_id.get(due_id)
            if chained is None:
                continue
            if chained.once and self._progress_store.is_fired(due_id):
                continue
            self._apply_event(chained)
            if chained.once:
                self._progress_store.mark_fired(due_id)
            self._schedule_next_if_chained(chained, current_tick)

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
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
    ) -> bool:
        """conditions の全てが真なら True（暗黙の AND）。"""
        graph = self._spot_graph_repository.find_graph()
        return self._condition_evaluator.evaluate_all(conditions, current_tick, graph)

    def _apply_event(self, event: ScenarioEventDef) -> None:
        acting_object = self._resolve_acting_object(event)
        graph = self._spot_graph_repository.find_graph()
        if acting_object is None:
            from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior

            base_interior = SpotInterior.empty()
            owner_spot = None
        else:
            base_interior = self._interior_for_object(acting_object.object_id)
            owner_spot = self._find_owner_spot_id(acting_object.object_id)
        effect_result = self._effect_service.apply_effects(
            interior=base_interior,
            acting_object=acting_object,
            effects=event.effects,
            world_flags=self._world_flag_state.as_frozen_set(),
        )
        self._world_flag_state.replace_from_interaction(effect_result.new_flags)

        if owner_spot is not None:
            self._spot_interior_repository.save(owner_spot, effect_result.new_interior)
        for spec in effect_result.passage_state_updates:
            graph.set_connection_passage_state(
                ConnectionId.create(spec.connection_id),
                spec.new_state,
                traversable_override=spec.traversable_override,
                sound_permeability_override=spec.sound_permeability_override,
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

        self._spot_graph_repository.save(graph)

        if effect_result.item_spec_ids_to_grant:
            for status in self._player_status_repository.find_all():
                grant_item_specs_to_inventory(
                    status.player_id,
                    tuple(effect_result.item_spec_ids_to_grant),
                    self._item_repository,
                    self._item_spec_repository,
                    self._player_inventory_repository,
                )
        if effect_result.item_spec_ids_to_remove:
            for status in self._player_status_repository.find_all():
                inv = self._player_inventory_repository.find_by_id(status.player_id)
                if inv is None:
                    continue
                for spec in effect_result.item_spec_ids_to_remove:
                    remove_one_item_of_spec_from_inventory(inv, spec, self._item_repository)
                self._player_inventory_repository.save(inv)

        if self._on_message is not None:
            for msg in effect_result.messages:
                self._on_message(event, msg)

    def _resolve_acting_object(self, event: ScenarioEventDef):
        for cond in event.conditions:
            if cond.object_id is not None:
                obj = self._find_object(SpotObjectId.create(cond.object_id))
                if obj is not None:
                    return obj
        for eff in event.effects:
            oid = eff.parameters.get("object_id")
            if oid is None:
                continue
            obj = self._find_object(SpotObjectId.create(oid))
            if obj is not None:
                return obj
        return None

    def _find_owner_spot_id(self, object_id: SpotObjectId) -> Optional[SpotId]:
        graph = self._spot_graph_repository.find_graph()
        for node in graph.iter_spot_nodes():
            interior = self._spot_interior_repository.find_by_spot_id(node.spot_id)
            if interior is None:
                continue
            if interior.get_object(object_id) is not None:
                return node.spot_id
        return None

    def _interior_for_object(self, object_id: SpotObjectId):
        owner_spot = self._find_owner_spot_id(object_id)
        if owner_spot is None:
            raise ValueError(f"Object not found in any interior: {object_id}")
        interior = self._spot_interior_repository.find_by_spot_id(owner_spot)
        if interior is None:
            raise ValueError(f"Interior not found for object: {object_id}")
        return interior

    def _find_object(self, object_id: SpotObjectId):
        owner_spot = self._find_owner_spot_id(object_id)
        if owner_spot is None:
            return None
        interior = self._spot_interior_repository.find_by_spot_id(owner_spot)
        if interior is None:
            return None
        return interior.get_object(object_id)
