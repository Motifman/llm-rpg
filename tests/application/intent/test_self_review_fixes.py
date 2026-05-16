"""PR #151 セルフレビュー指摘に対する修正の回帰テスト。

カバー対象:
- HIGH-SEC: ``_resolve_one`` の例外メッセージサニタイズ (exc 内容を LLM へ
  漏らさない)
- MED: ``submit_and_resolve_immediately`` の空 tool_name 早期検出
- MED: ``queue.remove`` 失敗時の hard raise (orphan 防止)
"""

from __future__ import annotations

import logging
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


class TestExceptionSanitization:
    """``_resolve_one`` の例外メッセージサニタイズ挙動。"""

    def test_handler_exception_message_is_not_leaked_to_dto(self, caplog) -> None:
        """raw 例外メッセージ (パス・secrets を含みうる) は DTO に出ない。"""

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            raise RuntimeError(
                "/home/user/project/secret_path: API_KEY=sk-xxxxxxxx leaked"
            )

        service = IntentResolutionService(
            handler_map={"crash": handler},
            intent_queue=IntentQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
        )

        with caplog.at_level(
            logging.ERROR,
            logger="ai_rpg_world.application.intent.intent_resolution_service",
        ):
            result = service.submit_and_resolve_immediately(
                player_id=1, tool_name="crash", arguments={}
            )

        assert result.success is False
        assert result.error_code == "INTENT_HANDLER_RAISED"
        # 例外文字列が DTO の message に混入していないこと
        assert "/home/user/project/secret_path" not in result.message
        assert "API_KEY" not in result.message
        assert "sk-xxxxxxxx" not in result.message
        # サーバログには残っていること (観測可能性は維持)
        assert any(
            "Intent handler raised" in record.message for record in caplog.records
        )

    def test_submission_rejection_does_not_leak_exception_message(self) -> None:
        """submit 失敗時にも例外文字列を返さない。"""
        # queue を pre-populate して同一 (player, tick) の duplicate を起こす
        queue = IntentQueue()
        from ai_rpg_world.domain.intent.value_object.intent import Intent
        from ai_rpg_world.domain.intent.value_object.intent_id import IntentId
        from ai_rpg_world.domain.intent.value_object.intent_phase import (
            IntentPhase,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        queue.submit(
            Intent(
                intent_id=IntentId(1),
                player_id=PlayerId(7),
                tool_name="noop",
                arguments={},
                phase=IntentPhase.OTHER,
                submitted_at_tick=WorldTick(5),
                complete_at_tick=WorldTick(5),
            )
        )

        service = IntentResolutionService(
            handler_map={"noop": lambda p, a: LlmCommandResultDto(success=True, message="ok")},
            intent_queue=queue,
            intent_id_generator=IntentIdGenerator(start=100),
            tick_provider=lambda: WorldTick(5),
        )

        result = service.submit_and_resolve_immediately(
            player_id=7, tool_name="noop", arguments={}
        )
        assert result.success is False
        assert result.error_code == "INTENT_SUBMISSION_REJECTED"
        # 例外オブジェクトの repr 等が漏れていないこと
        assert "DuplicateIntentForPlayerException" not in result.message


class TestEmptyToolNameRejection:
    """空 tool_name の早期検出。"""

    def test_empty_string_returns_no_tool_call(self) -> None:
        """空文字 tool_name は NO_TOOL_CALL で即返る (intent VO 化前)。"""
        service = IntentResolutionService(
            handler_map={},
            intent_queue=IntentQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
        )
        result = service.submit_and_resolve_immediately(
            player_id=1, tool_name="", arguments={}
        )
        assert result.success is False
        assert result.error_code == "NO_TOOL_CALL"

    def test_non_str_tool_name_returns_no_tool_call(self) -> None:
        """str 以外も同じく早期に NO_TOOL_CALL を返す。"""
        service = IntentResolutionService(
            handler_map={},
            intent_queue=IntentQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
        )
        result = service.submit_and_resolve_immediately(
            player_id=1, tool_name=None, arguments={}  # type: ignore[arg-type]
        )
        assert result.success is False
        assert result.error_code == "NO_TOOL_CALL"


class TestQueueRemoveFailureBehavior:
    """`queue.remove` 失敗時に hard raise する挙動 (orphan 防止)。"""

    def test_remove_failure_raises_instead_of_returning_dto(self) -> None:
        """submit 直後に queue が壊れていた場合 (シミュレート) は raise する。

        DTO で吸収すると submit した intent が queue 内に orphan として残り、
        次の drain で別 tick に紛れ込む状態破壊を招くため。
        """

        class _SabotagedQueue(IntentQueue):
            """submit はするが remove は常に失敗する queue。"""

            def remove(self, intent_id):  # type: ignore[override]
                from ai_rpg_world.domain.intent.exception.intent_exception import (
                    UnknownIntentException,
                )

                raise UnknownIntentException(
                    "sabotaged", intent_id=intent_id.value
                )

        service = IntentResolutionService(
            handler_map={"noop": lambda p, a: LlmCommandResultDto(success=True, message="ok")},
            intent_queue=_SabotagedQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
        )

        from ai_rpg_world.domain.intent.exception.intent_exception import (
            UnknownIntentException,
        )

        with pytest.raises(UnknownIntentException):
            service.submit_and_resolve_immediately(
                player_id=1, tool_name="noop", arguments={}
            )
