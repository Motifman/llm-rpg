import pytest
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import TerrainTypeEnum


class TestTerrainType:
    """TerrainType値オブジェクトのテスト"""

    def test_factory_methods(self):
        """ファクトリメソッドが正しく動作すること"""
        assert TerrainType.road().type == TerrainTypeEnum.ROAD
        assert TerrainType.road().base_cost.value == 1.0
        
        assert TerrainType.wall().type == TerrainTypeEnum.WALL
        assert TerrainType.wall().base_cost.value == float('inf')
        
        assert TerrainType.swamp().type == TerrainTypeEnum.SWAMP
        assert TerrainType.swamp().base_cost.value == 5.0

    def test_is_walkable(self):
        """通行可能性の判定が正しく動作すること"""
        assert TerrainType.road().is_walkable is True
        assert TerrainType.grass().is_walkable is True
        assert TerrainType.wall().is_walkable is False

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        t1 = TerrainType.road()
        t2 = TerrainType.road()
        t3 = TerrainType.grass()
        
        assert t1 == t2
        assert t1 != t3

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        t1 = TerrainType.road()
        t2 = TerrainType.road()
        assert hash(t1) == hash(t2)
        assert len({t1, t2}) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        t = TerrainType.road()
        with pytest.raises(AttributeError):
            t.type = TerrainTypeEnum.WALL
