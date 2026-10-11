"""``wrap_with_say_inline`` が、行動の結果を問わず発言を 1 回出し、出せなかったら本人に伝えることを保証する (#1601)。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SayInlineDelivery,
)
from ai_rpg_world.application.llm.services.world_llm_turn.say_inline_delivery import (
    NOT_DELIVERED_NOTE,
    with_delivery_carried_by,
    wrap_with_say_inline,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_ARGS = {"say_inline": "鍵を差せ"}


class _Speaker:
    def __init__(self, delivery: SayInlineDelivery) -> None:
        self.delivery = delivery
        self.calls: list[tuple[int, dict[str, Any]]] = []

    def __call__(self, player_id: int, args: dict[str, Any]) -> SayInlineDelivery:
        self.calls.append((player_id, args))
        return self.delivery


def _returning(result: LlmCommandResultDto):
    return lambda player_id, arguments, runtime_context: result


_REFUSED = LlmCommandResultDto(
    success=False,
    message="行動が拒否された: 鍵穴に合う鍵を持っていない。",
    error_code="INTERACTION_PRECONDITION_FAILED",
    trace_payload={"precondition_failure_kind": "missing_prerequisite"},
)


class TestWrapWithSayInline:
    """発言を出す包みが、handler の結果に応じて結果文と trace を書き足す規則を保証する。"""

    def test_refused_action_still_speaks_once(self) -> None:
        """handler が失敗を返しても、発言を 1 回出し、結果文はそのまま返す。"""
        speaker = _Speaker(SayInlineDelivery.SPOKEN)

        result = wrap_with_say_inline(_returning(_REFUSED), speaker)(PlayerId(3), _ARGS, None)

        assert speaker.calls == [(3, _ARGS)]
        assert result.message == _REFUSED.message
        assert result.success is False

    def test_spoken_words_are_recorded_in_the_trace_payload(self) -> None:
        """発言を出せたとき、trace_payload に say_inline_spoken=True を足し、既存の項目を残す。"""
        result = wrap_with_say_inline(
            _returning(_REFUSED), _Speaker(SayInlineDelivery.SPOKEN)
        )(PlayerId(3), _ARGS, None)

        assert result.trace_payload == {
            "precondition_failure_kind": "missing_prerequisite",
            "say_inline_spoken": True,
        }

    def test_undelivered_words_are_reported_to_the_actor(self) -> None:
        """発言を出せなかったとき、結果文の末尾に届かなかったことを足し、trace に say_inline_spoken=False を残す。"""
        result = wrap_with_say_inline(
            _returning(_REFUSED), _Speaker(SayInlineDelivery.NOT_DELIVERED)
        )(PlayerId(3), _ARGS, None)

        assert result.message == _REFUSED.message + NOT_DELIVERED_NOTE
        assert result.trace_payload is not None
        assert result.trace_payload["say_inline_spoken"] is False

    def test_nothing_to_say_leaves_the_result_untouched(self) -> None:
        """say_inline が無いときは、結果をそのまま返す。"""
        result = wrap_with_say_inline(
            _returning(_REFUSED), _Speaker(SayInlineDelivery.NOTHING_TO_SAY)
        )(PlayerId(3), {}, None)

        assert result is _REFUSED

    def test_raising_handler_still_speaks_and_reraises(self) -> None:
        """handler が例外を投げても発言を 1 回出し、例外はそのまま外へ出す。"""
        speaker = _Speaker(SayInlineDelivery.SPOKEN)

        def _raising(player_id, arguments, runtime_context):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            wrap_with_say_inline(_raising, speaker)(PlayerId(3), _ARGS, None)

        assert speaker.calls == [(3, _ARGS)]

    def test_raising_handler_carries_the_delivery_on_the_exception(self) -> None:
        """handler が例外を投げ、発話も断られると、例外に NOT_DELIVERED を載せ、例外から作った結果に注記が付く。"""

        def _raising(player_id, arguments, runtime_context):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError) as caught:
            wrap_with_say_inline(_raising, _Speaker(SayInlineDelivery.NOT_DELIVERED))(
                PlayerId(3), _ARGS, None
            )
        result = with_delivery_carried_by(_REFUSED, caught.value)

        assert result.message == _REFUSED.message + NOT_DELIVERED_NOTE

    def test_exception_without_a_delivery_leaves_the_result_untouched(self) -> None:
        """発言の結果を載せていない例外からは、結果に何も足さない。"""
        result = with_delivery_carried_by(_REFUSED, RuntimeError("boom"))

        assert result is _REFUSED
