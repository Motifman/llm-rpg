"""WorldTimeConfigService のテスト"""

import pytest
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
    DefaultWorldTimeConfigService,
)


class TestDefaultWorldTimeConfigService:
    """DefaultWorldTimeConfigService のテスト"""

    def test_get_ticks_per_day_default(self):
        """デフォルトで 86400（1日=秒）を返すこと"""
        service = DefaultWorldTimeConfigService()
        assert service.get_ticks_per_day() == 86400

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

    def test_get_days_per_month_default(self):
        """デフォルトで 30 を返すこと"""
        service = DefaultWorldTimeConfigService()
        assert service.get_days_per_month() == 30

    def test_get_months_per_year_default(self):
        """デフォルトで 12 を返すこと"""
        service = DefaultWorldTimeConfigService()
        assert service.get_months_per_year() == 12

    def test_days_per_month_custom(self):
        """days_per_month をコンストラクタで指定できること"""
        service = DefaultWorldTimeConfigService(days_per_month=28)
        assert service.get_days_per_month() == 28

    def test_months_per_year_custom(self):
        """months_per_year をコンストラクタで指定できること"""
        service = DefaultWorldTimeConfigService(months_per_year=10)
        assert service.get_months_per_year() == 10

    def test_days_per_month_positive_required(self):
        """days_per_month が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="days_per_month must be positive"):
            DefaultWorldTimeConfigService(days_per_month=0)
        with pytest.raises(ValueError, match="days_per_month must be positive"):
            DefaultWorldTimeConfigService(days_per_month=-1)

    def test_months_per_year_positive_required(self):
        """months_per_year が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="months_per_year must be positive"):
            DefaultWorldTimeConfigService(months_per_year=0)
        with pytest.raises(ValueError, match="months_per_year must be positive"):
            DefaultWorldTimeConfigService(months_per_year=-1)
