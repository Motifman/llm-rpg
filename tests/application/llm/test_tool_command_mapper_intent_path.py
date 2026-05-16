"""``ToolCommandMapper`` の intent キュー経路 (opt-in) を検証する統合テスト。

``intent_resolution_service`` を渡したマッパーは:
- handler を直接呼ばず service 経由で実行する
- 結果 DTO は service が返したものをそのまま返す
- intent_resolution_service=None なら従来の直接実行パスがそのまま動く (後方互換)
"""

from __future__ import annotations

from typing import Any, Mapping

from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)
from ai_rpg_world.application.intent.intent_resolution_service import (
    IntentResolutionService,
)
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_command_mapper import (
    ToolCommandMapper,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.aggregate.intent_queue import IntentQueue


def _handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
    return LlmCommandResultDto(
        success=True, message=f"called with {dict(args)}"
    )


class TestToolCommandMapperIntentPath:
    """opt-in 経路の挙動。"""

    def test_default_path_calls_handler_directly(self) -> None:
        """intent_resolution_service=None なら従来通り handler を直接呼ぶ。"""
        mapper = ToolCommandMapper({"travel": _handler})
        result = mapper.execute(1, "travel", {"to": "B"})
        assert result.success is True
        assert "to" in result.message

    def test_intent_path_routes_through_resolution_service(self) -> None:
        """intent_resolution_service を渡すと queue 経由で実行される。"""
        handlers = {"travel": _handler}
        queue = IntentQueue()
        service = IntentResolutionService(
            handler_map=handlers,
            intent_queue=queue,
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(7),
        )
        mapper = ToolCommandMapper(
            handler_map=handlers,
            intent_resolution_service=service,
        )

        result = mapper.execute(2, "travel", {"to": "C"})
        assert result.success is True
        # service が同じ handler を呼んでいることを確認
        assert "to" in result.message
        # queue は空 (即 drain 済み)
        assert queue.size() == 0

    def test_intent_path_unknown_tool_returns_failure_dto(self) -> None:
        """intent 経路でも UNKNOWN_TOOL は失敗 DTO で返る。"""
        handlers: dict = {}
        queue = IntentQueue()
        service = IntentResolutionService(
            handler_map=handlers,
            intent_queue=queue,
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
        )
        mapper = ToolCommandMapper(
            handler_map=handlers,
            intent_resolution_service=service,
        )
        result = mapper.execute(1, "ghost_tool", {})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
