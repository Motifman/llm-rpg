"""同席プレイヤーの「死亡」を「(倒れて動かない)」(=蘇生可能なダウン) と
区別して表示することを保証する。

観察 (v3coop_postrefactor_001) で、DEAD になったプレイヤー (リオ, t55) が spot
表示上は蘇生可能なダウン者と完全に同一の「(倒れて動かない)」で描画され、仲間は
145 tick にわたりリオを「救助対象の生存者」として扱い続けた。DEAD は終局・復活
不可なので、蘇生を試みても無駄であることを表示から直接読み取れる必要がある。
LLM が小さな語を読み落とさないよう、婉曲でなく「死亡している」と直接的に出す。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphNearbyEntityEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(*entities: SpotGraphNearbyEntityEntry) -> PlayerCurrentStateDto:
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="広間",
        current_spot_description="",
        travel_status_line=None,
        nearby_entities=tuple(entities),
    )
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="広間",
        current_spot_description="",
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


class TestNearbyEntityDeadRendered:
    """is_dead な同席プレイヤーを downed と区別して直接的に表示する。"""

    def test_dead_entity_shows_death_directly(self) -> None:
        """is_dead=True の相手は「死亡している」と直接的に表示される。"""
        dto = _make_dto(
            SpotGraphNearbyEntityEntry(entity_id=3, display_name="リオ", is_dead=True)
        )
        text = SpotGraphUiContextBuilder().build("base", dto).current_state_text
        assert '- "リオ"' in text
        assert "死亡" in text

    def test_dead_not_shown_as_mere_downed(self) -> None:
        """死亡者は蘇生可能なダウンの「(倒れて動かない)」では表示しない
        (= 蘇生を試みる誤解を誘発しない)。"""
        dto = _make_dto(
            SpotGraphNearbyEntityEntry(
                entity_id=3, display_name="リオ", is_down=True, is_dead=True
            )
        )
        text = SpotGraphUiContextBuilder().build("base", dto).current_state_text
        rio_line = next(l for l in text.splitlines() if "リオ" in l)
        assert "死亡" in rio_line
        assert "倒れて動かない" not in rio_line

    def test_downed_but_not_dead_still_shows_downed(self) -> None:
        """is_down だが is_dead でない相手は従来どおり「(倒れて動かない)」。"""
        dto = _make_dto(
            SpotGraphNearbyEntityEntry(
                entity_id=2, display_name="エイダ", is_down=True, is_dead=False
            )
        )
        text = SpotGraphUiContextBuilder().build("base", dto).current_state_text
        aida_line = next(l for l in text.splitlines() if "エイダ" in l)
        assert "倒れて動かない" in aida_line
        assert "死亡" not in aida_line

    def test_alive_entity_has_no_death_marker(self) -> None:
        """生存している相手には死亡表示が出ない。"""
        dto = _make_dto(
            SpotGraphNearbyEntityEntry(entity_id=2, display_name="カイ")
        )
        text = SpotGraphUiContextBuilder().build("base", dto).current_state_text
        assert "死亡" not in text
