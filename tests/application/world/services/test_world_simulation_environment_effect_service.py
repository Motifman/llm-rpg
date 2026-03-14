import unittest.mock as mock
import pytest

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.world.services.world_simulation_environment_effect_service import (
    WorldSimulationEnvironmentEffectService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestWorldSimulationEnvironmentEffectService:
    def test_applies_drain_and_saves_updated_statuses(self):
        repository = mock.Mock()
        status = mock.Mock()
        status.player_id = PlayerId(1)
        status.can_act.return_value = True
        status.stamina.value = 10
        repository.find_by_ids.return_value = [status]
        service = WorldSimulationEnvironmentEffectService(
            player_status_repository=repository,
            logger=mock.Mock(),
        )
        physical_map = mock.Mock(weather_state=mock.sentinel.weather, environment_type=mock.sentinel.env)

        with mock.patch(
            "ai_rpg_world.application.world.services.world_simulation_environment_effect_service.WeatherEffectService.calculate_environmental_stamina_drain",
            return_value=3,
        ):
            service.apply_bulk({PlayerId(1): physical_map})

        status.consume_stamina.assert_called_once_with(3)
        repository.save_all.assert_called_once_with([status])

    def test_skips_statuses_that_cannot_act(self):
        repository = mock.Mock()
        status = mock.Mock()
        status.player_id = PlayerId(1)
        status.can_act.return_value = False
        status.stamina.value = 10
        repository.find_by_ids.return_value = [status]
        service = WorldSimulationEnvironmentEffectService(
            player_status_repository=repository,
            logger=mock.Mock(),
        )

        with mock.patch(
            "ai_rpg_world.application.world.services.world_simulation_environment_effect_service.WeatherEffectService.calculate_environmental_stamina_drain",
            return_value=3,
        ):
            service.apply_bulk({PlayerId(1): mock.Mock()})

        status.consume_stamina.assert_not_called()
        repository.save_all.assert_not_called()

    def test_find_by_ids_raises_propagates_as_system_error(self):
        """find_by_ids が例外を投げた場合、SystemErrorException で再送出される"""
        repository = mock.Mock()
        repository.find_by_ids.side_effect = RuntimeError("db connection failed")
        service = WorldSimulationEnvironmentEffectService(
            player_status_repository=repository,
            logger=mock.Mock(),
        )

        with pytest.raises(SystemErrorException, match="Error applying environmental effects in bulk"):
            service.apply_bulk({PlayerId(1): mock.Mock()})

    def test_skips_player_status_not_in_map_and_continues(self):
        """status_map に存在しない player_id はスキップして他のプレイヤーは処理する"""
        repository = mock.Mock()
        status2 = mock.Mock()
        status2.player_id = PlayerId(2)
        status2.can_act.return_value = True
        status2.stamina.value = 10
        repository.find_by_ids.return_value = [status2]
        service = WorldSimulationEnvironmentEffectService(
            player_status_repository=repository,
            logger=mock.Mock(),
        )
        physical_map = mock.Mock(weather_state=mock.sentinel.weather, environment_type=mock.sentinel.env)

        with mock.patch(
            "ai_rpg_world.application.world.services.world_simulation_environment_effect_service.WeatherEffectService.calculate_environmental_stamina_drain",
            return_value=3,
        ):
            service.apply_bulk({
                PlayerId(1): physical_map,
                PlayerId(2): physical_map,
            })

        status2.consume_stamina.assert_called_once_with(3)
        repository.save_all.assert_called_once_with([status2])
