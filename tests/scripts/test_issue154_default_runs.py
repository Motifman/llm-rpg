"""``issue154_full_tables_experiment.py`` の試行セット選択ロジック単体テスト
(Issue #295 後続: memo 既定路線化に伴う R2_pure の routine 除外)。

検証する不変条件:
- 環境変数未指定 → DEFAULT_RUN_KEYS のみが走る (= R2_pure は含まない)
- ISSUE154_RUNS=R2_pure と明示すれば opt-in 可能
- カンマ区切りで複数 opt-in 可能
- 全部不一致なら warning 付きで default に fallback
- ALL_RUNS には R2_pure が「opt-in 可能な選択肢」として残っている
"""

from __future__ import annotations

from scripts.issue154_full_tables_experiment import (
    ALL_RUNS,
    DEFAULT_RUN_KEYS,
    _select_runs,
)


class TestDefaultRunKeys:
    """既定セットの内容。"""

    def test_R2_pure_は既定から外れている(self) -> None:
        """memo を既定路線として扱うので、memo OFF アブレーションの
        R2_pure は routine から除外。"""
        assert "R2_pure" not in DEFAULT_RUN_KEYS

    def test_R1_default_は既定に含まれる(self) -> None:
        assert "R1_default" in DEFAULT_RUN_KEYS

    def test_R3_contention_は既定に含まれる(self) -> None:
        assert "R3_contention" in DEFAULT_RUN_KEYS

    def test_R2_pure_はopt_in可能な選択肢としてALL_RUNSには残る(self) -> None:
        """完全に削除しない: 「memo の効果を再評価したい」ときに
        ``ISSUE154_RUNS=R2_pure`` で復活できる必要がある。"""
        assert "R2_pure" in ALL_RUNS


class TestSelectRuns:
    """``_select_runs`` の挙動。"""

    def test_filter_未指定なら_default_run_keys_だけ走る(self) -> None:
        runs, warning = _select_runs(ALL_RUNS, DEFAULT_RUN_KEYS, "")
        assert set(runs.keys()) == set(DEFAULT_RUN_KEYS)
        assert warning == ""

    def test_R2_pure_を明示すれば_opt_in_できる(self) -> None:
        runs, warning = _select_runs(ALL_RUNS, DEFAULT_RUN_KEYS, "R2_pure")
        assert set(runs.keys()) == {"R2_pure"}
        assert warning == ""

    def test_カンマ区切りで複数_opt_in_可能(self) -> None:
        runs, warning = _select_runs(
            ALL_RUNS, DEFAULT_RUN_KEYS, "R1_default,R2_pure"
        )
        assert set(runs.keys()) == {"R1_default", "R2_pure"}
        assert warning == ""

    def test_全て不一致なら_default_に_fallback_して_warning(self) -> None:
        runs, warning = _select_runs(ALL_RUNS, DEFAULT_RUN_KEYS, "X_unknown")
        assert set(runs.keys()) == set(DEFAULT_RUN_KEYS)
        assert "X_unknown" in warning
        assert "既定セット" in warning

    def test_filter_の前後空白は_trim_される(self) -> None:
        runs, _ = _select_runs(
            ALL_RUNS, DEFAULT_RUN_KEYS, "  R2_pure  ,  R1_default  "
        )
        assert set(runs.keys()) == {"R1_default", "R2_pure"}
