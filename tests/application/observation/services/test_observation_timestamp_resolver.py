"""ObservationTimestampResolver のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observation_timestamp_resolver import (
    ObservationTimestampResolver,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.service.world_time_config_service import (
    DefaultWorldTimeConfigService,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


class TestObservationTimestampResolverResolveOccurredAt:
    """resolve_occurred_at のテスト（正常・境界）"""

    def test_returns_occurred_at_when_event_has_attribute(self):
        """イベントに occurred_at がある場合、その値を返す（正常）"""
        resolver = ObservationTimestampResolver()
        occurred = datetime(2025, 3, 15, 10, 30, 0)
        event = MagicMock()
        event.occurred_at = occurred
        result = resolver.resolve_occurred_at(event)
        assert result == occurred

    def test_returns_now_when_event_has_no_occurred_at(self):
        """イベントに occurred_at がない場合、現在時刻を返す（境界）"""
        resolver = ObservationTimestampResolver()
        event = MagicMock(spec=[])
        del event.occurred_at
        before = datetime.now()
        result = resolver.resolve_occurred_at(event)
        after = datetime.now()
        assert before <= result <= after

    def test_returns_now_when_occurred_at_is_none(self):
        """occurred_at が None の場合、現在時刻を返す（境界）"""
        resolver = ObservationTimestampResolver()
        event = MagicMock()
        event.occurred_at = None
        before = datetime.now()
        result = resolver.resolve_occurred_at(event)
        after = datetime.now()
        assert before <= result <= after


class TestObservationTimestampResolverResolveGameTimeLabel:
    """resolve_game_time_label のテスト（正常・境界）"""

    def test_returns_label_when_both_provider_and_config_set(self):
        """game_time_provider と world_time_config が設定済みの場合、ラベルを返す（正常）"""
        provider = InMemoryGameTimeProvider(initial_tick=3600)
        config = DefaultWorldTimeConfigService(
            ticks_per_day=86400,
            days_per_month=30,
            months_per_year=12,
        )
        resolver = ObservationTimestampResolver(
            game_time_provider=provider,
            world_time_config=config,
        )
        event = MagicMock()
        event.occurred_tick = None
        result = resolver.resolve_game_time_label(event)
        assert result is not None
        assert "1年1月1日" in result
        assert "01:00:00" in result

    def test_uses_event_occurred_tick_when_present(self):
        """イベントに occurred_tick がある場合、それを優先して使用する（正常）"""
        provider = InMemoryGameTimeProvider(initial_tick=0)
        config = DefaultWorldTimeConfigService(
            ticks_per_day=86400,
            days_per_month=30,
            months_per_year=12,
        )
        resolver = ObservationTimestampResolver(
            game_time_provider=provider,
            world_time_config=config,
        )
        event = MagicMock()
        event.occurred_tick = WorldTick(7200)
        result = resolver.resolve_game_time_label(event)
        assert result is not None
        assert "02:00:00" in result

    def test_returns_none_when_game_time_provider_none(self):
        """game_time_provider が None の場合、None を返す（境界）"""
        config = DefaultWorldTimeConfigService(ticks_per_day=86400)
        resolver = ObservationTimestampResolver(
            game_time_provider=None,
            world_time_config=config,
        )
        event = MagicMock()
        result = resolver.resolve_game_time_label(event)
        assert result is None

    def test_returns_none_when_world_time_config_none(self):
        """world_time_config が None の場合、None を返す（境界）"""
        provider = InMemoryGameTimeProvider(initial_tick=0)
        resolver = ObservationTimestampResolver(
            game_time_provider=provider,
            world_time_config=None,
        )
        event = MagicMock()
        result = resolver.resolve_game_time_label(event)
        assert result is None

    def test_returns_none_when_both_none(self):
        """両方未設定の場合、None を返す（境界）"""
        resolver = ObservationTimestampResolver(
            game_time_provider=None,
            world_time_config=None,
        )
        event = MagicMock()
        result = resolver.resolve_game_time_label(event)
        assert result is None

    def test_uses_provider_current_tick_when_event_has_no_occurred_tick(self):
        """occurred_tick が無い場合、provider の現在ティックを使用する（正常）"""
        provider = InMemoryGameTimeProvider(initial_tick=172800)
        config = DefaultWorldTimeConfigService(
            ticks_per_day=86400,
            days_per_month=30,
            months_per_year=12,
        )
        resolver = ObservationTimestampResolver(
            game_time_provider=provider,
            world_time_config=config,
        )
        event = MagicMock()
        del event.occurred_tick
        result = resolver.resolve_game_time_label(event)
        assert result is not None
        assert "1年1月3日" in result


class TestObservationTimestampResolverExceptions:
    """例外伝播のテスト"""

    def test_resolve_game_time_label_propagates_provider_exception(self):
        """get_current_tick が例外を投げた場合、その例外を伝播する"""
        provider = MagicMock()
        provider.get_current_tick.side_effect = RuntimeError("provider failed")
        config = DefaultWorldTimeConfigService(ticks_per_day=86400)
        resolver = ObservationTimestampResolver(
            game_time_provider=provider,
            world_time_config=config,
        )
        event = MagicMock()
        event.occurred_tick = None
        with pytest.raises(RuntimeError, match="provider failed"):
            resolver.resolve_game_time_label(event)

    def test_resolve_game_time_label_propagates_config_exception(self):
        """world_time_config のメソッドが例外を投げた場合、その例外を伝播する"""
        provider = InMemoryGameTimeProvider(initial_tick=0)
        config = MagicMock()
        config.get_ticks_per_day.side_effect = ValueError("config error")
        resolver = ObservationTimestampResolver(
            game_time_provider=provider,
            world_time_config=config,
        )
        event = MagicMock()
        event.occurred_tick = None
        with pytest.raises(ValueError, match="config error"):
            resolver.resolve_game_time_label(event)
