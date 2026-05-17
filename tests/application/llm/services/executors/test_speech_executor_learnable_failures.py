"""Issue #168 PR-4: ``SpeechToolExecutor`` の失敗 DTO を learnable + 例外
サニタイズに統一する。

検証する不変条件:
- 引数 (content / target_player_id) 検証失敗は ``build_invalid_arg_failure``
  経由で arg 名 + 期待値が message に出る
- 内部例外メッセージ (path / 内部 ID 含みうる) は LLM 向け message に漏れない
  (PR #170 の str(exc) サニタイズと同 pattern)
- サーバログには warning レベルで全文脈を残す (観測性)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.speech_executor import (
    SpeechToolExecutor,
)


def _build_executor(*, speech_service=None) -> SpeechToolExecutor:
    return SpeechToolExecutor(speech_service=speech_service or MagicMock())


class TestWhisperInvalidArgs:
    """``_execute_whisper`` の引数検証。"""

    def test_missing_target_player_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_whisper(
            player_id=1, args={"content": "hi"}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "target_player_id" in result.message
        assert result.remediation

    def test_non_numeric_target_player_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_whisper(
            player_id=1, args={"target_player_id": "abc", "content": "hi"}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_empty_content_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_whisper(
            player_id=1, args={"target_player_id": 2, "content": ""}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "content" in result.message

    def test_whitespace_content_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_whisper(
            player_id=1, args={"target_player_id": 2, "content": "   "}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"


class TestSayInvalidArgs:
    def test_missing_content_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_say(player_id=1, args={})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "content" in result.message


class TestExceptionSanitization:
    """speech_service が例外を投げたとき str(e) が LLM に漏れない。"""

    def test_whisper_exception_is_sanitized(self, caplog) -> None:
        sensitive = "/internal/whisper/session/abc: secret_token=xyz"
        speech_service = MagicMock()
        speech_service.speak.side_effect = RuntimeError(sensitive)
        executor = _build_executor(speech_service=speech_service)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.failure_helpers",
        ):
            result = executor._execute_whisper(
                player_id=1,
                args={"target_player_id": 2, "content": "hi"},
            )
        assert result.success is False
        assert "/internal/whisper" not in result.message
        assert "secret_token" not in result.message
        # error_code は exception の getattr 経由 (今回は SYSTEM_ERROR)
        assert result.error_code == "SYSTEM_ERROR"
        assert result.remediation

    def test_say_exception_is_sanitized(self) -> None:
        sensitive = "/var/lib/speech/internal_state: 12345"
        speech_service = MagicMock()
        speech_service.speak.side_effect = RuntimeError(sensitive)
        executor = _build_executor(speech_service=speech_service)
        result = executor._execute_say(
            player_id=1, args={"content": "hello world"}
        )
        assert result.success is False
        assert "/var/lib/speech" not in result.message
        assert "12345" not in result.message
        assert result.error_code == "SYSTEM_ERROR"

    def test_exception_with_error_code_attribute_is_preserved(self) -> None:
        """ApplicationException の error_code はサニタイズ後も保たれる。"""
        class _AppError(Exception):
            error_code = "PLAYER_NOT_FOUND"

        speech_service = MagicMock()
        speech_service.speak.side_effect = _AppError("internal detail")
        executor = _build_executor(speech_service=speech_service)
        result = executor._execute_whisper(
            player_id=1,
            args={"target_player_id": 99, "content": "hi"},
        )
        assert result.success is False
        assert result.error_code == "PLAYER_NOT_FOUND"
        # internal detail は message に漏れない
        assert "internal detail" not in result.message


class TestUnwiredSpeechService:
    """speech_service が None のときは UNKNOWN_TOOL を返す (既存挙動)。"""

    def test_whisper_unwired_returns_unknown_tool(self) -> None:
        executor = SpeechToolExecutor(speech_service=None)
        result = executor._execute_whisper(player_id=1, args={})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_say_unwired_returns_unknown_tool(self) -> None:
        executor = SpeechToolExecutor(speech_service=None)
        result = executor._execute_say(player_id=1, args={"content": "hi"})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
