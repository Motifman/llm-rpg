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
        except Exception:
            speak(int(player_id.value), arguments)
            raise
        delivery = speak(int(player_id.value), arguments)
        if delivery is SayInlineDelivery.NOTHING_TO_SAY:
            return result
        payload = dict(result.trace_payload or {})
        payload["say_inline_spoken"] = delivery is SayInlineDelivery.SPOKEN
        if delivery is SayInlineDelivery.NOT_DELIVERED:
            return replace(
                result, message=result.message + NOT_DELIVERED_NOTE, trace_payload=payload,
            )
        return replace(result, trace_payload=payload)

    _handler.delivers_say_inline = True  # type: ignore[attr-defined]
    _handler.__wrapped__ = handler  # type: ignore[attr-defined]
    return _handler
