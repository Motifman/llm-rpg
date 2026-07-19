"""同 spot snapshot の nearby_entities が is_down を surface する (#347 後続)。

ダウンしたプレイヤーは「(倒れて動かない)」と表記され、speech / give 対象
として明確に区別できる。OFF mode で過去の PlayerDownedEvent が観測 buffer
から流れた後でも、snapshot から「あの人が床に転がっている」と読める。
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


def _wrap(snap: SpotGraphPlayerSnapshotDto) -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1, player_name="P",
        current_spot_id=snap.current_spot_id,
        current_spot_name=snap.current_spot_name,
        current_spot_description=snap.current_spot_description,
        x=None, y=None, z=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ", weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[], view_distance=0,
        available_moves=None, total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snap,
    )


def _snap(**overrides) -> SpotGraphPlayerSnapshotDto:
    defaults: dict = dict(
        current_spot_id=1,
        current_spot_name="test",
        current_spot_description="d",
        travel_status_line=None,
    )
    defaults.update(overrides)
    return SpotGraphPlayerSnapshotDto(**defaults)


class TestNearbyEntityIsDown:
    """nearby_entities の is_down フラグが UI プロンプトに reflect される。"""

    def test_down_true(self) -> None:
        """is down True なら 倒れて動かない 接尾辞が付く。"""
        snap = _snap(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2, display_name="エイダ", is_down=True
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        dto = builder.build(current_state_text="(base)\n", current_state=_wrap(snap))
        assert '"エイダ" (倒れて動かない)' in dto.current_state_text

    def test_down_false(self) -> None:
        """isdownFalse は通常表記。"""
        snap = _snap(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2, display_name="ノア", is_down=False
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        dto = builder.build(current_state_text="(base)\n", current_state=_wrap(snap))
        # "ノア" は出るが "倒れて動かない" は出ない
        assert "ノア" in dto.current_state_text
        assert "倒れて動かない" not in dto.current_state_text

    def test_documented_behavior(self) -> None:
        """混在時は 該当する人のみ 接尾辞。"""
        snap = _snap(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2, display_name="エイダ", is_down=True
                ),
                SpotGraphNearbyEntityEntry(
                    entity_id=3, display_name="ノア", is_down=False
                ),
            ),
        )
        builder = SpotGraphUiContextBuilder()
        dto = builder.build(current_state_text="(base)\n", current_state=_wrap(snap))
        text = dto.current_state_text
        # エイダだけ接尾辞、ノアは無し
        assert '"エイダ" (倒れて動かない)' in text
        # ノアの行は "ノア" で終わって "倒れて" が続かない
        # PR-FF (Y_after_pr639_640): entity 名は ``""`` で囲まれる
        assert '"ノア"\n' in text or text.endswith('"ノア"')
