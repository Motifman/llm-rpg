"""own_fatigue_level に応じた「身体の状態」section の hint が prompt に出るか。

Y_after_pr607 観察で発見した silent failure の回帰テスト。
旧構造では ``player_state["fatigue_level"]`` を読もうとしていたが、
``player_state`` は ``dict(player.state)`` (= 自由 state) しか乗らず、
``fatigue_level`` が常に None で _FATIGUE_OWN_HINT が一度も適用されていなかった。
専用 field ``own_fatigue_level`` 経由で正しく読まれることを保証する。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)


def _make_snapshot(own_fatigue_level: str = "ok", **overrides) -> SpotGraphPlayerSnapshotDto:
    defaults: dict = {
        "current_spot_id": 0,
        "current_spot_name": "",
        "current_spot_description": "",
        "travel_status_line": "",
        "need_lines": ("空腹: 問題なし（10/100）", "疲労: 問題なし（5/100）"),
        "own_fatigue_level": own_fatigue_level,
    }
    defaults.update(overrides)
    return SpotGraphPlayerSnapshotDto(**defaults)


def _render_state_section(snap: SpotGraphPlayerSnapshotDto) -> list[str]:
    builder = SpotGraphUiContextBuilder()
    lines: list[str] = []
    builder._build_needs_section(snap, lines)
    return lines


class TestOwnFatigueHintRendered:
    """own_fatigue_level に応じて _FATIGUE_OWN_HINT が prompt に出る挙動を保証する。"""

    def test_ok_tier_hint_not_rendered(self) -> None:
        """疲労 ok (= 0-29) では hint は省略され、無駄なノイズが乗らない。"""
        lines = _render_state_section(_make_snapshot(own_fatigue_level="ok"))
        joined = "\n".join(lines)
        assert "→" not in joined

    def test_tired_tier_hint_not_rendered(self) -> None:
        """疲労 tired (= 30-59) も hint なし (= _FATIGUE_OWN_HINT に未登録)。"""
        lines = _render_state_section(_make_snapshot(own_fatigue_level="tired"))
        joined = "\n".join(lines)
        assert "→" not in joined

    def test_fatigued_action_hint_rendered(self) -> None:
        """fatigued (60-84) で「動きが鈍くなっている。重い行動は控えめに」が出る。"""
        lines = _render_state_section(_make_snapshot(own_fatigue_level="fatigued"))
        joined = "\n".join(lines)
        assert "動きが鈍" in joined or "重い行動は控えめ" in joined

    def test_severe_hint_rendered(self) -> None:
        """severe (85-99) で「判断が鈍る・早めに休むこと」が出る。"""
        lines = _render_state_section(_make_snapshot(own_fatigue_level="severe"))
        joined = "\n".join(lines)
        assert "早めに休む" in joined

    def test_exhausted_block_tool_rendered(self) -> None:
        """exhausted (100) で「travel / attack / interact は実行できない」と
        block 対象が明示され、wait や食事での回復経路も併記される。
        Y_after_pr607 で agent がこの情報を読めず「動けない」と思い込んで
        wait 一辺倒になった silent failure を防ぐ。"""
        lines = _render_state_section(_make_snapshot(own_fatigue_level="exhausted"))
        joined = "\n".join(lines)
        assert "travel" in joined
        assert "attack" in joined
        assert "interact" in joined
        assert "wait" in joined or "食事" in joined

    def test_default_ok(self) -> None:
        """own_fatigue_level field を default のまま使うと ok と同じ挙動。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=0,
            current_spot_name="",
            current_spot_description="",
            travel_status_line="",
        )
        # default = "ok" なので hint は出ない
        lines = _render_state_section(snap)
        assert all("→" not in line for line in lines)

    def test_unknown_tier_does_not_crash(self) -> None:
        """不正な tier 文字列でも crash せず hint なしで終わる (= fallback)。"""
        lines = _render_state_section(_make_snapshot(own_fatigue_level="???"))
        joined = "\n".join(lines)
        assert "→" not in joined
