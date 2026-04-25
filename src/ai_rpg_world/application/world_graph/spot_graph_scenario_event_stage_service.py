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
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
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

    def set_message_callback(self, callback: Optional[Callable[[ScenarioEventDef, str], None]]) -> None:
        self._on_message = callback

    def run(self, current_tick: WorldTick) -> None:
        if not self._scenario_events:
            return
        for event in self._scenario_events:
            if event.trigger != "ON_TICK":
                continue
            if event.once and self._progress_store.is_fired(event.event_id):
                continue
            if not self._matches_conditions(event.conditions, current_tick):
                continue
            self._apply_event(event)
            if event.once:
                self._progress_store.mark_fired(event.event_id)

    def _matches_conditions(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
    ) -> bool:
        world_flags = self._world_flag_state.as_frozen_set()
        graph = self._spot_graph_repository.find_graph()
        for cond in conditions:
            ctype = cond.condition_type
            if ctype == "TICK_AT_LEAST":
                if cond.tick is None or current_tick.value < int(cond.tick):
                    return False
                continue
            if ctype == "TICK_BETWEEN":
                if cond.tick_start is None or cond.tick_end is None:
                    return False
                if not (int(cond.tick_start) <= current_tick.value <= int(cond.tick_end)):
                    return False
                continue
            if ctype == "FLAG_SET":
                if not cond.flag_name or cond.flag_name not in world_flags:
                    return False
                continue
            if ctype == "FLAG_NOT_SET":
                if not cond.flag_name or cond.flag_name in world_flags:
                    return False
                continue
            if ctype == "PLAYER_AT_SPOT":
                if cond.spot_id is None:
                    return False
                spot_id = SpotId.create(cond.spot_id)
                presence = graph.presence_at(spot_id)
                if not presence.present_entity_ids:
                    return False
                continue
            if ctype == "OBJECT_STATE":
                if cond.object_id is None or cond.required_state is None:
                    return False
                obj = self._find_object(SpotObjectId.create(cond.object_id))
                if obj is None:
                    return False
                for k, v in cond.required_state.items():
                    if obj.state.get(k) != v:
                        return False
                continue
            if ctype == "HAS_ITEM":
                if cond.item_spec_id is None:
                    return False
                target_spec = cond.item_spec_id
                has_item = False
                for status in self._player_status_repository.find_all():
                    inv = self._player_inventory_repository.find_by_id(status.player_id)
                    if inv is None:
                        continue
                    owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)
                    if any(spec.value == target_spec for spec in owned):
                        has_item = True
                        break
                if not has_item:
                    return False
                continue
            return False
        return True

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
        for cid, is_passable in effect_result.connection_passability_updates:
            graph.set_connection_passable(cid, is_passable)
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
