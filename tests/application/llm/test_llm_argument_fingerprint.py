"""llm_argument_fingerprint のテスト。"""

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    NARRATIVE_ARG_FIELDS,
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    ACTION_HISTORY_PROJECTION_KEY,
)


def test_fingerprint_empty_dict() -> None:
    assert build_argument_fingerprint({}) == "{}"


def test_fingerprint_sorts_keys() -> None:
    a = build_argument_fingerprint({"z": 1, "a": 2})
    b = build_argument_fingerprint({"a": 2, "z": 1})
    assert a == b


def test_fingerprint_none_is_empty_object_string() -> None:
    assert build_argument_fingerprint(None) == "{}"


def test_fingerprint_strips_narrative_fields_by_default() -> None:
    """Issue #264 後続: inner_thought 等の narrative は default で除外される。

    これにより「同じ wait を違う inner_thought で連打」が同一 fingerprint と判定され、
    loop_guard が機能する。
    """
    a = build_argument_fingerprint(
        {"inner_thought": "心が躍る", "destination_label": "S1"}
    )
    b = build_argument_fingerprint(
        {"inner_thought": "心が沈む", "destination_label": "S1"}
    )
    assert a == b == '{"destination_label": "S1"}'


def test_fingerprint_strip_narrative_false_keeps_all_fields() -> None:
    """strip_narrative=False (旧挙動) なら narrative も含めて fingerprint する。"""
    a = build_argument_fingerprint(
        {"inner_thought": "心が躍る", "destination_label": "S1"},
        strip_narrative=False,
    )
    b = build_argument_fingerprint(
        {"inner_thought": "心が沈む", "destination_label": "S1"},
        strip_narrative=False,
    )
    assert a != b
    assert "心が躍る" in a
    assert "心が沈む" in b


def test_fingerprint_strips_all_known_narrative_fields() -> None:
    """NARRATIVE_ARG_FIELDS に含まれる全 field が除外される。"""
    full_args = {f: f"value-{f}" for f in NARRATIVE_ARG_FIELDS}
    full_args["destination_label"] = "S1"
    result = build_argument_fingerprint(full_args)
    # destination_label のみ残る
    assert result == '{"destination_label": "S1"}'


def test_fingerprint_pure_narrative_args_become_empty() -> None:
    """narrative だけの引数は除外後に空 dict になる。

    spot_graph_wait の typical case (inner_thought + reason のみ) で、
    全 LLM 試行が同じ fingerprint = '{}' になり、3 回連続検知が成立する。
    """
    a = build_argument_fingerprint({"inner_thought": "落ち着こう", "reason": "様子見"})
    b = build_argument_fingerprint({"inner_thought": "焦りそうだ", "reason": "様子伺い"})
    assert a == b == "{}"


class TestSameActionWithDifferentWordsOrQuotes:
    """発言と対象名の引用符の違いを、同じ行動かの比較から外すことを保証する (#1594)。"""

    def test_actions_that_differ_only_in_say_inline_share_a_fingerprint(self) -> None:
        """同じ金庫に同じ番号で働きかけ、say_inline だけが違う 2 回は、同じ fingerprint になる。"""
        base = {"target_label": "金庫", "action_name": "open_safe", "parameters": {"text": "1907"}}

        a = build_argument_fingerprint({**base, "say_inline": "この番号で合わせてみる。"})
        b = build_argument_fingerprint({**base, "say_inline": "番号の渡し方を変えて試す。"})
        c = build_argument_fingerprint(base)

        assert a == b == c

    def test_quoted_and_unquoted_identifiers_share_a_fingerprint(self) -> None:
        """target_label と action_name を引用符つきで渡した呼び出しは、引用符なしと同じ fingerprint になる。"""
        quoted = build_argument_fingerprint(
            {"target_label": '"金庫"', "action_name": "'open_safe'"}
        )
        plain = build_argument_fingerprint({"target_label": "金庫", "action_name": "open_safe"})

        assert quoted == plain

    def test_resolved_identifiers_carried_by_dispatch_replace_the_raw_ones(self) -> None:
        """dispatch が載せた解決済みの識別値が生値と違えば解決済みの値で比べ、運搬用のキーそのものは比べない。"""
        carried = {
            "target_label": "S2: 金庫",
            "action_name": "open_safe",
            ACTION_HISTORY_PROJECTION_KEY: (
                {"target_label": "金庫", "action_name": "open_safe"},
                ("parameters", "say_inline"),
            ),
        }
        plain = {
            "target_label": "金庫",
            "action_name": "open_safe",
            ACTION_HISTORY_PROJECTION_KEY: ({"target_label": "金庫", "action_name": "open_safe"}, ()),
        }

        assert build_argument_fingerprint(carried) == build_argument_fingerprint(plain)
        assert ACTION_HISTORY_PROJECTION_KEY not in build_argument_fingerprint(carried)

    def test_quotes_carried_raw_by_dispatch_are_stripped_too(self) -> None:
        """解決済みの値を報告しない resolver で、dispatch が引用符つきの生値を運んでも、引用符なしと同じ fingerprint になる。"""
        carried = {
            "item_label": '"松明"',
            ACTION_HISTORY_PROJECTION_KEY: ({"item_label": '"松明"'}, ()),
        }

        assert build_argument_fingerprint(carried) == build_argument_fingerprint({"item_label": "松明"})

    def test_speak_content_is_the_action_and_stays_in_the_fingerprint(self) -> None:
        """speak の content は発言そのものが行動なので外さず、内容が違えば fingerprint も違う。"""
        a = build_argument_fingerprint({"channel": "say", "content": "鍵を探そう"})
        b = build_argument_fingerprint({"channel": "say", "content": "金庫を開けよう"})

        assert a != b

    def test_quotes_inside_free_text_are_kept(self) -> None:
        """speak の content のような自由文は、両端の引用符も中身として比べる。"""
        quoted = build_argument_fingerprint({"channel": "say", "content": '"助けて"'})
        plain = build_argument_fingerprint({"channel": "say", "content": "助けて"})

        assert quoted != plain
