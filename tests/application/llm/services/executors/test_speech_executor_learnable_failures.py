"""Issue #168 PR-4 + Issue #264: 統合された ``SpeechToolExecutor._execute_speech`` の
失敗 DTO を learnable + 例外サニタイズに統一する。

旧 SAY/WHISPER は単一 speech_speak (channel 引数) に統合された (Issue #264 後続)。
チェック内容は不変条件として維持:
- 引数 (channel / content / target_label) 検証失敗は build_invalid_arg_failure
  経由で arg 名 + 期待値が message に出る
- 内部例外メッセージ (path / 内部 ID 含みうる) は LLM 向け message に漏れない
- サーバログには warning レベルで全文脈を残す
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.speech_executor import (
    SpeechToolExecutor,
)


def _build_executor(*, speech_service=None) -> SpeechToolExecutor:
    return SpeechToolExecutor(speech_service=speech_service or MagicMock())


class TestSpeechInvalidArgs:
    """``_execute_speech`` の引数検証。"""

    def test_missing_channel_is_learnable(self) -> None:
        """channel 未指定なら INVALID_ARGUMENT で arg 名 channel が message に出る。"""
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"content": "hi"}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "channel" in result.message

    def test_invalid_channel_is_learnable(self) -> None:
        """channel が enum 外なら INVALID_ARGUMENT で許容値が message に出る。"""
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"channel": "yell", "content": "hi"}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "channel" in result.message

    def test_whisper_missing_target_player_id_is_learnable(self) -> None:
        """channel=whisper で target_player_id 欠落なら INVALID_ARGUMENT。"""
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"channel": "whisper", "content": "hi"}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "target_player_id" in result.message

    def test_whisper_non_numeric_target_player_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1,
            args={"channel": "whisper", "target_player_id": "abc", "content": "hi"},
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_empty_content_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"channel": "say", "content": ""}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "content" in result.message

    def test_whitespace_content_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"channel": "say", "content": "   "}
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"


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
            result = executor._execute_speech(
                player_id=1,
                args={"channel": "whisper", "target_player_id": 2, "content": "hi"},
            )
        assert result.success is False
        assert "/internal/whisper" not in result.message
        assert "secret_token" not in result.message
        assert result.error_code == "SYSTEM_ERROR"
        assert result.remediation

    def test_say_exception_is_sanitized(self) -> None:
        sensitive = "/var/lib/speech/internal_state: 12345"
        speech_service = MagicMock()
        speech_service.speak.side_effect = RuntimeError(sensitive)
        executor = _build_executor(speech_service=speech_service)
        result = executor._execute_speech(
            player_id=1, args={"channel": "say", "content": "hello world"}
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
        result = executor._execute_speech(
            player_id=1,
            args={"channel": "whisper", "target_player_id": 99, "content": "hi"},
        )
        assert result.success is False
        assert result.error_code == "PLAYER_NOT_FOUND"
        assert "internal detail" not in result.message


class TestSpeechOmitResultInPrompt:
    """audience_resolver が無い場合の旧挙動: 成功時は omit_result_in_prompt=True。

    audience_resolver があると rich message を出すため omit=False になる
    (これは別のテストで担保)。
    """

    def test_say_success_sets_omit_result_flag(self) -> None:
        """audience_resolver 未注入の SAY 成功は omit=True (旧挙動互換)。"""
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"channel": "say", "content": "Hello"}
        )
        assert result.success is True
        assert result.omit_result_in_prompt is True

    def test_whisper_success_sets_omit_result_flag(self) -> None:
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1,
            args={"channel": "whisper", "target_player_id": 2, "content": "Hi"},
        )
        assert result.success is True
        assert result.omit_result_in_prompt is True

    def test_shout_success_sets_omit_result_flag(self) -> None:
        """SHOUT も同様 (Issue #264 後続で初公開)。"""
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"channel": "shout", "content": "聞こえるか！"}
        )
        assert result.success is True
        assert result.omit_result_in_prompt is True

    def test_failure_does_not_set_omit_result_flag(self) -> None:
        """失敗時は省略しない (LLM が remediation を見て修正できるように)。"""
        executor = _build_executor()
        result = executor._execute_speech(
            player_id=1, args={"channel": "say"}
        )  # content 欠落
        assert result.success is False
        assert result.omit_result_in_prompt is False


class TestUnwiredSpeechService:
    """speech_service が None のときは UNKNOWN_TOOL を返す (既存挙動)。"""

    def test_speech_unwired_returns_unknown_tool(self) -> None:
        executor = SpeechToolExecutor(speech_service=None)
        result = executor._execute_speech(player_id=1, args={"channel": "say"})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
