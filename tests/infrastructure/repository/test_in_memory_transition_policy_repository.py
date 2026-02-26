"""InMemoryTransitionPolicyRepository のテスト"""

import pytest
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.transition_condition import RequireToll, BlockIfWeather, block_if_weather
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.infrastructure.repository.in_memory_transition_policy_repository import (
    InMemoryTransitionPolicyRepository,
)


class TestInMemoryTransitionPolicyRepository:
    def test_get_conditions_empty_when_nothing_set(self):
        repo = InMemoryTransitionPolicyRepository()
        assert repo.get_conditions(SpotId(1), SpotId(2)) == []

    def test_set_and_get_conditions(self):
        repo = InMemoryTransitionPolicyRepository()
        conditions = [RequireToll(amount_gold=10)]
        repo.set_conditions(SpotId(1), SpotId(2), conditions)
        result = repo.get_conditions(SpotId(1), SpotId(2))
        assert len(result) == 1
        assert result[0].amount_gold == 10

    def test_get_conditions_returns_copy(self):
        repo = InMemoryTransitionPolicyRepository()
        conditions = [RequireToll(amount_gold=5)]
        repo.set_conditions(SpotId(1), SpotId(2), conditions)
        result = repo.get_conditions(SpotId(1), SpotId(2))
        result.append(RequireToll(amount_gold=99))
        assert len(repo.get_conditions(SpotId(1), SpotId(2))) == 1

    def test_different_key_returns_empty(self):
        repo = InMemoryTransitionPolicyRepository()
        repo.set_conditions(SpotId(1), SpotId(2), [RequireToll(amount_gold=10)])
        assert repo.get_conditions(SpotId(1), SpotId(3)) == []
        assert repo.get_conditions(SpotId(2), SpotId(2)) == []

    def test_initial_dict(self):
        repo = InMemoryTransitionPolicyRepository(initial={
            (SpotId(1), SpotId(2)): [block_if_weather([WeatherTypeEnum.BLIZZARD])],
        })
        result = repo.get_conditions(SpotId(1), SpotId(2))
        assert len(result) == 1
        assert WeatherTypeEnum.BLIZZARD in result[0].blocked_weather_types
