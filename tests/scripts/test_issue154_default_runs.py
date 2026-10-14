"""``issue154_full_tables_experiment.py`` の試行セット選択ロジック単体テスト。

検証する不変条件:
- 環境変数未指定 → DEFAULT_RUN_KEYS のみが走る
- ISSUE154_RUNS で 1 つだけ選べる
- カンマ区切りで複数選べる
- 全部不一致なら warning 付きで default に fallback
- memo を外すアブレーション R2_pure は #1631 で消したので、選択肢に無い
"""

from __future__ import annotations

from scripts.issue154_full_tables_experiment import (
    ALL_RUNS,
    DEFAULT_RUN_KEYS,
    _select_runs,
)


class TestDefaultRunKeys:
    """既定セットの内容。"""

    def test_r1_default_included(self) -> None:
        """R1 default は既定に含まれる。"""
        assert "R1_default" in DEFAULT_RUN_KEYS

    def test_r3_contention_default_included(self) -> None:
        """R3 contention は既定に含まれる。"""
        assert "R3_contention" in DEFAULT_RUN_KEYS

    def test_removed_r2_pure_is_not_selectable(self) -> None:
        """消した R2_pure は、選べる試行の一覧に無い。"""
        assert "R2_pure" not in ALL_RUNS


class TestSelectRuns:
    """``_select_runs`` の挙動。"""

    def test_filter_unspecified_default_run_keys(self) -> None:
        """filter 未指定なら default run keys だけ走る。"""
        runs, warning = _select_runs(ALL_RUNS, DEFAULT_RUN_KEYS, "")
        assert set(runs.keys()) == set(DEFAULT_RUN_KEYS)
        assert warning == ""

    def test_single_run_can_be_selected(self) -> None:
        """R3_contention だけを明示すれば、その 1 つだけが走る。"""
        runs, warning = _select_runs(ALL_RUNS, DEFAULT_RUN_KEYS, "R3_contention")
        assert set(runs.keys()) == {"R3_contention"}
        assert warning == ""

    def test_multiple_opt(self) -> None:
        """カンマ区切りで複数選べる。"""
        runs, warning = _select_runs(
            ALL_RUNS, DEFAULT_RUN_KEYS, "R1_default,R3_contention"
        )
        assert set(runs.keys()) == {"R1_default", "R3_contention"}
        assert warning == ""

    def test_emits_warning_for_all_default_fallback(self) -> None:
        """全て不一致なら default に fallback して warning。消した R2_pure を指定しても同じ。"""
        runs, warning = _select_runs(ALL_RUNS, DEFAULT_RUN_KEYS, "R2_pure")
        assert set(runs.keys()) == set(DEFAULT_RUN_KEYS)
        assert "R2_pure" in warning
        assert "既定セット" in warning

    def test_filter_around_blank_trim(self) -> None:
        """filter の前後空白は trim される。"""
        runs, _ = _select_runs(
            ALL_RUNS, DEFAULT_RUN_KEYS, "  R3_contention  ,  R1_default  "
        )
        assert set(runs.keys()) == {"R1_default", "R3_contention"}
