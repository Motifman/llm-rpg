import pytest
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRespawnValidationException
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


class TestRespawnInfo:
    """RespawnInfo値オブジェクトのテスト"""

    def test_create_success(self):
        respawn = RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True)
        assert respawn.respawn_interval_ticks == 100
        assert respawn.is_auto_respawn is True
        assert respawn.condition is None

    def test_create_with_condition(self):
        condition = SpawnCondition(time_band=TimeOfDay.NIGHT)
        respawn = RespawnInfo(respawn_interval_ticks=50, is_auto_respawn=True, condition=condition)
        assert respawn.condition is condition
        assert respawn.condition.is_satisfied_at(TimeOfDay.NIGHT) is True
        assert respawn.condition.is_satisfied_at(TimeOfDay.DAY) is False

    def test_create_fail_negative_interval(self):
        with pytest.raises(MonsterRespawnValidationException, match="Respawn interval cannot be negative"):
            RespawnInfo(respawn_interval_ticks=-1)
