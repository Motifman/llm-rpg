"""Issue #171a: SpotGraphCurrentStateFormatter が tick_budget_remaining を
「残り行動可能 tick」として LLM プロンプトに載せるかを検証する。

設計判断:
- WIN 条件には触れない (メタ情報のみ)。シナリオに TICK_LIMIT lose_condition が
  あるときの「時間切れまでの猶予」だけ伝える。
- 制限が無いシナリオ (tick_budget_remaining=None) ではセクションごと出さない。
- 残り 0 以下なら「時間切れ寸前」を明示し、LLM の最後の一押しを促す。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(
    *, tick_budget_remaining: int | None
) -> PlayerCurrentStateDto:
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="dummy",
        current_spot_description="",
        travel_status_line=None,
    )
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
        tick_budget_remaining=tick_budget_remaining,
    )


class TestTickBudgetRendering:
    """tick_budget_remaining のプロンプト表示。"""

    def test_renders_positive_remaining(self) -> None:
        """正の残量は「残り行動可能 tick: N」として出る。"""
        text = SpotGraphCurrentStateFormatter().format(
            _make_dto(tick_budget_remaining=42)
        )
        assert "残り行動可能 tick: 42" in text

    def test_renders_zero_as_imminent(self) -> None:
        """残り 0 のときは「時間切れ寸前」が明示される。"""
        text = SpotGraphCurrentStateFormatter().format(
            _make_dto(tick_budget_remaining=0)
        )
        assert "残り行動可能 tick: 0" in text
        assert "時間切れ寸前" in text

    def test_negative_clamped_to_imminent(self) -> None:
        """負値 (理論上来ないが防御的に) も「時間切れ寸前」として扱う。"""
        text = SpotGraphCurrentStateFormatter().format(
            _make_dto(tick_budget_remaining=-3)
        )
        assert "時間切れ寸前" in text

    def test_section_omitted_when_none(self) -> None:
        """tick_budget_remaining=None ならセクションは出ない (時間制限なしシナリオ)。"""
        text = SpotGraphCurrentStateFormatter().format(
            _make_dto(tick_budget_remaining=None)
        )
        assert "残り行動可能 tick" not in text

    def test_does_not_leak_win_condition(self) -> None:
        """tick budget セクションには WIN 関連の語彙が紛れていない。"""
        text = SpotGraphCurrentStateFormatter().format(
            _make_dto(tick_budget_remaining=10)
        )
        # 念のため WIN 系語彙が出てないことを軽くチェック (回帰防止)
        for forbidden in ("勝利", "WIN", "ゴール", "脱出", "ALL_AT_SPOT", "FLAG_SET"):
            assert forbidden not in text
