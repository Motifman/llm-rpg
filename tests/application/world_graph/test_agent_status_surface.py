"""busy 状態の snapshot surface 検証 (travel 中の agent_status)。

LLM プロンプトに「あなたは移動中、軽い行動だけ並行可能」が読める形で出ること、
busy=False (rest 状態) のときは section ごと出ないことを確認する。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphAgentStatusEntry,
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


class TestAgentStatusSurface:
    """agent_status の busy フラグが UI プロンプトに reflect される。"""

    def test_busy_True_なら_現在の行動状態_section_が_追記される(self) -> None:
        snap = _snap(
            agent_status=SpotGraphAgentStatusEntry(
                busy=True,
                busy_reason="山頂への移動中",
                remaining_ticks=3,
                interruptible=True,
            ),
        )
        builder = SpotGraphUiContextBuilder()
        dto = builder.build(current_state_text="(base)\n", current_state=_wrap(snap))
        text = dto.current_state_text
        assert "現在の行動状態:" in text
        assert "山頂への移動中 (残り 3 tick)" in text
        # 中断可能の説明も出る
        assert "軽い行動" in text and "重い行動" in text

    def test_busy_False_なら_section_は_出ない(self) -> None:
        snap = _snap()  # default = busy=False
        builder = SpotGraphUiContextBuilder()
        dto = builder.build(current_state_text="(base)\n", current_state=_wrap(snap))
        assert "現在の行動状態" not in dto.current_state_text

    def test_busy_かつ_interruptible_False_なら_中断説明は出ない(self) -> None:
        snap = _snap(
            agent_status=SpotGraphAgentStatusEntry(
                busy=True,
                busy_reason="儀式の最中",
                remaining_ticks=2,
                interruptible=False,
            ),
        )
        builder = SpotGraphUiContextBuilder()
        dto = builder.build(current_state_text="(base)\n", current_state=_wrap(snap))
        text = dto.current_state_text
        assert "儀式の最中" in text
        # 中断可能性の文言が出ない
        assert "軽い行動" not in text
