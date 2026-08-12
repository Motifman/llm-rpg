"""共通シナリオ述語が不可能な定義を構築時に拒否する仕様。"""

import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    FlagSetPredicate,
    TickAtLeastPredicate,
)


class TestFlagSetPredicate:
    """世界フラグ名の型と空白条件を保証する。"""

    @pytest.mark.parametrize("flag_name", [None, "", "   ", 1, True])
    def test_rejects_missing_empty_or_non_string_name(self, flag_name: object) -> None:
        """空・空白のみ・文字列以外のフラグ名は定義時に拒否する。"""
        with pytest.raises(ScenarioPredicateValidationException):
            FlagSetPredicate(flag_name)  # type: ignore[arg-type]

    def test_preserves_exact_name_without_normalization(self) -> None:
        """大文字小文字や前後空白を勝手に変えず、完全一致用の名前を保持する。"""
        predicate = FlagSetPredicate(" Flag_A ")

        assert predicate.flag_name == " Flag_A "


class TestTickAtLeastPredicate:
    """tick閾値の型を保証し、既存の負数整数は意味を変えず保持する。"""

    @pytest.mark.parametrize("threshold", [None, True, False, "10", 1.5])
    def test_rejects_non_integer_threshold(self, threshold: object) -> None:
        """boolを含む整数以外の閾値は、型付き述語の構築時に拒否する。"""
        with pytest.raises(ScenarioPredicateValidationException):
            TickAtLeastPredicate(threshold)  # type: ignore[arg-type]

    @pytest.mark.parametrize("threshold", [-1, 0, 10])
    def test_preserves_integer_threshold(self, threshold: int) -> None:
        """入力厳格化を別PRへ分けるため、既存が受理する負数を含む整数を保持する。"""
        assert TickAtLeastPredicate(threshold).threshold == threshold
