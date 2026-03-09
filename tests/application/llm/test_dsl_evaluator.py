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
        """サポート外の形式（keyword arg）で DslParseException または DslEvaluationException"""
        with pytest.raises((DslParseException, DslEvaluationException)):
            eval_expr("episodic.where(x=1)", [])

    def test_take_negative_unmatched_form(self):
        """take(-1) は DslParseException または DslEvaluationException"""
        with pytest.raises((DslParseException, DslEvaluationException)):
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
        """未サポートメソッドまたは不正な引数で DslParseException"""
        with pytest.raises(DslParseException):
            eval_expr("episodic.unknown_method(1)", [])

    def test_join_truncate_pack_unsupported(self):
        """join, truncate, pack は未サポートのため DslParseException"""
        data = [{"id": "e1"}]
        for method in ("join", "truncate", "pack"):
            with pytest.raises(DslParseException, match="Unsupported method"):
                eval_expr(f"episodic.{method}(1)", data)


class TestDslEvaluatorEdgeCases:
    """DSL 境界値・エッジケース"""

    def test_take_large_n_returns_available(self):
        """take(999999) はデータ件数分のみ返す"""
        data = [{"id": f"e{i}"} for i in range(3)]
        got = eval_expr("episodic.take(999999)", data)
        assert len(got) == 3

    def test_take_exactly_length_returns_all(self):
        """take(n) がデータ件数と同一のとき全件"""
        data = [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]
        got = eval_expr("facts.take(3)", data)
        assert len(got) == 3
        assert got[2]["id"] == "e3"

    def test_var_name_with_underscore_accepted(self):
        """アンダースコア付き変数名がパースできる"""
        data = [{"id": "e1"}]
        got = eval_expr("my_episodic.take(1)", data)
        assert len(got) == 1

    def test_expr_trailing_junk_rejected(self):
        """expr 末尾の余計な文字はパースに失敗する"""
        with pytest.raises(DslParseException):
            eval_expr("episodic.take(5)x", [])

    def test_expr_leading_whitespace_accepted(self):
        """expr 先頭のスペースは strip で許容"""
        data = [{"id": "e1"}]
        got = eval_expr("  episodic.take(1)", data)
        assert len(got) == 1

    def test_data_with_non_dict_items_returned_as_is(self):
        """data に dict 以外が含まれてもそのまま返す（フォーマット層の責務）"""
        data = [{"id": "e1"}, "string_item", 42]
        got = eval_expr("episodic.take(3)", data)
        assert len(got) == 3
        assert got[0] == {"id": "e1"}
        assert got[1] == "string_item"
        assert got[2] == 42


class TestDslEvaluatorExtended:
    """where, sort_by, drop, select, has_any, contains, eq のテスト"""

    def test_where_has_any_filters(self):
        """where(has_any("entity_ids", ["スライム"])) でフィルタ"""
        data = [
            {"id": "1", "entity_ids": ["スライム", "ゴブリン"]},
            {"id": "2", "entity_ids": ["ドラゴン"]},
            {"id": "3", "entity_ids": ["ゴブリン"]},
        ]
        got = eval_expr(
            'episodic.where(has_any("entity_ids", ["スライム"])).take(10)',
            data,
        )
        assert len(got) == 1
        assert got[0]["id"] == "1"

    def test_sort_by_ascending(self):
        """sort_by("timestamp") で昇順"""
        data = [
            {"id": "2", "timestamp": "2024-02-01"},
            {"id": "1", "timestamp": "2024-01-01"},
            {"id": "3", "timestamp": "2024-03-01"},
        ]
        got = eval_expr('episodic.sort_by("timestamp").take(10)', data)
        assert [g["id"] for g in got] == ["1", "2", "3"]

    def test_sort_by_descending(self):
        """sort_by("-timestamp") で降順"""
        data = [
            {"id": "2", "timestamp": "2024-02-01"},
            {"id": "1", "timestamp": "2024-01-01"},
            {"id": "3", "timestamp": "2024-03-01"},
        ]
        got = eval_expr('episodic.sort_by("-timestamp").take(10)', data)
        assert [g["id"] for g in got] == ["3", "2", "1"]

    def test_drop_skips(self):
        """drop(2) で先頭2件をスキップ"""
        data = [{"id": f"e{i}"} for i in range(5)]
        got = eval_expr("episodic.drop(2).take(10)", data)
        assert len(got) == 3
        assert got[0]["id"] == "e2"

    def test_contains_filters(self):
        """contains("content", "属性") で部分一致フィルタ"""
        data = [
            {"id": "1", "content": "火属性の呪文"},
            {"id": "2", "content": "氷属性"},
            {"id": "3", "content": "炎の剣"},
        ]
        got = eval_expr('facts.where(contains("content", "属性")).take(10)', data)
        assert len(got) == 2
        assert got[0]["id"] == "1"
        assert got[1]["id"] == "2"

    def test_select_extracts_fields(self):
        """select("id", "content") でフィールド抽出"""
        data = [
            {"id": "1", "content": "a", "extra": "x"},
            {"id": "2", "content": "b"},
        ]
        got = eval_expr('episodic.select("id", "content").take(10)', data)
        assert got == [{"id": "1", "content": "a"}, {"id": "2", "content": "b"}]


class TestDslEvaluatorValidationAndEdgeCases:
    """バリデーション・エッジケースの追加テスト"""

    def test_select_empty_args_raises(self):
        """select() に引数なしで DslEvaluationException"""
        with pytest.raises(DslEvaluationException, match="at least 1 argument"):
            eval_expr("episodic.select().take(10)", [{"id": "1"}])

    def test_where_non_callable_arg_raises(self):
        """where に述語でない値（数値など）を渡すと DslEvaluationException"""
        with pytest.raises(
            DslEvaluationException,
            match="where\\(\\) argument must be predicate",
        ):
            eval_expr("episodic.where(1).take(10)", [{"id": "1"}])

    def test_sort_by_empty_field_raises(self):
        """sort_by に空の field で DslEvaluationException"""
        with pytest.raises(
            DslEvaluationException,
            match="non-empty field",
        ):
            eval_expr('episodic.sort_by("").take(10)', [{"id": "1"}])

    def test_sort_by_minus_only_raises(self):
        """sort_by("-") はキーフィールドが空で DslEvaluationException"""
        with pytest.raises(
            DslEvaluationException,
            match="non-empty field",
        ):
            eval_expr('episodic.sort_by("-").take(10)', [{"id": "1"}])

    def test_take_float_raises(self):
        """take に float を渡すと DslEvaluationException"""
        with pytest.raises(DslEvaluationException, match="n to be int"):
            eval_expr("episodic.take(3.5)", [{"id": "1"}])

    def test_drop_negative_raises(self):
        """drop(-1) は DslEvaluationException"""
        with pytest.raises(DslEvaluationException, match="n >= 0"):
            eval_expr("episodic.drop(-1).take(10)", [{"id": "1"}])

    def test_unsupported_predicate_raises(self):
        """未サポートの述語で DslParseException"""
        with pytest.raises(DslParseException, match="Unsupported predicate"):
            eval_expr('episodic.where(invalid_pred("x", 1)).take(10)', [{"id": "1"}])

    def test_has_any_wrong_arg_count_raises(self):
        """has_any に引数1つで DslEvaluationException"""
        with pytest.raises(DslEvaluationException, match="requires 2 arguments"):
            eval_expr('episodic.where(has_any("field")).take(10)', [{"field": "a"}])

    def test_eq_filters_correctly(self):
        """eq(field, value) で等価フィルタ"""
        data = [
            {"id": "1", "status": "active"},
            {"id": "2", "status": "inactive"},
            {"id": "3", "status": "active"},
        ]
        got = eval_expr('episodic.where(eq("status", "active")).take(10)', data)
        assert len(got) == 2
        assert got[0]["id"] == "1"
        assert got[1]["id"] == "3"

    def test_ge_filters_correctly(self):
        """ge(field, value) で以上フィルタ"""
        data = [
            {"id": "1", "level": 5},
            {"id": "2", "level": 3},
            {"id": "3", "level": 7},
        ]
        got = eval_expr("episodic.where(ge(\"level\", 5)).take(10)", data)
        assert len(got) == 2
        assert got[0]["id"] == "1"
        assert got[1]["id"] == "3"

    def test_le_filters_correctly(self):
        """le(field, value) で以下フィルタ"""
        data = [
            {"id": "1", "count": 2},
            {"id": "2", "count": 5},
            {"id": "3", "count": 1},
        ]
        got = eval_expr("episodic.where(le(\"count\", 2)).take(10)", data)
        assert len(got) == 2
        assert got[0]["id"] == "1"
        assert got[1]["id"] == "3"

    def test_select_missing_fields_omitted(self):
        """select で存在しないフィールドは結果に含まれない"""
        data = [{"id": "1", "a": "x"}, {"id": "2"}]
        got = eval_expr('episodic.select("id", "missing").take(10)', data)
        assert got == [{"id": "1"}, {"id": "2"}]
