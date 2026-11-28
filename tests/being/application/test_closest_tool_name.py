from __future__ import annotations

from ai_rpg_world.being.application.closest_tool_name import unsupported_tool_failure
from ai_rpg_world.being.contract import UNKNOWN, ObservedTime, OwnActionResult

NOW = ObservedTime(display="1日目 9:00")


class TestUnsupportedToolFailure:
    """unsupported_tool_failure が、出していないツールを選んだ 1 手を、近い名前と使えるツールを添えた自分の失敗にすることを保証する。"""

    def test_failure_names_the_closest_tool_and_the_offered_tools(self) -> None:
        """speech_speech を選ぶと、speech_speak を勧め、使えるツールを並べた文を、自分の 1 手の失敗として返す。"""
        failure = unsupported_tool_failure(
            requested="speech_speech",
            valid_tools=["travel_to", "speech_speak"],
            call_id="call_1",
            now=NOW,
            action_summary="speech_speech を実行しました。",
        )

        assert failure.suggestion == "speech_speak"
        assert failure.observation.body == (
            "未対応のツールです: speech_speech。もしかして 'speech_speak' ですか? 現在使える tool: [speech_speak, travel_to]"
        )
        assert failure.observation.route == OwnActionResult(
            call_id="call_1", succeeded=False, action_summary="speech_speech を実行しました。"
        )
        assert (failure.observation.time, failure.observation.subject_is_self, failure.observation.place) == (
            NOW,
            True,
            UNKNOWN,
        )

    def test_no_close_name_gives_no_suggestion(self) -> None:
        """先頭の語が共通する名前が無ければ、勧めずに使えるツールだけを並べる。"""
        failure = unsupported_tool_failure(
            requested="harvest", valid_tools=["travel_to"], call_id="call_1", now=NOW, action_summary="…"
        )

        assert failure.suggestion is None
        assert failure.observation.body == "未対応のツールです: harvest。 現在使える tool: [travel_to]"
