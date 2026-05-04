"""Step 6: スポットグラフ用フォーマッタ・ツールカタログ・UiContextBuilder のスモークテスト"""

from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphAtmosphereEntry,
    SpotGraphConnectionEntry,
    SpotGraphInteractionEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
    SpotGraphSubLocationEntry,
    SpotGraphWeatherEntry,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(snap: SpotGraphPlayerSnapshotDto) -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=snap.current_spot_id,
        current_spot_name=snap.current_spot_name,
        current_spot_description=snap.current_spot_description,
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


def test_get_spot_graph_specs_has_nine_tools() -> None:
    specs = get_spot_graph_specs()
    assert len(specs) == 9
    names = {s[0].name for s in specs}
    assert "spot_graph_travel_to" in names
    assert "spot_graph_set_sub_location" in names
    assert "spot_graph_explore" in names
    assert "spot_graph_interact" in names
    assert "spot_graph_prepare_action" in names
    assert "spot_graph_use_item" in names
    assert "spot_graph_wait" in names
    assert "speech_say" in names
    assert "speech_whisper" in names


def test_spot_graph_specs_use_labels_not_ids() -> None:
    specs = get_spot_graph_specs()
    for defn, _ in specs:
        props = defn.parameters.get("properties", {})
        assert "destination_spot_id" not in props, f"{defn.name} should not expose raw IDs"
        assert "object_id" not in props, f"{defn.name} should not expose raw IDs"
        assert "sub_location_id" not in props, f"{defn.name} should not expose raw IDs"


def test_spot_graph_specs_require_inner_thought() -> None:
    """全ツールに inner_thought があり、required に含まれる。"""
    specs = get_spot_graph_specs()
    for defn, _ in specs:
        req = defn.parameters.get("required") or []
        props = defn.parameters.get("properties") or {}
        assert "inner_thought" in props, defn.name
        assert "inner_thought" in req, defn.name


def test_spot_graph_formatter_outputs_base_info() -> None:
    """フォーマッタは場所・雰囲気・時刻のベーステキストのみを出力する。"""
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="地下室",
        current_spot_description="暗い",
        travel_status_line=None,
        atmosphere=SpotGraphAtmosphereEntry(
            lighting="DIM", sound_ambient="水滴の音", temperature="COLD", smell="カビ",
        ),
    )
    dto = _make_dto(snap)
    text = SpotGraphCurrentStateFormatter().format(dto)
    assert "地下室" in text
    assert "暗い" in text
    assert "DIM" in text
    assert "水滴の音" in text
    assert "COLD" in text
    assert "カビ" in text


def test_spot_graph_ui_context_builder_adds_labels() -> None:
    """UiContextBuilder が接続先・オブジェクト・サブロケーションにラベルを付与する。"""
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="地下室",
        current_spot_description="暗い",
        travel_status_line=None,
        connections=(
            SpotGraphConnectionEntry(
                destination_spot_id=2,
                connection_name="扉",
                destination_spot_name="玄関",
                is_passable=True,
            ),
        ),
        objects=(
            SpotGraphObjectEntry(
                object_id=10,
                name="箱",
                description="古い木箱",
                interactions=(
                    SpotGraphInteractionEntry(action_name="open", display_label="開ける"),
                ),
            ),
        ),
        sub_locations=(
            SpotGraphSubLocationEntry(
                sub_location_id=5,
                name="北",
                is_current=True,
                is_hidden=False,
            ),
        ),
    )
    dto = _make_dto(snap)
    base_text = "現在地: 地下室"
    result = SpotGraphUiContextBuilder().build(base_text, dto)

    assert "S1" in result.current_state_text
    assert "玄関" in result.current_state_text
    assert "OBJ1" in result.current_state_text
    assert "箱" in result.current_state_text
    assert "開ける" in result.current_state_text
    assert "SL1" in result.current_state_text
    assert "北" in result.current_state_text

    targets = result.tool_runtime_context.targets
    assert "S1" in targets
    assert targets["S1"].spot_id == 2
    assert "OBJ1" in targets
    assert targets["OBJ1"].world_object_id == 10
    assert "SL1" in targets
    assert targets["SL1"].sub_location_id == 5
    assert result.tool_runtime_context.current_spot_id == 1
    assert result.tool_runtime_context.current_sub_location_id == 5


def test_spot_graph_ui_context_first_is_current_wins_when_multiple_marked_current() -> None:
    """is_current が複数 True のとき先頭の sub_location_id を採用する（仕様固定）。"""
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="地下室",
        current_spot_description="暗い",
        travel_status_line=None,
        sub_locations=(
            SpotGraphSubLocationEntry(
                sub_location_id=5,
                name="北",
                is_current=True,
                is_hidden=False,
            ),
            SpotGraphSubLocationEntry(
                sub_location_id=9,
                name="南",
                is_current=True,
                is_hidden=False,
            ),
        ),
    )
    dto = _make_dto(snap)
    result = SpotGraphUiContextBuilder().build("現在地: 地下室", dto)
    assert result.tool_runtime_context.current_sub_location_id == 5


def test_spot_graph_formatter_shows_weather_for_outdoor() -> None:
    """屋外スポットで天候がある場合、天候行が表示される。"""
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=3,
        current_spot_name="外",
        current_spot_description="外に出た",
        travel_status_line=None,
        atmosphere=None,
        weather=SpotGraphWeatherEntry(
            weather_type="FOG",
            weather_intensity=0.6,
            is_outdoor=True,
        ),
    )
    dto = _make_dto(snap)
    text = SpotGraphCurrentStateFormatter().format(dto)
    assert "天候" in text
    assert "霧" in text
    assert "屋外" in text


def test_spot_graph_formatter_omits_weather_for_indoor() -> None:
    """屋内スポットでは weather=None のため天候行が出ない。"""
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="地下室",
        current_spot_description="暗い",
        travel_status_line=None,
        atmosphere=SpotGraphAtmosphereEntry(
            lighting="DIM", sound_ambient="水滴の音", temperature="COLD", smell="カビ",
        ),
        weather=None,
    )
    dto = _make_dto(snap)
    text = SpotGraphCurrentStateFormatter().format(dto)
    assert "天候" not in text


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
