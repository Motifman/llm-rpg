"""Step 6: スポットグラフ用フォーマッタ・ツールカタログのスモークテスト"""

from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def test_get_spot_graph_specs_has_four_tools() -> None:
    specs = get_spot_graph_specs()
    assert len(specs) == 4
    names = {s[0].name for s in specs}
    assert "spot_graph_travel_to" in names
    assert "spot_graph_set_sub_location" in names
    assert "spot_graph_explore" in names
    assert "spot_graph_interact" in names


def test_spot_graph_formatter_uses_snapshot() -> None:
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_name="地下室",
        current_spot_description="暗い",
        travel_status_line=None,
        connection_lines=["- 扉 → 玄関（通行可）"],
        sub_location_lines=["- 北（現在ここ）"],
        object_lines=["- 箱 [ 開ける ]"],
        ground_item_lines=[],
    )
    dto = PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="地下室",
        current_spot_description="暗い",
        x=None,
        y=None,
        z=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=0,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snap,
    )
    text = SpotGraphCurrentStateFormatter().format(dto)
    assert "地下室" in text
    assert "接続先" in text
    assert "サブロケーション" in text


def test_spot_graph_formatter_falls_back_without_snapshot() -> None:
    dto = PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="広場",
        current_spot_description="",
        x=1,
        y=2,
        z=0,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=3,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=None,
    )
    text = SpotGraphCurrentStateFormatter().format(dto)
    assert "広場" in text
    assert "座標" in text
