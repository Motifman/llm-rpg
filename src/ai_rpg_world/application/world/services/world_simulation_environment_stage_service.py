import logging
from typing import Callable, Dict, List

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.weather_zone_repository import WeatherZoneRepository
from ai_rpg_world.domain.world.service.weather_config_service import WeatherConfigService
from ai_rpg_world.domain.world.service.weather_simulation_service import (
    WeatherSimulationService,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState


class WorldSimulationEnvironmentStageService:
    """天候更新とマップへの同期を扱う stage service。"""

    def __init__(
        self,
        weather_zone_repository: WeatherZoneRepository,
        weather_config_service: WeatherConfigService,
        logger: logging.Logger,
        weather_config_service_getter: Callable[[], WeatherConfigService] | None = None,
    ) -> None:
        self._weather_zone_repository = weather_zone_repository
        self._weather_config_service = weather_config_service
        self._weather_config_service_getter = weather_config_service_getter
        self._logger = logger

    def run(
        self,
        current_tick: WorldTick,
        maps: List[PhysicalMapAggregate],
    ) -> None:
        latest_weather = self._update_weather_if_needed(current_tick)
        for physical_map in maps:
            self._sync_weather_to_map(physical_map, latest_weather)

    def _update_weather_if_needed(
        self, current_tick: WorldTick
    ) -> Dict[SpotId, WeatherState]:
        latest_weather: Dict[SpotId, WeatherState] = {}
        weather_config_service = (
            self._weather_config_service_getter()
            if self._weather_config_service_getter is not None
            else self._weather_config_service
        )
        interval = weather_config_service.get_update_interval_ticks()

        try:
            zones = self._weather_zone_repository.find_all()
            if not zones:
                self._logger.debug("No weather zones found")
                return latest_weather

            for zone in zones:
                if current_tick.value % interval == 0:
                    try:
                        new_state = WeatherSimulationService.simulate_next_weather(
                            zone.current_state
                        )
                        zone.change_weather(new_state)
                        self._weather_zone_repository.save(zone)
                        self._logger.info(
                            "Weather updated in zone %s to %s",
                            zone.zone_id,
                            new_state.weather_type,
                        )
                    except DomainException as exc:
                        self._logger.error(
                            "Weather transition rule violation in zone %s: %s",
                            zone.zone_id,
                            str(exc),
                        )
                    except Exception as exc:
                        self._logger.error(
                            "Unexpected error updating weather for zone %s: %s",
                            zone.zone_id,
                            str(exc),
                            exc_info=True,
                        )

                for spot_id in zone.spot_ids:
                    latest_weather[spot_id] = zone.current_state
        except Exception as exc:
            self._logger.error("Failed to retrieve weather zones: %s", str(exc))

        return latest_weather

    def _sync_weather_to_map(
        self,
        physical_map: PhysicalMapAggregate,
        latest_weather: Dict[SpotId, WeatherState],
    ) -> None:
        if physical_map.spot_id in latest_weather:
            physical_map.set_weather(latest_weather[physical_map.spot_id])
            return

        try:
            zone = self._weather_zone_repository.find_by_spot_id(physical_map.spot_id)
            if zone:
                physical_map.set_weather(zone.current_state)
            else:
                physical_map.set_weather(WeatherState.clear())
        except DomainException as exc:
            self._logger.error(
                "Domain error syncing weather to map %s: %s",
                physical_map.spot_id,
                str(exc),
            )
            physical_map.set_weather(WeatherState.clear())
        except Exception as exc:
            self._logger.error(
                "Unexpected error syncing weather to map %s: %s",
                physical_map.spot_id,
                str(exc),
                exc_info=True,
            )
            physical_map.set_weather(WeatherState.clear())
