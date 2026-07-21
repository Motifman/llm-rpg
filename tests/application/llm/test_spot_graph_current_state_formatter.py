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


class TestDistantViewSection:
    """常時遠景を現在地説明へ織り込む表示。"""

    def test_renders_distant_view_after_current_spot_description(self) -> None:
        """遠景文は現在地説明の直後に入り、独立見出しを作らない。"""
        snap = _empty_snap(
            current_spot_name="浜辺",
            current_spot_description="白い砂と流木が散らばっている。",
            distant_view_lines=("北東に切り立った山影が見える。",),
        )

        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))

        lines = text.splitlines()
        assert lines[:3] == [
            "現在地: 浜辺",
            "  白い砂と流木が散らばっている。",
            "  北東に切り立った山影が見える。",
        ]
        assert "遠景:" not in text

    def test_distant_view_does_not_render_internal_area_id(self) -> None:
        """遠景本文には area_id を出さず、visible_name 由来の文だけを表示する。"""
        snap = _empty_snap(
            distant_view_lines=("北東に切り立った山影が見える。",),
        )

        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))

        assert "切り立った山影" in text
        assert "internal_mountain" not in text
        assert "area_id" not in text


class TestObjectStateSection:
    """スポット内オブジェクトの state セクションの表示。"""

    def test_legacy_spot_state_block_not_output(self) -> None:
        """PR-X (Y_after_pr639_640 後続): object の state は
        SpotGraphUiContextBuilder._build_object_section が「オブジェクト:」
        section 内 inline (``(key=value)``) で表示する方針に統一。
        formatter の旧 block は削除された (重複と format 揺れを避けるため)。
        """
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
        # 旧 block は出さない。inline 版 (UiContextBuilder 経由) で表示する
        assert "スポット内オブジェクトの状態:" not in text

    def test_skips_objects_without_state(self) -> None:
        """state が空のオブジェクトは (旧仕様と同じく) このセクションに出ない。
        旧 block そのものが削除されたので trivially pass するが、期待動作
        として残す。"""
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

    def test_None_renders_as_null(self) -> None:
        """None は文字列の "None" ではなく "null" として表示される。"""
        snap = _empty_snap(player_state={"target": None})
        text = SpotGraphCurrentStateFormatter().format(_make_dto(snap))
        assert "target=null" in text
        assert "target=None" not in text
