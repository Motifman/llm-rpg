import logging
from typing import Dict

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService


class WorldSimulationEnvironmentEffectService:
    """環境効果の一括適用を扱う service。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        logger: logging.Logger,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._logger = logger

    def apply_bulk(
        self,
        player_map_map: Dict[PlayerId, PhysicalMapAggregate],
    ) -> None:
        player_ids = list(player_map_map.keys())
        try:
            player_statuses = self._player_status_repository.find_by_ids(player_ids)
            status_map = {status.player_id: status for status in player_statuses}
            updated_statuses = []

            for player_id, physical_map in player_map_map.items():
                player_status = status_map.get(player_id)
                if not player_status:
                    self._logger.warning(
                        "Player status not found for player %s",
                        player_id,
                    )
                    continue

                if not player_status.can_act():
                    continue

                drain = WeatherEffectService.calculate_environmental_stamina_drain(
                    physical_map.weather_state,
                    physical_map.environment_type,
                )
                if drain <= 0 or player_status.stamina.value <= 0:
                    continue

                actual_drain = min(player_status.stamina.value, drain)
                try:
                    player_status.consume_stamina(actual_drain)
                    updated_statuses.append(player_status)
                except DomainException as exc:
                    self._logger.warning(
                        "Could not apply environmental effect to player %s: %s",
                        player_id,
                        str(exc),
                    )
                except Exception as exc:
                    self._logger.error(
                        "Unexpected error consuming stamina for player %s: %s",
                        player_id,
                        str(exc),
                        exc_info=True,
                    )

            if updated_statuses:
                self._player_status_repository.save_all(updated_statuses)
        except Exception as exc:
            self._logger.error(
                "Error applying environmental effects in bulk: %s",
                str(exc),
                exc_info=True,
            )
