"""llm_argument_fingerprint のテスト。"""

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    NARRATIVE_ARG_FIELDS,
    build_argument_fingerprint,
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
