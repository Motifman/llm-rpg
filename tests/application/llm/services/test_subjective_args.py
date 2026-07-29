"""subjective_args (U2): raw tool arguments から主観入力 (心の声 / 予測 / 目的 / 感情) を
取り出す共有ヘルパの単体テスト。

full wiring (agent_orchestrator) と escape (runtime_manager) の両経路がこの
1 箇所を共有するため、抽出ルール (非 str / 空文字 → None) をここで固定する。
"""

from ai_rpg_world.application.llm.services.subjective_args import (
    extract_subjective_action_fields,
    extract_subjective_text,
)


class TestExtractSubjectiveText:
    """単一キーの抽出ルール (canonical 化前 raw args 由来)。"""

    def test_returns_stripped_text(self) -> None:
        """前後空白を落とした文字列を返す。"""
        assert extract_subjective_text({"expected_result": "  封印が解ける  "}, "expected_result") == "封印が解ける"

    def test_missing_key_is_none(self) -> None:
        """キーが無ければ None。"""
        assert extract_subjective_text({}, "intention") is None

    def test_empty_string_is_none(self) -> None:
        """空文字 (空白のみ含む) は None に倒す。"""
        assert extract_subjective_text({"intention": "   "}, "intention") is None

    def test_non_string_is_none(self) -> None:
        """非 str (数値・dict 等) は None に倒す。"""
        assert extract_subjective_text({"emotion_hint": 123}, "emotion_hint") is None
        assert extract_subjective_text({"emotion_hint": {"x": 1}}, "emotion_hint") is None


class TestExtractSubjectiveActionFields:
    """4 フィールド一括抽出 (do_* / recorder へ渡す形)。"""

    def test_extracts_all_four(self) -> None:
        """inner_thought / expected_result / intention / emotion_hint を dict で返す。"""
        out = extract_subjective_action_fields(
            {
                "expected_result": "封印が解ける",
                "intention": "封印を調べる",
                "emotion_hint": "curiosity",
                "inner_thought": "何か手掛かりがある。",
            }
        )
        assert out == {
            "inner_thought": "何か手掛かりがある。",
            "expected_result": "封印が解ける",
            "intention": "封印を調べる",
            "emotion_hint": "curiosity",
        }

    def test_absent_fields_are_none(self) -> None:
        """露出 OFF (キー無し) の現状では全 None になる。"""
        out = extract_subjective_action_fields({"inner_thought": "考えごと"})
        assert out == {
            "inner_thought": "考えごと",
            "expected_result": None,
            "intention": None,
            "emotion_hint": None,
        }

    def test_only_subjective_keys_returned(self) -> None:
        """主観入力以外のキーは返り値に含めない (do_* の余計な kwargs を避ける)。"""
        out = extract_subjective_action_fields({"inner_thought": "x", "object_label": "OBJ1"})
        assert set(out.keys()) == {
            "inner_thought",
            "expected_result",
            "intention",
            "emotion_hint",
        }
