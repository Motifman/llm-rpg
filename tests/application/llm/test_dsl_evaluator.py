"""DslEvaluator のテスト（正常・境界・例外）"""

import pytest

from ai_rpg_world.application.llm.exceptions import (
    DslEvaluationException,
    DslParseException,
)
from ai_rpg_world.application.llm.services.dsl_evaluator import eval_expr


class TestDslEvaluator:
    """eval_expr の正常・境界・例外ケース"""

    def test_take_returns_first_n(self):
        """episodic.take(3) は先頭 3 件を返す"""
        data = [{"id": f"e{i}"} for i in range(5)]
        got = eval_expr("episodic.take(3)", data)
        assert len(got) == 3
        assert got[0]["id"] == "e0"
        assert got[1]["id"] == "e1"
        assert got[2]["id"] == "e2"

    def test_take_more_than_length_returns_all(self):
        """take(n) がデータ件数を超えるときは全件返す"""
        data = [{"id": "e1"}, {"id": "e2"}]
        got = eval_expr("facts.take(10)", data)
        assert len(got) == 2

    def test_take_zero_returns_empty(self):
        """take(0) は空リスト"""
        data = [{"id": "e1"}]
        got = eval_expr("episodic.take(0)", data)
        assert got == []

    def test_take_empty_data_returns_empty(self):
        """空データに take すると空リスト"""
        got = eval_expr("laws.take(5)", [])
        assert got == []

    def test_take_with_spaces_accepted(self):
        """take( 5 ) のようにスペースがあってもパースできる"""
        data = [{"id": "e1"}, {"id": "e2"}]
        got = eval_expr("episodic.take( 2 )", data)
        assert len(got) == 2

    def test_empty_expr_raises_parse_error(self):
        """空の expr で DslParseException"""
        with pytest.raises(DslParseException, match="must not be empty"):
            eval_expr("", [])

    def test_whitespace_only_expr_raises_parse_error(self):
        """空白のみの expr で DslParseException"""
        with pytest.raises(DslParseException, match="must not be empty"):
            eval_expr("   ", [])

    def test_invalid_form_raises_parse_error(self):
        """サポート外の形式で DslParseException"""
        with pytest.raises(DslParseException, match="Unsupported DSL form"):
            eval_expr("episodic.where(x=1)", [])

    def test_take_negative_unmatched_form(self):
        """take(-1) はサポート外形式として DslParseException"""
        with pytest.raises(DslParseException, match="Unsupported DSL form"):
            eval_expr("episodic.take(-1)", [])

    def test_expr_not_str_raises_parse_error(self):
        """expr が str でないとき DslParseException"""
        with pytest.raises(DslParseException, match="expr must be str"):
            eval_expr(123, [])  # type: ignore[arg-type]

    def test_data_not_list_raises_eval_error(self):
        """data が list でないとき DslEvaluationException"""
        with pytest.raises(DslEvaluationException, match="data must be list"):
            eval_expr("episodic.take(5)", "not a list")  # type: ignore[arg-type]

    def test_unknown_method_raises_parse_error(self):
        """take 以外のメソッドで DslParseException"""
        with pytest.raises(DslParseException, match="Unsupported DSL form"):
            eval_expr("episodic.sort_by(timestamp)", [])
