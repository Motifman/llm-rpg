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
    weather_type="clear",
    terrain_type="grass",
    has_visible_objects=False,
    has_available_moves=False,
):
    """テスト用の最小限の PlayerCurrentStateDto を組み立てる"""
    visible = []
    if has_visible_objects:
        visible = [
            VisibleObjectDto(
                object_id=1,
                object_type="player",
                x=1,
                y=1,
                z=0,
                distance=2,
            ),
        ]
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
        area_id=1,
        area_name=area_name,
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

    def test_format_includes_visible_objects_when_present(self, formatter):
        """視界内オブジェクトがあるとき表示される"""
        dto = _minimal_current_state_dto(has_visible_objects=True)
        text = formatter.format(dto)
        assert "視界内オブジェクト" in text
        assert "タイプ=player" in text

    def test_format_includes_available_moves_when_present(self, formatter):
        """利用可能な移動先があるとき表示される"""
        dto = _minimal_current_state_dto(has_available_moves=True)
        text = formatter.format(dto)
        assert "利用可能な移動先" in text
        assert "隣のスポット" in text

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

    def test_format_dto_none_raises_type_error(self, formatter):
        """dto が None のとき TypeError"""
        with pytest.raises(TypeError, match="dto must be PlayerCurrentStateDto"):
            formatter.format(None)  # type: ignore[arg-type]

    def test_format_dto_not_player_current_state_dto_raises_type_error(self, formatter):
        """dto が PlayerCurrentStateDto でない場合 TypeError"""
        with pytest.raises(TypeError, match="dto must be PlayerCurrentStateDto"):
            formatter.format("not a dto")  # type: ignore[arg-type]
