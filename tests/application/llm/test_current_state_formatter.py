"""DefaultCurrentStateFormatter のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.world.contracts.dtos import (
    PlayerCurrentStateDto,
    VisibleObjectDto,
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
