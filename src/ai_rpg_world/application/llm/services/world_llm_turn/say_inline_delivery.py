"""行動に添えた発言 (``say_inline``) を、行動の結果にかかわらず出す包み (#1601)。

発言を各 handler の成功の経路に置くと、断られた行動の発言が届かない。前提条件、
名前の解決、疲労のどれで断られても、口にしたことは聞こえる範囲に届く。dispatch で
handler が返った後に 1 か所で出す。設計判断は ``docs/design_decisions.md`` の D1601。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SayInlineDelivery,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ToolHandler = Callable[[PlayerId, dict[str, Any], Any], LlmCommandResultDto]
SayInlineSpeaker = Callable[[int, dict[str, Any]], SayInlineDelivery]

NOT_DELIVERED_NOTE = "（添えた発言は届かなかった）"


def wrap_with_say_inline(handler: ToolHandler, speak: SayInlineSpeaker) -> ToolHandler:
    """handler が返った後に ``say_inline`` を出し、出せなかったら結果文に書き足す。"""

    def _handler(
        player_id: PlayerId, arguments: dict[str, Any], runtime_context: Any,
    ) -> LlmCommandResultDto:
        try:
            result = handler(player_id, arguments, runtime_context)
        except Exception as exc:
            # 例外から失敗の結果を作るのは phase_b なので、届いたかを例外に載せて渡す。
            exc.say_inline_delivery = speak(int(player_id.value), arguments)  # type: ignore[attr-defined]
            raise
        return with_say_inline_delivery(result, speak(int(player_id.value), arguments))

    _handler.delivers_say_inline = True  # type: ignore[attr-defined]
    _handler.__wrapped__ = handler  # type: ignore[attr-defined]
    return _handler


def with_say_inline_delivery(
    result: LlmCommandResultDto, delivery: SayInlineDelivery,
) -> LlmCommandResultDto:
    """発言を出した結果を、本人の結果文と trace に書き足す。"""
    if delivery is SayInlineDelivery.NOTHING_TO_SAY:
        return result
    payload = dict(result.trace_payload or {})
    payload["say_inline_spoken"] = delivery is SayInlineDelivery.SPOKEN
    if delivery is SayInlineDelivery.NOT_DELIVERED:
        return replace(
            result, message=result.message + NOT_DELIVERED_NOTE, trace_payload=payload,
        )
    return replace(result, trace_payload=payload)


def with_delivery_carried_by(
    result: LlmCommandResultDto, exc: BaseException,
) -> LlmCommandResultDto:
    """handler の例外に載った発言の結果を、例外から作った失敗の結果に書き足す。"""
    delivery = getattr(exc, "say_inline_delivery", None)
    if not isinstance(delivery, SayInlineDelivery):
        return result
    return with_say_inline_delivery(result, delivery)


def with_unspoken_say_inline(
    result: LlmCommandResultDto, arguments: dict[str, Any],
) -> LlmCommandResultDto:
    """handler まで届かずに断られた行動の ``say_inline`` は出さず、出さなかったと書き足す。"""
    raw = arguments.get("say_inline")
    if not isinstance(raw, str) or not raw.strip():
        return result
    return with_say_inline_delivery(result, SayInlineDelivery.NOT_DELIVERED)
