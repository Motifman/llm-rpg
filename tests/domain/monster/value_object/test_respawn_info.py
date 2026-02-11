import pytest
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRespawnValidationException

class TestRespawnInfo:
    """RespawnInfo値オブジェクトのテスト"""

    def test_create_success(self):
        respawn = RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True)
        assert respawn.respawn_interval_ticks == 100
        assert respawn.is_auto_respawn is True

    def test_create_fail_negative_interval(self):
        with pytest.raises(MonsterRespawnValidationException, match="Respawn interval cannot be negative"):
            RespawnInfo(respawn_interval_ticks=-1)
