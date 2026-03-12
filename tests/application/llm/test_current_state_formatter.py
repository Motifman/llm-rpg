"""DefaultCurrentStateFormatter のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.world.contracts.dtos import (
    ActiveHarvestDto,
    PlayerCurrentStateDto,
    VisibleObjectDto,
    VisibleTileMapDto,
    AvailableMoveDto,
)
from ai_rpg_world.application.llm.services.current_state_formatter import (
    DefaultCurrentStateFormatter,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _minimal_current_state_dto(
    spot_name="テストスポット",
    spot_description="説明",
    area_name="エリア1",
    current_location_description=None,
    weather_type="clear",
    terrain_type="grass",
    has_visible_objects=False,
    has_available_moves=False,
    current_game_time_label=None,
):
    """テスト用の最小限の PlayerCurrentStateDto を組み立てる"""
    visible = []
    notable = []
    actionable = []
    if has_visible_objects:
        target = VisibleObjectDto(
            object_id=1,
            object_type="player",
            x=1,
            y=1,
            z=0,
            distance=2,
            display_name="Bob",
            direction_from_player="南東",
            can_interact=True,
            is_notable=True,
            notable_reason="actionable",
        )
        visible = [target]
        notable = [target]
        actionable = [target]
    moves = None
    total_moves = None
    if has_available_moves:
        moves = [
            AvailableMoveDto(
                spot_id=2,
                spot_name="隣のスポット",
                road_id=1,
                road_description="道",
                conditions_met=True,
                failed_conditions=[],
            ),
        ]
        total_moves = 1
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="TestPlayer",
        current_spot_id=1,
        current_spot_name=spot_name,
        current_spot_description=spot_description,
        x=0,
        y=0,
        z=0,
        area_id=1 if area_name else None,
        area_name=area_name,
        current_location_description=current_location_description,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type=weather_type,
        weather_intensity=0.5,
        current_terrain_type=terrain_type,
        visible_objects=visible,
        view_distance=5,
        available_moves=moves,
        total_available_moves=total_moves,
        attention_level=AttentionLevel.FULL,
        actionable_objects=actionable,
        notable_objects=notable,
        current_game_time_label=current_game_time_label,
    )


class TestDefaultCurrentStateFormatter:
    """DefaultCurrentStateFormatter の正常・例外ケース"""

    @pytest.fixture
    def formatter(self):
        return DefaultCurrentStateFormatter()

    def test_format_includes_spot_and_area(self, formatter):
        """現在地・エリアが含まれる"""
        dto = _minimal_current_state_dto(
            spot_name="広場",
            spot_description="中央の広場です。",
            area_name="町",
        )
        text = formatter.format(dto)
        assert "現在地: 広場" in text
        assert "中央の広場です。" in text
        assert "エリア: 町" in text

    def test_format_includes_weather_and_terrain(self, formatter):
        """天気・地形が含まれる"""
        dto = _minimal_current_state_dto(
            weather_type="rain",
            terrain_type="grass",
        )
        text = formatter.format(dto)
        assert "天気: rain" in text
        assert "地形: grass" in text

    def test_format_includes_notable_and_actionable_count_only(self, formatter):
        """注目対象と行動可能対象は件数のみ要約（詳細は UiContextBuilder の責務）"""
        dto = _minimal_current_state_dto(has_visible_objects=True)
        text = formatter.format(dto)
        assert "視界距離: 5" in text
        assert "注目対象: 1件" in text
        assert "今すぐ行動可能な対象: 1件" in text

    def test_format_includes_available_moves_count_when_present(self, formatter):
        """利用可能な移動先は件数のみ要約（詳細は UiContextBuilder）"""
        dto = _minimal_current_state_dto(has_available_moves=True)
        text = formatter.format(dto)
        assert "利用可能な移動先: 1 件" in text

    def test_format_includes_attention_level(self, formatter):
        """注意レベルが含まれる（enum の value が表示される）"""
        dto = _minimal_current_state_dto()
        text = formatter.format(dto)
        assert "注意レベル" in text
        assert AttentionLevel.FULL.value in text

    def test_format_includes_busy_state_when_busy(self, formatter):
        """busy 状態があるとき行動状態が含まれる"""
        dto = _minimal_current_state_dto()
        dto.is_busy = True
        dto.busy_until_tick = 42
        text = formatter.format(dto)
        assert "行動状態: 実行中" in text
        assert "42" in text

    def test_format_includes_active_harvest_when_present(self, formatter):
        dto = _minimal_current_state_dto()
        dto.active_harvest = ActiveHarvestDto(
            target_world_object_id=10,
            target_display_name="薬草",
            finish_tick=42,
        )
        text = formatter.format(dto)
        assert "採集中: 薬草" in text
        assert "42" in text

    def test_format_includes_area_description_when_present(self, formatter):
        """current_location_description あり: 出力にエリア説明が含まれる"""
        dto = _minimal_current_state_dto(
            area_name="町の広場",
            current_location_description="賑やかな市場が並ぶ中央広場。",
        )
        text = formatter.format(dto)
        assert "エリア: 町の広場" in text
        assert "賑やかな市場が並ぶ中央広場。" in text

    def test_format_area_without_description_returns_area_only(self, formatter):
        """area_name あり・current_location_description なし: エリア名のみ表示"""
        dto = _minimal_current_state_dto(
            area_name="空き地",
            current_location_description=None,
        )
        text = formatter.format(dto)
        assert "エリア: 空き地" in text
        lines = text.split("\n")
        area_idx = next(i for i, ln in enumerate(lines) if ln.startswith("エリア:"))
        next_line = lines[area_idx + 1] if area_idx + 1 < len(lines) else ""
        assert not next_line.startswith("  "), "説明行が含まれてはいけない"

    def test_format_without_area_name_omits_area_and_description(self, formatter):
        """area_name なし: エリア行・説明行ともに出力されない"""
        dto = _minimal_current_state_dto(area_name=None)
        text = formatter.format(dto)
        assert "エリア:" not in text

    def test_format_area_description_long_truncated(self, formatter):
        """current_location_description が200文字超: truncate される"""
        dto = _minimal_current_state_dto(
            area_name="長文の場所",
            current_location_description="あ" * 250,
        )
        text = formatter.format(dto)
        assert "エリア: 長文の場所" in text
        assert "あ" * 200 in text
        assert "…" in text
        assert "あ" * 250 not in text

    def test_format_dto_none_raises_type_error(self, formatter):
        """dto が None のとき TypeError"""
        with pytest.raises(TypeError, match="dto must be PlayerCurrentStateDto"):
            formatter.format(None)  # type: ignore[arg-type]

    def test_format_dto_not_player_current_state_dto_raises_type_error(self, formatter):
        """dto が PlayerCurrentStateDto でない場合 TypeError"""
        with pytest.raises(TypeError, match="dto must be PlayerCurrentStateDto"):
            formatter.format("not a dto")  # type: ignore[arg-type]

    def test_format_without_visible_tile_map_omits_tile_map_section(self, formatter):
        """visible_tile_map が None のときタイルマップ行が含まれない"""
        dto = _minimal_current_state_dto()
        assert dto.visible_tile_map is None
        text = formatter.format(dto)
        assert "視界タイルマップ" not in text

    def test_format_with_visible_tile_map_includes_legend_and_grid(self, formatter):
        """visible_tile_map ありのとき凡例とグリッドが出力に含まれる"""
        tile_map = VisibleTileMapDto(
            center_x=1,
            center_y=1,
            view_distance=1,
            rows=["...", ".P.", "..."],
            legend={".": "草", "P": "自分"},
        )
        dto = _minimal_current_state_dto()
        dto.visible_tile_map = tile_map
        text = formatter.format(dto)
        assert "視界タイルマップ凡例" in text
        assert "視界タイルマップ:" in text
        assert "草" in text
        assert "自分" in text
        assert ".P." in text

    def test_format_current_spot_name_none_shows_unplaced(self, formatter):
        """current_spot_name が None のとき「現在地: 未配置」"""
        dto = _minimal_current_state_dto()
        dto.current_spot_name = None
        dto.current_spot_id = None
        text = formatter.format(dto)
        assert "現在地: 未配置" in text

    def test_format_with_visible_tile_map_empty_legend(self, formatter):
        """visible_tile_map の legend が空でも例外なく出力される"""
        tile_map = VisibleTileMapDto(
            center_x=1,
            center_y=1,
            view_distance=1,
            rows=[".", ".", "."],
            legend={},
        )
        dto = _minimal_current_state_dto()
        dto.visible_tile_map = tile_map
        text = formatter.format(dto)
        assert "視界タイルマップ凡例" in text
        assert "視界タイルマップ:" in text

    def test_format_has_active_path_shows_movement_planned(self, formatter):
        """has_active_path が True で busy でないとき「移動計画あり」"""
        dto = _minimal_current_state_dto()
        dto.is_busy = False
        dto.has_active_path = True
        text = formatter.format(dto)
        assert "行動状態: 移動計画あり" in text

    def test_format_notable_and_actionable_zero_when_empty(self, formatter):
        """notable_objects と actionable_objects が空のとき 0件"""
        dto = _minimal_current_state_dto(has_visible_objects=False)
        dto.actionable_objects = []
        dto.notable_objects = []
        text = formatter.format(dto)
        assert "注目対象: 0件" in text
        assert "今すぐ行動可能な対象: 0件" in text

    def test_format_includes_coordinates_when_present(self, formatter):
        """x, y が設定されているとき座標が含まれる"""
        dto = _minimal_current_state_dto()
        dto.x = 3
        dto.y = 4
        dto.z = 0
        text = formatter.format(dto)
        assert "座標:" in text
        assert "x=3" in text
        assert "y=4" in text

    def test_format_includes_connected_spots_when_present(self, formatter):
        """connected_spot_names があるとき接続先が含まれる"""
        dto = _minimal_current_state_dto()
        dto.connected_spot_names = {"北の森", "東の町"}
        text = formatter.format(dto)
        assert "接続先スポット" in text
        assert "北の森" in text
        assert "東の町" in text

    def test_format_includes_current_player_count_when_positive(self, formatter):
        """current_player_count > 0 のとき同スポットのプレイヤー数が含まれる"""
        dto = _minimal_current_state_dto()
        dto.current_player_count = 3
        text = formatter.format(dto)
        assert "同スポットのプレイヤー: 3人" in text

    def test_format_available_moves_partial_none_omits_section(self, formatter):
        """available_moves と total_available_moves の片方のみ None のとき移動先件数は表示されない"""
        dto = _minimal_current_state_dto()
        dto.available_moves = []
        dto.total_available_moves = None
        text = formatter.format(dto)
        assert "利用可能な移動先:" not in text

    def test_format_includes_all_attention_levels(self, formatter):
        """各注意レベルが正しく表示される"""
        for level in AttentionLevel:
            dto = _minimal_current_state_dto()
            dto.attention_level = level
            text = formatter.format(dto)
            assert "注意レベル" in text
            assert level.value in text

    def test_format_includes_current_game_time_when_present(self, formatter):
        """current_game_time_label が設定されているとき現在時刻が含まれる"""
        dto = _minimal_current_state_dto(
            current_game_time_label="2年3月4日 12:30:45",
        )
        text = formatter.format(dto)
        assert "現在時刻: 2年3月4日 12:30:45" in text

    def test_format_omits_current_game_time_when_none(self, formatter):
        """current_game_time_label が None のとき現在時刻行が含まれない"""
        dto = _minimal_current_state_dto(current_game_time_label=None)
        text = formatter.format(dto)
        assert "現在時刻:" not in text

    def test_format_omits_current_game_time_when_empty_string(self, formatter):
        """current_game_time_label が空文字のとき現在時刻行が含まれない（falsy 扱い）"""
        dto = _minimal_current_state_dto(current_game_time_label="")
        text = formatter.format(dto)
        assert "現在時刻:" not in text
