import pytest
from ai_rpg_world.domain.common.value_object import WorldTick

class TestWorldTick:
    """WorldTick値オブジェクトのテスト"""

    def test_world_tick_creation(self):
        """正常に作成できること"""
        tick = WorldTick(10)
        assert tick.value == 10

    def test_world_tick_invalid_value(self):
        """負の値で作成しようとした場合にエラーが発生すること"""
        with pytest.raises(ValueError, match="Invalid tick: -1"):
            WorldTick(-1)

    def test_world_tick_next(self):
        """nextメソッドで次のティックが取得できること"""
        tick = WorldTick(10)
        next_tick = tick.next()
        assert next_tick.value == 11

    def test_world_tick_add_duration(self):
        """add_durationメソッドで期間が加算できること"""
        tick = WorldTick(10)
        future_tick = tick.add_duration(5)
        assert future_tick.value == 15

    def test_world_tick_add_duration_invalid(self):
        """add_durationに負の値を指定した場合にエラーが発生すること"""
        tick = WorldTick(10)
        with pytest.raises(ValueError, match="Duration cannot be negative: -1"):
            tick.add_duration(-1)

    def test_world_tick_addition(self):
        """演算子+で加算ができること（数値およびWorldTick）"""
        tick = WorldTick(10)
        # intとの加算
        assert (tick + 5).value == 15
        # WorldTickとの加算
        assert (tick + WorldTick(5)).value == 15

    def test_world_tick_subtraction(self):
        """演算子-でティックの差分が取得できること"""
        tick1 = WorldTick(20)
        tick2 = WorldTick(15)
        assert tick1 - tick2 == 5

    def test_world_tick_comparison(self):
        """比較演算子が正しく動作すること"""
        tick1 = WorldTick(10)
        tick2 = WorldTick(20)
        tick3 = WorldTick(10)
        
        assert tick2 > tick1
        assert tick1 < tick2
        assert tick1 >= tick3
        assert tick1 <= tick3
        assert tick1 == tick3
        assert tick1 != tick2

    def test_world_tick_str_repr(self):
        """文字列変換および表現が正しく動作すること"""
        tick = WorldTick(123)
        assert str(tick) == "123"
        assert repr(tick) == "WorldTick(123)"
