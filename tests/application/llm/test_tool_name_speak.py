"""``speech_speak`` から ``speak`` へのリネーム (Y_after_pr639_640 後続、PR-DD)。

Y_after_pr639_640 の分析で「speech_speak というツール名は分かりにくい」と
指摘された。歴史的経緯:
- 元々 SAY / WHISPER / SHOUT の 3 tool → PR #264 で channel 引数付きの
  1 tool に統合、tool_name を ``speech_speak`` に設定
- ``speech`` と ``speak`` が意味重複、prefix の意味が希薄

**変更**: tool 名を ``speak`` に短縮。channel enum {whisper, say, shout} で
音量を選ぶ設計は保持。RPG UI の慣習 (Skyrim 等の "Speak to NPC") にも
沿う。

Python 内の定数 ``TOOL_NAME_SPEECH`` は grep 継続性のため名前は据え置き、
値のみ ``"speak"`` に変更する。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH


class TestSpeakToolName:
    """発話 tool の名前が ``speak`` である。"""

    def test_tool_name_speech_value_speak(self) -> None:
        """``TOOL_NAME_SPEECH`` (歴史的名残の Python 定数) の値は ``"speak"``。
        LLM に露出する tool name はこの値で決まる。"""
        assert TOOL_NAME_SPEECH == "speak", (
            "PR-DD: 発話 tool 名を speech_speak → speak に短縮する"
        )

    def test_speech_tool_prefix(self) -> None:
        """``speech_`` などの冗長 prefix が含まれない (spot_graph_ prefix 廃止と
        同方針)。"""
        assert not TOOL_NAME_SPEECH.startswith("speech_"), (
            "冗長 prefix (speech_) を除去する"
        )
        assert not TOOL_NAME_SPEECH.startswith("spot_graph_")
