"""Phase 4-E: SpotGraphCurrentStateFormatter が「自分の state」と「スポット内
オブジェクトの state」をプロンプトに載せるかを検証する。

- snap.player_state を「自分の状態: ...」セクションとして出す
- snap.objects[*].state があれば「スポット内オブジェクトの状態:」セクションを出す
- HIDDEN な値も自分のものは載せる (本人プロンプトのみ)
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphInteractionEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(snap: SpotGraphPlayerSnapshotDto) -> PlayerCurrentStateDto:
    """SpotGraphCurrentStateFormatter は spot_graph_snapshot と
    current_game_time_label しか見ないが、PlayerCurrentStateDto は他に
    多数の必須フィールドを持つので合理的な空デフォルトで埋める。
    """
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="tester",
        current_spot_id=1,
        current_spot_name="dummy",
        current_spot_description="",
        x=0,
        y=0,
        z=0,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="CLEAR",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=0,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snap,
    )


def _empty_snap(**overrides) -> SpotGraphPlayerSnapshotDto:
    base = dict(
        current_spot_id=1,
        current_spot_name="酒場",
        current_spot_description="",
        travel_status_line=None,
    )
    base.update(overrides)
    return SpotGraphPlayerSnapshotDto(**base)


class TestPlayerStateSection:
    """自分の state セクションの表示。"""

    def test_renders_player_state_when_present(self) -> None:
        """player_state があれば「自分の状態」行に key=value で表示される。"""
        snap = _empty_snap(player_state={"poisoned": True, "buff_strength": 2})
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "自分の状態:" in text
        assert "poisoned=true" in text
        assert "buff_strength=2" in text

    def test_omits_section_when_empty(self) -> None:
        """player_state が空のときセクションは出ない。"""
        snap = _empty_snap(player_state={})
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "自分の状態:" not in text

    def test_includes_hidden_keys_for_self(self) -> None:
        """HIDDEN 相当の値 (毒・呪い等) も本人プロンプトには載る。"""
        snap = _empty_snap(player_state={"cursed": True})
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "cursed=true" in text


class TestObjectStateSection:
    """スポット内オブジェクトの state セクションの表示。"""

    def test_renders_object_state_when_present(self) -> None:
        """obj.state がある object は「スポット内オブジェクトの状態」セクションに出る。"""
        snap = _empty_snap(
            objects=(
                SpotGraphObjectEntry(
                    object_id=1,
                    name="燭台",
                    description="",
                    interactions=(),
                    state={"lit": True, "fuel": 5},
                ),
            ),
        )
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "スポット内オブジェクトの状態:" in text
        assert "燭台" in text
        assert "lit=true" in text
        assert "fuel=5" in text

    def test_skips_objects_without_state(self) -> None:
        """state が空のオブジェクトはこのセクションには出ない。"""
        snap = _empty_snap(
            objects=(
                SpotGraphObjectEntry(
                    object_id=1,
                    name="椅子",
                    description="",
                    interactions=(SpotGraphInteractionEntry("sit", "座る"),),
                    state={},
                ),
            ),
        )
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "スポット内オブジェクトの状態:" not in text


class TestRenderValue:
    """_render_value のエッジケース。"""

    def test_none_renders_as_null(self) -> None:
        """None は文字列の "None" ではなく "null" として表示される。"""
        snap = _empty_snap(player_state={"target": None})
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "target=null" in text
        assert "target=None" not in text
