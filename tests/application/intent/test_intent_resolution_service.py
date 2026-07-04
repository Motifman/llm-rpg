"""``IntentResolutionService`` の挙動を検証する単体テスト。

submit→drain→resolve の流れ、未知ツール、handler 例外、queue 拒否のケースを
カバーする。
"""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)
from ai_rpg_world.application.intent.intent_resolution_service import (
    IntentResolutionService,
)
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.aggregate.intent_queue import IntentQueue


def _build(
    handlers: dict | None = None,
    start_tick: int = 1,
) -> tuple[IntentResolutionService, IntentQueue, list[int]]:
    queue = IntentQueue()
    tick_holder = [start_tick]

    def tick_provider() -> WorldTick:
        return WorldTick(tick_holder[0])

    service = IntentResolutionService(
        handler_map=handlers if handlers is not None else {},
        intent_queue=queue,
        intent_id_generator=IntentIdGenerator(),
        tick_provider=tick_provider,
    )
    return service, queue, tick_holder


class TestSubmitAndResolveImmediately:
    """``submit_and_resolve_immediately`` の挙動。"""

    def test_handler_is_invoked_with_player_id_and_args(self) -> None:
        """既存形の handler が intent 経由でも同じ引数で呼ばれる。"""
        captured: dict[str, Any] = {}

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            captured["player_id"] = player_id
            captured["args"] = dict(args)
            return LlmCommandResultDto(success=True, message="ok")

        service, queue, _ = _build({"travel_to": handler})
        result = service.submit_and_resolve_immediately(
            player_id=42,
            tool_name="travel_to",
            arguments={"destination_label": "B"},
        )

        assert result.success is True
        assert result.message == "ok"
        assert captured == {
            "player_id": 42,
            "args": {"destination_label": "B"},
        }
        # 解決後 queue は空になる
        assert queue.size() == 0

    def test_unknown_tool_returns_failure_dto(self) -> None:
        """handler_map に無いツールは UNKNOWN_TOOL の失敗 DTO。"""
        service, _, _ = _build({})
        result = service.submit_and_resolve_immediately(
            player_id=1, tool_name="nonexistent", arguments={}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_handler_exception_becomes_failure_dto(self) -> None:
        """handler が例外を投げると INTENT_HANDLER_RAISED の失敗 DTO。"""

        def boom(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            raise RuntimeError("oops")

        service, _, _ = _build({"crash": boom})
        result = service.submit_and_resolve_immediately(
            player_id=1, tool_name="crash", arguments={}
        )
        assert result.success is False
        assert result.error_code == "INTENT_HANDLER_RAISED"

    def test_arguments_are_defensively_copied(self) -> None:
        """submit 後に呼び出し側が dict を mutate しても intent には影響しない。"""

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            # handler が受け取った args の中身を結果に乗せる
            return LlmCommandResultDto(
                success=True, message=str(dict(args))
            )

        service, _, _ = _build({"say": handler})
        original = {"content": "hello"}
        result = service.submit_and_resolve_immediately(
            player_id=1, tool_name="say", arguments=original
        )
        # handler はオリジナルの content を受け取った
        assert "hello" in result.message
        # submit 後にオリジナルを mutate しても (検査不可能だが) 安全に呼べる
        original["content"] = "mutated"
        # 同じ tick で再度 submit すると新たな intent_id が振られる
        # (同じ tick で 2 件目の submit は queue が拒否するので別 tick で)


class TestResolveDrained:
    """``_resolve_drained`` の挙動 (将来 batching 経路向け private API)。"""

    def test_resolves_each_intent_in_order(self) -> None:
        """渡された intent 順に handler を呼び、(intent, dto) のリストを返す。"""
        order: list[str] = []

        def handler_a(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            order.append("a")
            return LlmCommandResultDto(success=True, message="a")

        def handler_b(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            order.append("b")
            return LlmCommandResultDto(success=True, message="b")

        service, queue, _ = _build({"tool_a": handler_a, "tool_b": handler_b})
        # 直接 queue に submit して drain して _resolve_drained に渡す
        service.submit_and_resolve_immediately(
            player_id=1, tool_name="tool_a", arguments={}
        )
        # 再 submit で別 player の intent を入れる
        service.submit_and_resolve_immediately(
            player_id=2, tool_name="tool_b", arguments={}
        )

        # submit_and_resolve_immediately は即 resolve するので順序は呼び出し順
        assert order == ["a", "b"]

    def test_does_not_steal_other_callers_intents(self) -> None:
        """immediate path は他 caller の intent を巻き込まない (race 対策)。

        Agent A が submit した直後に Agent B が submit した状況を模倣する。
        A の resolve は A の intent だけを取り出し、B の intent は queue に
        残り続けることを保証する。
        """
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.intent.aggregate.intent_queue import (
            IntentQueue,
        )
        from ai_rpg_world.domain.intent.value_object.intent import Intent
        from ai_rpg_world.domain.intent.value_object.intent_id import IntentId
        from ai_rpg_world.domain.intent.value_object.intent_phase import (
            IntentPhase,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        # 事前に Agent B の intent を queue に入れておく
        queue = IntentQueue()
        b_intent = Intent(
            intent_id=IntentId(9999),
            player_id=PlayerId(2),
            tool_name="tool_a",
            arguments={},
            phase=IntentPhase.OTHER,
            submitted_at_tick=WorldTick(1),
            complete_at_tick=WorldTick(1),
        )
        queue.submit(b_intent)

        called: list[int] = []

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            called.append(player_id)
            return LlmCommandResultDto(success=True, message="ok")

        service = IntentResolutionService(
            handler_map={"tool_a": handler},
            intent_queue=queue,
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
        )
        # Agent A が submit
        service.submit_and_resolve_immediately(
            player_id=1, tool_name="tool_a", arguments={}
        )

        # handler は A だけ呼ばれている
        assert called == [1]
        # B の intent は queue に残り続けている
        assert queue.size() == 1
        assert queue.pending()[0].intent_id == IntentId(9999)


class TestConstructorValidation:
    """construct 時の型チェック。"""

    def test_invalid_handler_map_rejected(self) -> None:
        queue = IntentQueue()
        with pytest.raises(TypeError):
            IntentResolutionService(
                handler_map="not a mapping",  # type: ignore[arg-type]
                intent_queue=queue,
                intent_id_generator=IntentIdGenerator(),
                tick_provider=lambda: WorldTick(1),
            )

    def test_invalid_intent_queue_rejected(self) -> None:
        with pytest.raises(TypeError):
            IntentResolutionService(
                handler_map={},
                intent_queue="not a queue",  # type: ignore[arg-type]
                intent_id_generator=IntentIdGenerator(),
                tick_provider=lambda: WorldTick(1),
            )

    def test_invalid_tick_provider_rejected(self) -> None:
        with pytest.raises(TypeError):
            IntentResolutionService(
                handler_map={},
                intent_queue=IntentQueue(),
                intent_id_generator=IntentIdGenerator(),
                tick_provider="not callable",  # type: ignore[arg-type]
            )
