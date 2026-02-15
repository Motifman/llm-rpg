"""WorldTimeConfigService のテスト"""

import pytest
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
    DefaultWorldTimeConfigService,
)


class TestDefaultWorldTimeConfigService:
    """DefaultWorldTimeConfigService のテスト"""

    def test_get_ticks_per_day_default(self):
        """デフォルトで 96 を返すこと"""
        service = DefaultWorldTimeConfigService()
        assert service.get_ticks_per_day() == 96

    def test_get_ticks_per_day_custom(self):
        """コンストラクタで指定した値を返すこと"""
        service = DefaultWorldTimeConfigService(ticks_per_day=24)
        assert service.get_ticks_per_day() == 24

    def test_ticks_per_day_positive_required(self):
        """ticks_per_day が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="ticks_per_day must be positive"):
            DefaultWorldTimeConfigService(ticks_per_day=0)
        with pytest.raises(ValueError, match="ticks_per_day must be positive"):
            DefaultWorldTimeConfigService(ticks_per_day=-1)
