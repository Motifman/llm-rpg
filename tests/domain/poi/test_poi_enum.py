import pytest

from src.domain.poi.poi_enum import POIType


class TestPOIType:
    """POITypeクラスのテスト"""
    
    def test_poi_type_values(self):
        """POITypeの値の確認"""
        assert POIType.TREASURE.value == "treasure"
        assert POIType.MONSTER_LAIR.value == "monster_lair"
        assert POIType.SECRET_PASSAGE.value == "secret_passage"
        assert POIType.INFORMATION.value == "information"
    
    def test_poi_type_enumeration(self):
        """POITypeの列挙確認"""
        poi_types = list(POIType)
        assert len(poi_types) == 4
        assert POIType.TREASURE in poi_types
        assert POIType.MONSTER_LAIR in poi_types
        assert POIType.SECRET_PASSAGE in poi_types
        assert POIType.INFORMATION in poi_types
    
    def test_poi_type_string_representation(self):
        """POITypeの文字列表現"""
        assert str(POIType.TREASURE) == "POIType.TREASURE"
        assert str(POIType.MONSTER_LAIR) == "POIType.MONSTER_LAIR"
        assert str(POIType.SECRET_PASSAGE) == "POIType.SECRET_PASSAGE"
        assert str(POIType.INFORMATION) == "POIType.INFORMATION"
    
    def test_poi_type_equality(self):
        """POITypeの等価性"""
        assert POIType.TREASURE == POIType.TREASURE
        assert POIType.TREASURE != POIType.MONSTER_LAIR
        assert POIType.MONSTER_LAIR != POIType.SECRET_PASSAGE
        assert POIType.SECRET_PASSAGE != POIType.INFORMATION
        assert POIType.INFORMATION != POIType.TREASURE
    
    def test_poi_type_membership(self):
        """POITypeのメンバーシップテスト"""
        assert POIType.TREASURE in POIType
        assert POIType.MONSTER_LAIR in POIType
        assert POIType.SECRET_PASSAGE in POIType
        assert POIType.INFORMATION in POIType
    
    def test_poi_type_from_value(self):
        """値からPOITypeを取得"""
        assert POIType("treasure") == POIType.TREASURE
        assert POIType("monster_lair") == POIType.MONSTER_LAIR
        assert POIType("secret_passage") == POIType.SECRET_PASSAGE
        assert POIType("information") == POIType.INFORMATION
    
    def test_poi_type_invalid_value(self):
        """無効な値でのPOIType作成"""
        with pytest.raises(ValueError):
            POIType("invalid_type")
    
    def test_poi_type_iteration(self):
        """POITypeのイテレーション"""
        expected_values = ["treasure", "monster_lair", "secret_passage", "information"]
        actual_values = [poi_type.value for poi_type in POIType]
        assert actual_values == expected_values
    
    def test_poi_type_name_attribute(self):
        """POITypeのname属性"""
        assert POIType.TREASURE.name == "TREASURE"
        assert POIType.MONSTER_LAIR.name == "MONSTER_LAIR"
        assert POIType.SECRET_PASSAGE.name == "SECRET_PASSAGE"
        assert POIType.INFORMATION.name == "INFORMATION"
