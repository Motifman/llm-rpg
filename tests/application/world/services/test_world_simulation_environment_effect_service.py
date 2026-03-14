import unittest.mock as mock

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
