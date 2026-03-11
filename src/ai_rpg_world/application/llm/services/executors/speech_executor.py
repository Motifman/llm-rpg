"""
Speech ツール（whisper, say）の実行。

ToolCommandMapper のサブマッパーとして、発言・囁き関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_executor_helpers import exception_result
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SAY, TOOL_NAME_WHISPER
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)


class SpeechToolExecutor:
    """
    Speech ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(
        self,
        speech_service: Optional[PlayerSpeechApplicationService] = None,
    ) -> None:
        self._speech_service = speech_service

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。speech_service が None の場合は空辞書。"""
        if self._speech_service is None:
            return {}
        return {
            TOOL_NAME_WHISPER: self._execute_whisper,
            TOOL_NAME_SAY: self._execute_say,
        }

    def _execute_whisper(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._speech_service is None:
            return LlmCommandResultDto(
                success=False,
                message="囁きツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            target_player_id = args.get("target_player_id")
            content = args.get("content", "")
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content if isinstance(content, str) else str(content),
                    channel=args.get("channel"),
                    target_player_id=(
                        int(target_player_id)
                        if isinstance(target_player_id, (int, float))
                        else None
                    ),
                )
            )
            return LlmCommandResultDto(
                success=True,
                message="囁きを送信しました。",
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )

    def _execute_say(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._speech_service is None:
            return LlmCommandResultDto(
                success=False,
                message="発言ツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            content = args.get("content", "")
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content if isinstance(content, str) else str(content),
                    channel=args.get("channel"),
                )
            )
            return LlmCommandResultDto(
                success=True,
                message="発言しました。",
            )
        except Exception as e:
            return exception_result(e)
