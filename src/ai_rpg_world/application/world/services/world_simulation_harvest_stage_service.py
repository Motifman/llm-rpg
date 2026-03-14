import logging
from typing import Any, Callable, List, Optional

from ai_rpg_world.application.harvest.contracts.commands import FinishHarvestCommand
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException


class WorldSimulationHarvestStageService:
    """採取完了の自動進行を扱う stage service。"""

    def __init__(
        self,
        harvest_command_service_getter: Callable[[], Optional[Any]],
        logger: logging.Logger,
    ) -> None:
        self._harvest_command_service_getter = harvest_command_service_getter
        self._logger = logger

    def run(
        self,
        maps: List[PhysicalMapAggregate],
        current_tick: WorldTick,
    ) -> None:
        finish_harvest = getattr(
            self._harvest_command_service_getter(),
            "finish_harvest_in_current_unit_of_work",
            None,
        )
        if not callable(finish_harvest):
            return

        for physical_map in maps:
            for obj in physical_map.get_all_objects():
                component = getattr(obj, "component", None)
                if not isinstance(component, HarvestableComponent):
                    continue
                if component.current_actor_id is None or component.harvest_finish_tick is None:
                    continue
                if component.harvest_finish_tick > current_tick:
                    continue

                try:
                    actor = physical_map.get_actor(component.current_actor_id)
                except ObjectNotFoundException:
                    self._logger.warning(
                        "Skipping auto-complete harvest without actor: target_id=%s",
                        obj.object_id,
                    )
                    continue

                if actor.player_id is None:
                    continue

                try:
                    finish_harvest(
                        FinishHarvestCommand(
                            actor_id=str(int(actor.player_id)),
                            target_id=str(int(obj.object_id)),
                            spot_id=str(int(physical_map.spot_id)),
                            current_tick=current_tick.value,
                        )
                    )
                except Exception as exc:
                    self._logger.warning(
                        "Auto harvest completion failed: spot_id=%s actor_id=%s target_id=%s error=%s",
                        int(physical_map.spot_id),
                        int(actor.player_id),
                        int(obj.object_id),
                        exc,
                    )
