"""行動者本人の HP 行が「身体の状態」section の先頭に出るか。

観察 (v3coop_postrefactor_001) で、プレイヤー自身の HP はプロンプトのどこにも
描画されておらず (空腹・疲労のみ)、エージェントは被弾観測を暗算で積み上げて
HP を推定するしかなかった。空腹・疲労と同じ「身体の状態」section に、値 +
前 turn からの増減つきで HP を出すことを保証する。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)


def _make_snapshot(hp_line: str = "", **overrides) -> SpotGraphPlayerSnapshotDto:
    defaults: dict = {
        "current_spot_id": 0,
        "current_spot_name": "",
        "current_spot_description": "",
        "travel_status_line": "",
        "need_lines": ("空腹: 問題なし（10/100）", "疲労: 問題なし（5/100）"),
        "hp_line": hp_line,
    }
    defaults.update(overrides)
    return SpotGraphPlayerSnapshotDto(**defaults)


def _render_state_section(snap: SpotGraphPlayerSnapshotDto) -> list[str]:
    builder = SpotGraphUiContextBuilder()
    lines: list[str] = []
    builder._build_needs_section(snap, lines)
    return lines


class TestOwnHpLineRendered:
    """hp_line が「身体の状態」section に描画される挙動を保証する。"""

    def test_hp_line_rendered_in_state_section(self) -> None:
        """hp_line があると「身体の状態」section に HP 行が出る。"""
        lines = _render_state_section(
            _make_snapshot(hp_line="HP: 消耗（48/100）、前回 -12")
        )
        joined = "\n".join(lines)
        assert "身体の状態:" in joined
        assert "HP: 消耗（48/100）、前回 -12" in joined

    def test_hp_line_precedes_need_lines(self) -> None:
        """HP 行は空腹・疲労より前 (= 本人が真っ先に読む位置) に出る。"""
        lines = _render_state_section(
            _make_snapshot(hp_line="HP: 良好（100/100）")
        )
        hp_idx = next(i for i, l in enumerate(lines) if "HP:" in l)
        hunger_idx = next(i for i, l in enumerate(lines) if "空腹" in l)
        assert hp_idx < hunger_idx

    def test_empty_hp_line_omitted(self) -> None:
        """hp_line が空なら HP 行は出ない (= 後方互換・ノイズ削減)。"""
        lines = _render_state_section(_make_snapshot(hp_line=""))
        assert all("HP:" not in line for line in lines)

    def test_state_section_shown_even_if_only_hp(self) -> None:
        """need_lines が空でも hp_line だけで「身体の状態」section が出る。"""
        lines = _render_state_section(
            _make_snapshot(hp_line="HP: 瀕死（10/100）、前回 -30", need_lines=())
        )
        joined = "\n".join(lines)
        assert "身体の状態:" in joined
        assert "HP: 瀕死（10/100）、前回 -30" in joined
