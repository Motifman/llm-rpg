"""VisibleTileMapBuilder のテスト（正常・境界・例外）。"""

from unittest.mock import MagicMock, patch

import pytest

from ai_rpg_world.application.world.contracts.dtos import VisibleObjectDto, VisibleTileMapDto
from ai_rpg_world.application.world.services.visible_tile_map_builder import (
    VisibleTileMapBuilder,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    ChestComponent,
    InteractableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import (
    DirectionEnum,
    InteractionTypeEnum,
    ObjectTypeEnum,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_map_with_tiles(
    spot_id: int,
    width: int,
    height: int,
    objects: list[WorldObject] | None = None,
    terrain_overrides: dict[tuple[int, int], TerrainType] | None = None,
) -> PhysicalMapAggregate:
    """指定サイズのマップを作成。terrain_overrides で特定座標の地形を上書き。"""
    tiles = {}
    for x in range(width):
        for y in range(height):
            coord = Coordinate(x, y, 0)
            tt = (terrain_overrides or {}).get((x, y), TerrainType.grass())
            tiles[coord] = Tile(coord, tt)
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects or [],
    )


class TestVisibleTileMapBuilder:
    """VisibleTileMapBuilder の正常・境界・例外ケース"""

    @pytest.fixture
    def builder(self) -> VisibleTileMapBuilder:
        return VisibleTileMapBuilder()

    def test_build_visible_tile_map_empty_terrain_only(self, builder: VisibleTileMapBuilder):
        """空マップ（地形のみ）: 草のグリッドが返る"""
        physical_map = _make_map_with_tiles(1, 5, 5)
        origin = Coordinate(2, 2, 0)
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=origin,
            view_distance=1,
            visible_objects=[],
            player_id=1,
        )
        assert isinstance(result, VisibleTileMapDto)
        assert result.center_x == 2
        assert result.center_y == 2
        assert result.view_distance == 1
        # 3x3 グリッド、中心がプレイヤー位置（空なので草）
        assert len(result.rows) == 3
        assert all(len(row) == 3 for row in result.rows)
        # 中心 (2,2) は草
        assert result.rows[1][1] == "."
        assert "草" in result.legend["."]

    def test_build_visible_tile_map_player_at_center(self, builder: VisibleTileMapBuilder):
        """プレイヤー単体: 中心に P が表示される"""
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(2, 2, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        physical_map = _make_map_with_tiles(1, 5, 5, objects=[actor])
        visible_objects = [
            VisibleObjectDto(
                object_id=1,
                object_type="PLAYER",
                x=2,
                y=2,
                z=0,
                distance=0,
                display_name="Alice",
                object_kind="player",
                is_self=True,
            )
        ]
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(2, 2, 0),
            view_distance=1,
            visible_objects=visible_objects,
            player_id=1,
        )
        assert result.rows[1][1] == "P"

    def test_build_visible_tile_map_mixed_terrain(self, builder: VisibleTileMapBuilder):
        """水・道・茂みの混在: 各地形が正しい文字で表示される（壁は不透明で視界を遮るため除外）"""
        overrides = {
            (2, 1): TerrainType.water(),
            (1, 2): TerrainType.road(),
            (2, 3): TerrainType.bush(),
        }
        physical_map = _make_map_with_tiles(1, 5, 5, terrain_overrides=overrides)
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(2, 2, 0),
            view_distance=1,
            visible_objects=[],
            player_id=1,
        )
        # y=1 の行: (2,1) 水（中心の真上）
        row_y1 = result.rows[0]
        assert row_y1[1] == "~"
        # y=2 の行: (1,2) 道, (2,2) 中心の草, (3,2) 草
        row_y2 = result.rows[1]
        assert row_y2[0] == "="
        assert row_y2[1] == "."
        # y=3 の行: (2,3) 茂み（中心の真下）
        row_y3 = result.rows[2]
        assert row_y3[1] == "%"

    def test_build_visible_tile_map_chest_and_npc(self, builder: VisibleTileMapBuilder):
        """チェストと NPC が正しい文字で表示される"""
        chest = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(2, 1, 0),
            object_type=ObjectTypeEnum.CHEST,
            is_blocking=False,
            component=ChestComponent(is_open=True, item_ids=[]),
        )
        npc = WorldObject(
            object_id=WorldObjectId(101),
            coordinate=Coordinate(3, 2, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=InteractableComponent(InteractionTypeEnum.TALK),
        )
        physical_map = _make_map_with_tiles(1, 6, 6, objects=[chest, npc])
        visible_objects = [
            VisibleObjectDto(
                object_id=100,
                object_type="CHEST",
                x=2,
                y=1,
                z=0,
                distance=1,
                object_kind="chest",
                is_self=False,
            ),
            VisibleObjectDto(
                object_id=101,
                object_type="NPC",
                x=3,
                y=2,
                z=0,
                distance=1,
                object_kind="npc",
                is_self=False,
            ),
        ]
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(2, 2, 0),
            view_distance=1,
            visible_objects=visible_objects,
            player_id=1,
        )
        # 北 (2,1) にチェスト → rows[0] の中央
        assert result.rows[0][1] == "C"
        # 東 (3,2) に NPC → rows[1] の右
        assert result.rows[1][2] == "N"

    def test_build_visible_tile_map_wall_blocks_visibility(self, builder: VisibleTileMapBuilder):
        """壁で遮蔽された座標は ? になる"""
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(2, 2, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.EAST, player_id=PlayerId(1)),
        )
        # 壁を (3,2) に配置。origin=(2,2) から (4,2) へは壁を通過するため見えない
        overrides = {(3, 2): TerrainType.wall()}
        physical_map = _make_map_with_tiles(1, 6, 6, objects=[actor], terrain_overrides=overrides)
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(2, 2, 0),
            view_distance=2,
            visible_objects=[
                VisibleObjectDto(
                    object_id=1,
                    object_type="PLAYER",
                    x=2,
                    y=2,
                    z=0,
                    distance=0,
                    object_kind="player",
                    is_self=True,
                )
            ],
            player_id=1,
        )
        # row for y=2: rows[2] (y: 0,1,2 → index 2)
        # x: 0,1,2,3,4. (4,2) は壁の向こうで視界外
        # row[2]: x=0,1,2,3,4 → index 4 is (4,2)
        row_y2 = result.rows[2]
        assert row_y2[4] == "?"
        # 壁 (3,2) 自体は見える（index 3）
        assert row_y2[3] == "#"

    def test_build_visible_tile_map_view_distance_zero(self, builder: VisibleTileMapBuilder):
        """view_distance=0: 1x1 グリッド"""
        physical_map = _make_map_with_tiles(1, 3, 3)
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(1, 1, 0),
            view_distance=0,
            visible_objects=[],
            player_id=1,
        )
        assert len(result.rows) == 1
        assert len(result.rows[0]) == 1
        assert result.rows[0][0] == "."

    def test_build_visible_tile_map_view_distance_one(self, builder: VisibleTileMapBuilder):
        """view_distance=1: 3x3 グリッド"""
        physical_map = _make_map_with_tiles(1, 5, 5)
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(2, 2, 0),
            view_distance=1,
            visible_objects=[],
            player_id=1,
        )
        assert len(result.rows) == 3
        assert all(len(row) == 3 for row in result.rows)

    def test_build_visible_tile_map_out_of_bounds_shows_question_mark(
        self, builder: VisibleTileMapBuilder
    ):
        """マップ外座標は ? になる（負の座標または TileNotFoundException）"""
        # 2x2 の小さいマップ、origin=(0,0), view_distance=1 → (-1,-1)は負のため ?
        physical_map = _make_map_with_tiles(1, 2, 2)
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(0, 0, 0),
            view_distance=1,
            visible_objects=[],
            player_id=1,
        )
        # 左上 (-1,-1) は負の座標のため rows[0][0] = ?
        assert result.rows[0][0] == "?"
        # (1,1) はマップ範囲外（2x2 は (0,0),(1,0),(0,1),(1,1) のみ）-> 実は在る。3x3で(2,2)を試す
        physical_map2 = _make_map_with_tiles(1, 2, 2)
        result2 = builder.build_visible_tile_map(
            physical_map=physical_map2,
            origin=Coordinate(1, 1, 0),
            view_distance=1,
            visible_objects=[],
            player_id=1,
        )
        # (2,2) は 2x2 マップ外 → TileNotFoundException → ?
        # row for y=2, x=2: rows index: y 0,1,2 → row 2. x 0,1,2 → index 2
        assert result2.rows[2][2] == "?"
        assert "?" in result.legend

    def test_build_visible_tile_map_other_player_shows_p(self, builder: VisibleTileMapBuilder):
        """他プレイヤーは p で表示される"""
        physical_map = _make_map_with_tiles(1, 5, 5)
        visible_objects = [
            VisibleObjectDto(
                object_id=2,
                object_type="PLAYER",
                x=2,
                y=1,
                z=0,
                distance=1,
                display_name="Bob",
                object_kind="player",
                is_self=False,
            )
        ]
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(2, 2, 0),
            view_distance=1,
            visible_objects=visible_objects,
            player_id=1,
        )
        assert result.rows[0][1] == "p"

    def test_build_visible_tile_map_legend_contains_all_chars(self, builder: VisibleTileMapBuilder):
        """凡例に必要な全文字が含まれる"""
        physical_map = _make_map_with_tiles(1, 3, 3)
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(1, 1, 0),
            view_distance=0,
            visible_objects=[],
            player_id=1,
        )
        expected_keys = {".", "#", "~", "=", "%", "@", "P", "p", "N", "M", "C", "R", "D", "I", "O", "?"}
        assert expected_keys <= set(result.legend.keys())

    def test_build_visible_tile_map_weather_reduces_effective_distance(
        self, builder: VisibleTileMapBuilder
    ):
        """天候による視界減衰で effective_distance が縮小する"""
        from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
        from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum

        physical_map = _make_map_with_tiles(1, 10, 10)
        physical_map.set_weather(WeatherState(WeatherTypeEnum.FOG, 1.0))
        # FOG intensity 1 → reduction 8. view_distance=10, effective=2
        result = builder.build_visible_tile_map(
            physical_map=physical_map,
            origin=Coordinate(5, 5, 0),
            view_distance=10,
            visible_objects=[],
            player_id=1,
        )
        # グリッドは 21x21
        assert len(result.rows) == 21
        # 中心 row: y=5 は rows[10]. x: -5..15 だが負は ?. x=8 は Manhattan 3 > effective 2 → ?
        # x range 0..15 のうち x=8: index = 8 - (-5) = 13? No. range(0, 21) for x from -5 to 15.
        # Index i corresponds to x = -5 + i. So index 13 → x=8. From (5,5) Manhattan to (8,5)=3. ?
        center_row_idx = 10
        row_center = result.rows[center_row_idx]
        # x=8 at index 13
        assert row_center[13] == "?"
