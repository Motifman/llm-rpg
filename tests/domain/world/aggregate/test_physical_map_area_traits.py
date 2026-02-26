"""PhysicalMapAggregate の area_traits（スポット特性）のテスト"""

import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.enum.world_enum import SpotTraitEnum
from ai_rpg_world.domain.world.exception.map_exception import InvalidAreaTraitException
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


class TestPhysicalMapAreaTraits:
    """PhysicalMapAggregate の area_traits のテスト"""

    @pytest.fixture
    def spot_id(self):
        return SpotId(1)

    @pytest.fixture
    def minimal_tiles(self):
        return [Tile(Coordinate(0, 0), TerrainType.grass())]

    # --- 正常ケース ---

    def test_create_without_area_traits_returns_empty_frozenset(self, spot_id, minimal_tiles):
        """area_traits を指定しない場合、空の frozenset が返る"""
        aggregate = PhysicalMapAggregate.create(spot_id, minimal_tiles)
        assert aggregate.area_traits == frozenset()
        assert len(aggregate.area_traits) == 0

    def test_create_with_area_traits_none_returns_empty_frozenset(self, spot_id, minimal_tiles):
        """area_traits=None で create した場合、空の frozenset が返る"""
        aggregate = PhysicalMapAggregate.create(spot_id, minimal_tiles, area_traits=None)
        assert aggregate.area_traits == frozenset()

    def test_create_with_empty_area_traits_returns_empty_frozenset(self, spot_id, minimal_tiles):
        """area_traits=[] で create した場合、空の frozenset が返る"""
        aggregate = PhysicalMapAggregate.create(spot_id, minimal_tiles, area_traits=[])
        assert aggregate.area_traits == frozenset()

    def test_create_with_single_trait(self, spot_id, minimal_tiles):
        """単一の SpotTraitEnum を指定して create できる"""
        aggregate = PhysicalMapAggregate.create(
            spot_id, minimal_tiles, area_traits=[SpotTraitEnum.FOREST]
        )
        assert aggregate.area_traits == frozenset({SpotTraitEnum.FOREST})

    def test_create_with_multiple_traits(self, spot_id, minimal_tiles):
        """複数の SpotTraitEnum を指定して create できる"""
        traits = {
            SpotTraitEnum.FOREST,
            SpotTraitEnum.WATER_EDGE,
            SpotTraitEnum.DANGEROUS,
        }
        aggregate = PhysicalMapAggregate.create(spot_id, minimal_tiles, area_traits=traits)
        assert aggregate.area_traits == frozenset(traits)
        assert len(aggregate.area_traits) == 3

    def test_create_with_traits_as_list(self, spot_id, minimal_tiles):
        """area_traits に list を渡しても正規化されて frozenset で返る"""
        traits_list = [SpotTraitEnum.LAVA, SpotTraitEnum.DUNGEON_DEPTH]
        aggregate = PhysicalMapAggregate.create(spot_id, minimal_tiles, area_traits=traits_list)
        assert aggregate.area_traits == frozenset(traits_list)

    def test_area_traits_property_is_immutable(self, spot_id, minimal_tiles):
        """area_traits プロパティで返る frozenset は不変である"""
        aggregate = PhysicalMapAggregate.create(
            spot_id, minimal_tiles, area_traits=[SpotTraitEnum.SAFE_ZONE]
        )
        traits = aggregate.area_traits
        with pytest.raises(AttributeError):
            traits.add(SpotTraitEnum.FOREST)

    def test_init_directly_with_area_traits(self, spot_id, minimal_tiles):
        """__init__ に area_traits を渡した場合も正しく保持される"""
        tile_dict = {tile.coordinate: tile for tile in minimal_tiles}
        aggregate = PhysicalMapAggregate(
            spot_id=spot_id,
            tiles=tile_dict,
            area_traits=[SpotTraitEnum.OPEN_FIELD, SpotTraitEnum.OTHER],
        )
        assert aggregate.area_traits == frozenset({SpotTraitEnum.OPEN_FIELD, SpotTraitEnum.OTHER})

    def test_all_spot_trait_enum_values_accepted(self, spot_id, minimal_tiles):
        """すべての SpotTraitEnum 値を area_traits に指定できる"""
        all_traits = list(SpotTraitEnum)
        aggregate = PhysicalMapAggregate.create(spot_id, minimal_tiles, area_traits=all_traits)
        assert aggregate.area_traits == frozenset(all_traits)

    # --- 例外ケース ---

    def test_create_with_invalid_trait_type_raises_invalid_area_trait_exception(
        self, spot_id, minimal_tiles
    ):
        """SpotTraitEnum 以外の型を混入させると InvalidAreaTraitException が発生する"""
        with pytest.raises(InvalidAreaTraitException) as exc_info:
            PhysicalMapAggregate.create(
                spot_id, minimal_tiles, area_traits=[SpotTraitEnum.FOREST, "NOT_ENUM"]
            )
        assert "SpotTraitEnum" in str(exc_info.value)
        assert "str" in str(exc_info.value)

    def test_create_with_string_value_raises_invalid_area_trait_exception(
        self, spot_id, minimal_tiles
    ):
        """文字列のみを渡した場合 InvalidAreaTraitException が発生する"""
        with pytest.raises(InvalidAreaTraitException):
            PhysicalMapAggregate.create(spot_id, minimal_tiles, area_traits=["FOREST"])

    def test_create_with_int_raises_invalid_area_trait_exception(self, spot_id, minimal_tiles):
        """int を渡した場合 InvalidAreaTraitException が発生する"""
        with pytest.raises(InvalidAreaTraitException):
            PhysicalMapAggregate.create(spot_id, minimal_tiles, area_traits=[1])

    def test_init_with_invalid_trait_raises_invalid_area_trait_exception(self, spot_id):
        """__init__ に不正な trait を渡した場合も InvalidAreaTraitException が発生する"""
        with pytest.raises(InvalidAreaTraitException):
            PhysicalMapAggregate(
                spot_id=spot_id,
                tiles={},
                area_traits=[None],
            )

    # --- スポーン条件との連携（area_traits を SpawnCondition に Enum のまま渡す）---

    def test_area_traits_passed_directly_to_spawn_condition_is_satisfied(
        self, spot_id, minimal_tiles
    ):
        """PhysicalMap.area_traits をそのまま SpawnCondition.is_satisfied に渡すと条件一致で True"""
        aggregate = PhysicalMapAggregate.create(
            spot_id, minimal_tiles,
            area_traits=[SpotTraitEnum.FOREST, SpotTraitEnum.WATER_EDGE],
        )
        condition = SpawnCondition(
            time_band=None,
            required_area_traits=frozenset({SpotTraitEnum.FOREST}),
        )
        assert condition.is_satisfied(TimeOfDay.DAY, area_traits=aggregate.area_traits) is True

    def test_spawn_condition_not_satisfied_when_map_lacks_required_trait(
        self, spot_id, minimal_tiles
    ):
        """マップの area_traits に required_area_traits が含まれない場合 is_satisfied は False"""
        aggregate = PhysicalMapAggregate.create(
            spot_id, minimal_tiles,
            area_traits=[SpotTraitEnum.LAVA],
        )
        condition = SpawnCondition(
            time_band=None,
            required_area_traits=frozenset({SpotTraitEnum.FOREST, SpotTraitEnum.LAVA}),
        )
        assert condition.is_satisfied(TimeOfDay.DAY, area_traits=aggregate.area_traits) is False

    def test_spawn_condition_satisfied_when_map_has_all_required_traits(
        self, spot_id, minimal_tiles
    ):
        """マップの area_traits が required_area_traits をすべて含む場合 is_satisfied は True"""
        aggregate = PhysicalMapAggregate.create(
            spot_id, minimal_tiles,
            area_traits=[SpotTraitEnum.FOREST, SpotTraitEnum.WATER_EDGE, SpotTraitEnum.DANGEROUS],
        )
        condition = SpawnCondition(
            time_band=None,
            required_area_traits=frozenset({SpotTraitEnum.FOREST, SpotTraitEnum.WATER_EDGE}),
        )
        assert condition.is_satisfied(TimeOfDay.DAY, area_traits=aggregate.area_traits) is True

    def test_spawn_condition_with_empty_map_traits_and_required_returns_false(
        self, spot_id, minimal_tiles
    ):
        """マップの area_traits が空で required_area_traits がある場合 is_satisfied は False"""
        aggregate = PhysicalMapAggregate.create(spot_id, minimal_tiles)
        condition = SpawnCondition(
            time_band=None,
            required_area_traits=frozenset({SpotTraitEnum.FOREST}),
        )
        assert condition.is_satisfied(TimeOfDay.DAY, area_traits=aggregate.area_traits) is False
        assert condition.is_satisfied(TimeOfDay.DAY, area_traits=None) is False
