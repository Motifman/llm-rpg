"""``demos/world_runtime/world_episodic_wiring.py`` の単体テスト (Issue #283 後続)。

検証:
- ``is_episodic_enabled`` の env 解釈
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_runtime.world_episodic_wiring import (
    is_episodic_enabled,
    is_episodic_subjective_enabled,
)


class TestIsEpisodicEnabled:
    """``LLM_EPISODIC_ENABLED`` の env 解釈。"""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("1", True),
            ("true", True),
            ("True", True),
            ("YES", True),
            ("yes", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("", False),
            ("garbage", False),
        ],
    )
    def test_string(self, raw: str, expected: bool) -> None:
        """各種文字列の解釈。"""
        env = {"LLM_EPISODIC_ENABLED": raw}
        assert is_episodic_enabled(env) is expected

    def test_unset_false(self) -> None:
        """未設定なら False。"""
        assert is_episodic_enabled({}) is False


class TestIsEpisodicSubjectiveEnabled:
    """``LLM_EPISODIC_SUBJECTIVE_ENABLED`` の env 解釈。**既定 True**。

    第22回実験以降「エピソード記憶を使うときは LLM 補完も既定で走らせたい」
    方針になったため、明示的に OFF にしたいときだけ falsy 値を指定する。
    """

    def test_unset_true_default(self) -> None:
        """key 自体が無いとき既定 ON。"""
        assert is_episodic_subjective_enabled({}) is True

    def test_empty_string_true_default(self) -> None:
        """空文字は「key だけ設定されたが値なし」と同じ扱いで既定 ON。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": ""}) is True

    @pytest.mark.parametrize("raw", ["0", "false", "False", "no", "NO", "off"])
    def test_off_string_false(self, raw: str) -> None:
        """明示的 off 文字列で False。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": raw}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
    def test_string_true(self, raw: str) -> None:
        """明示的 on 文字列で True。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": raw}) is True

    def test_value_true_default(self) -> None:
        """誤設定で機能が消えるより、on 側に倒して通知する方が安全。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": "garbage"}) is True

