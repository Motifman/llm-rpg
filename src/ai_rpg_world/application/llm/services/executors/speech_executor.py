"""
Speech ツール（whisper, say）の実行。

ToolCommandMapper のサブマッパーとして、発言・囁き関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.failure_helpers import (
    build_invalid_arg_failure,
    build_sanitized_exception_failure,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    append_inner_thought_to_message,
)
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
        target_player_id = args.get("target_player_id")
        if not isinstance(target_player_id, (int, float)):
            return build_invalid_arg_failure(
                arg_name="target_player_id",
                detail="囁きの宛先プレイヤー ID (正の整数) を指定してください",
            )
        content = args.get("content", "")
        if not isinstance(content, str) or not content.strip():
            return build_invalid_arg_failure(
                arg_name="content",
                detail="非空の文字列で発話内容を指定してください",
            )
        try:
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content,
                    channel=args.get("channel"),
                    target_player_id=int(target_player_id),
                )
            )
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message("囁きを送信しました。", args),
            )
        except Exception as e:
            # speech_service が ApplicationException を投げた場合は error_code を
            # 引き継ぐが、str(e) を LLM に直渡しすると内部 path / 識別子が漏れうるため
            # サニタイズ ファクトリ経由で固定文 + サーバログに残す (PR #170 と同 pattern)。
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return build_sanitized_exception_failure(
                exc=e,
                log_context=(
                    f"speech_whisper failure player_id={player_id} "
                    f"target_player_id={target_player_id}"
                ),
                public_message="囁きの送信に失敗しました。宛先プレイヤーの存在と状況を確認してください。",
                error_code=error_code,
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
        content = args.get("content", "")
        if not isinstance(content, str) or not content.strip():
            return build_invalid_arg_failure(
                arg_name="content",
                detail="非空の文字列で発話内容を指定してください",
            )
        try:
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content,
                    channel=args.get("channel"),
                )
            )
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message("発言しました。", args),
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return build_sanitized_exception_failure(
                exc=e,
                log_context=f"speech_say failure player_id={player_id}",
                public_message="発言に失敗しました。場所や状況を確認してください。",
                error_code=error_code,
            )
