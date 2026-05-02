"""llm_argument_fingerprint のテスト。"""

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
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
