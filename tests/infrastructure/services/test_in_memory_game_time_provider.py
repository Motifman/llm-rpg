import pytest
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider
from ai_rpg_world.domain.common.value_object import WorldTick

class TestInMemoryGameTimeProvider:
    """InMemoryGameTimeProviderのテスト"""

    def test_initial_tick(self):
        """初期ティックが正しく設定されること"""
        provider = InMemoryGameTimeProvider(100)
        assert provider.get_current_tick() == WorldTick(100)

    def test_advance_tick(self):
        """ティックを正しく進められること"""
        provider = InMemoryGameTimeProvider(10)
        new_tick = provider.advance_tick(5)
        
        assert new_tick == WorldTick(15)
        assert provider.get_current_tick() == WorldTick(15)

    def test_advance_tick_default_one(self):
        """デフォルトで1ティック進むこと"""
        provider = InMemoryGameTimeProvider(10)
        provider.advance_tick()
        assert provider.get_current_tick() == WorldTick(11)

    def test_advance_tick_invalid_amount(self):
        """負の値を指定した場合にエラーが発生すること"""
        provider = InMemoryGameTimeProvider(10)
        with pytest.raises(ValueError, match="Amount to advance must be positive: -1"):
            provider.advance_tick(-1)
