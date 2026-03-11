"""視界範囲のタイルマップを構築する。"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from ai_rpg_world.application.world.contracts.dtos import VisibleObjectDto, VisibleTileMapDto
from ai_rpg_world.domain.world.enum.world_enum import TerrainTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import TileNotFoundException
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
        PhysicalMapAggregate,
    )

# 地形 → 文字
_TERRAIN_CHAR: Dict[str, str] = {
    TerrainTypeEnum.GRASS.value: ".",
    TerrainTypeEnum.WALL.value: "#",
    TerrainTypeEnum.WATER.value: "~",
    TerrainTypeEnum.ROAD.value: "=",
    TerrainTypeEnum.BUSH.value: "%",
    TerrainTypeEnum.SWAMP.value: "@",
}

# オブジェクト種別 → 文字（優先度順で上書きする）
_OBJECT_KIND_CHAR: Dict[str, str] = {
    "chest": "C",
    "door": "D",
    "resource": "R",
    "ground_item": "I",
    "monster": "M",
    "npc": "N",
    "player": "p",  # is_self で P に上書き
    "object": "O",
}


class VisibleTileMapBuilder:
    """視界範囲のタイルマップ（グリッド）を構築する。"""

    def build_visible_tile_map(
        self,
        *,
        physical_map: "PhysicalMapAggregate",
        origin: Coordinate,
        view_distance: int,
        visible_objects: List[VisibleObjectDto],
        player_id: int,
    ) -> VisibleTileMapDto:
        """
        視界範囲のタイルマップを構築する。

        天候による視界減衰・最大視界制限は get_objects_in_range と同様に適用する。
        """
        # effective_distance: 天候を考慮した有効視界距離
        reduction = WeatherEffectService.calculate_vision_reduction(
            physical_map.weather_state,
            physical_map.environment_type,
        )
        effective_distance = max(0, view_distance - reduction)
        max_dist = WeatherEffectService.get_max_vision_distance(
            physical_map.weather_state,
            physical_map.environment_type,
        )
        effective_distance = min(effective_distance, max_dist)

        # 座標 → オブジェクト文字（同一タイル複数時は優先度で決定）
        objects_by_coord: Dict[tuple[int, int], str] = {}
        for obj in visible_objects:
            char = self._object_to_char(obj, player_id)
            key = (obj.x, obj.y)
            if key not in objects_by_coord or self._char_priority(char) > self._char_priority(
                objects_by_coord[key]
            ):
                objects_by_coord[key] = char

        # 矩形範囲を y 昇順で走査
        # 注: Coordinate は x,y >= 0 を要求するため、負の座標はマップ外として ? にする
        rows: List[str] = []
        for y in range(origin.y - view_distance, origin.y + view_distance + 1):
            row_chars: List[str] = []
            for x in range(origin.x - view_distance, origin.x + view_distance + 1):
                if x < 0 or y < 0:
                    row_chars.append("?")
                    continue
                coord = Coordinate(x, y, origin.z)
                if (x, y) in objects_by_coord:
                    row_chars.append(objects_by_coord[(x, y)])
                else:
                    row_chars.append(
                        self._tile_char_at(
                            physical_map=physical_map,
                            origin=origin,
                            coord=coord,
                            effective_distance=effective_distance,
                        )
                    )
            rows.append("".join(row_chars))

        legend = self._build_legend()
        return VisibleTileMapDto(
            center_x=origin.x,
            center_y=origin.y,
            view_distance=view_distance,
            rows=rows,
            legend=legend,
        )

    def _tile_char_at(
        self,
        *,
        physical_map: "PhysicalMapAggregate",
        origin: Coordinate,
        coord: Coordinate,
        effective_distance: float,
    ) -> str:
        """指定座標のタイル文字を返す。視界外・マップ外は '?'。"""
        if origin.distance_to(coord) > effective_distance:
            return "?"
        if not physical_map.is_visible(origin, coord):
            return "?"
        try:
            tile = physical_map.get_tile(coord)
            return _TERRAIN_CHAR.get(
                tile.terrain_type.type.value,
                tile.terrain_type.type.value[0].lower() if tile.terrain_type.type.value else ".",
            )
        except TileNotFoundException:
            return "?"

    def _object_to_char(self, obj: VisibleObjectDto, player_id: int) -> str:
        """VisibleObjectDto をタイルマップ用1文字に変換する。"""
        if obj.is_self:
            return "P"
        kind = obj.object_kind or "object"
        return _OBJECT_KIND_CHAR.get(kind, "O")

    def _char_priority(self, char: str) -> int:
        """表示優先度（大きいほど優先）。自分 > 他プレイヤー > NPC > ..."""
        order = ("O", "I", "D", "R", "C", "M", "N", "p", "P")
        try:
            return order.index(char)
        except ValueError:
            return -1

    def _build_legend(self) -> Dict[str, str]:
        """凡例を構築する。"""
        return {
            ".": "草",
            "#": "壁",
            "~": "水",
            "=": "道",
            "%": "茂み",
            "@": "湿地",
            "P": "自分",
            "p": "他プレイヤー",
            "N": "NPC",
            "M": "モンスター",
            "C": "チェスト",
            "R": "資源",
            "D": "ドア",
            "I": "落ちているアイテム",
            "O": "オブジェクト",
            "?": "未視認",
        }
