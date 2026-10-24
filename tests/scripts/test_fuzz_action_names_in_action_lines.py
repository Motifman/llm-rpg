"""でたらめに動かす入口が、行動の行の要約に出たシナリオの操作名を漏れとして見つけることを保証する (#1564)。

操作名 (action_name) は呼び出しの値で、世界の言葉ではない。候補の行と ``呼び出し:`` の続き行には
渡すための値として正しく出るので、``find_leaks`` では拾えない。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.fuzz_scenario_with_random_agents import (
    find_action_names_in_action_lines,
    run_random_agents,
    scenario_action_names,
)

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"


class TestDetectsActionNamesInActionLines:
    """行動の行の要約 (``[行動]`` から ``→`` まで) か成功の結果に操作名が出たときだけ漏れとして返す。"""

    def test_failed_interact_line_written_with_the_action_name_is_reported(self) -> None:
        """失敗した働きかけの行が「「カンテラ」に light_lamp した」と操作名で書かれていたら、その行を返す。"""
        line = "- [Day 1 10:00] [行動] 「カンテラ」に light_lamp した → [失敗] | 行動が拒否された: カンテラに足す油が無い。"

        assert find_action_names_in_action_lines(line, frozenset({"light_lamp"})) == [line.strip()]

    def test_succeeded_result_written_with_the_action_name_is_reported(self) -> None:
        """成功の結果が「「open_thaw_valve」の側を受け持った」と操作名で語っていたら、その行を返す。

        結果の文も本人の経験として記憶へ流れる。世界で起きたことを呼び出しの値で語らない。
        """
        line = "- [深夜 2:15] [行動] 「解氷弁」に働きかけた → [結果] 「open_thaw_valve」の側を受け持った。まだ動いていない。"

        assert find_action_names_in_action_lines(line, frozenset({"open_thaw_valve"})) == [line.strip()]

    @pytest.mark.parametrize(
        "text",
        [
            '- [Day 1 10:00] [行動] 「カンテラ」で油を足して灯す → [結果] 灯がともった\n  呼び出し: interact(target_label="カンテラ", action_name="light_lamp")',
            "- [Day 1 10:00] [行動] 「金庫」で調べる → [失敗] | 'light_lamp' という操作はありません",
            '- "カンテラ" [油を足して灯す → "light_lamp"]',
        ],
    )
    def test_action_name_outside_the_summary_of_an_action_line_is_not_reported(self, text: str) -> None:
        """呼び出しの続き行・失敗の結果・候補の行に出る操作名は、渡した値か渡せる値なので拾わない。"""
        assert find_action_names_in_action_lines(text, frozenset({"light_lamp"})) == []

    def test_scenario_action_names_are_read_from_interactions(self) -> None:
        """廃坑の山村の宣言から、カンテラを灯す操作名 light_lamp を読み取る。"""
        assert "light_lamp" in scenario_action_names(_SCENARIOS / "mine_village_v1.json")


class TestPretendActionLines:
    """偽装の操作が、本物と同じ表示名で行動の行に書かれることを run で見張る。"""

    def test_pretend_action_line_does_not_show_the_pretend_name(self) -> None:
        """偽装の操作 (``*_pretend``) を選ぶシードで回しても、行動の行の要約に操作名が出ない。

        ツールが増減するとでたらめな選び方の分布がずれるので、シードを 1 つに決めず、
        偽装の操作を選んだ最初のシードで確かめる。
        """
        scenario = _SCENARIOS / "station_drill.json"
        for seed in range(20):
            result = run_random_agents(scenario, seed=seed, max_world_ticks=5)
            if any(
                str(a.arguments.get("action_name", "")).endswith("_pretend")
                for a in result.actions
            ):
                break
        else:
            pytest.fail("シード 0〜19 のどれも偽装の操作を選ばなかった。何も確かめていない")
        names = scenario_action_names(scenario)
        assert [f for f in result.findings if find_action_names_in_action_lines(f.detail, names)] == []
