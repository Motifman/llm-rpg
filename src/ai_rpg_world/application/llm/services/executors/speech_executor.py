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
from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceResolver,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


class SpeechToolExecutor:
    """
    Speech ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。

    Issue #264 後続: speech_audience_resolver (Optional) が注入されると、
    speech 実行直後に「届いた player 数」を計算し、result_summary に
    フィードバックする。これにより agent が「speech が届かなかった」
    事実を次ターンで学習できる (旧実装は『発言しました。』を omit_result_in_prompt=True
    で隠していたため、空振りに気付かなかった)。
    """

    def __init__(
        self,
        speech_service: Optional[PlayerSpeechApplicationService] = None,
        *,
        audience_resolver: Optional[SpeechAudienceResolver] = None,
    ) -> None:
        self._speech_service = speech_service
        self._audience_resolver = audience_resolver

    def _format_say_result_message(
        self,
        speaker_player_id: int,
        channel: SpeechChannel,
        args: Dict[str, Any],
    ) -> tuple[str, bool]:
        """speech 結果 message と prompt 表示要否を返す。

        audience_resolver があれば「届いた人数」を含む rich message を作る。
        無ければ legacy の '発言しました。' に omit_result_in_prompt=True で
        フォールバック (旧挙動互換)。

        Returns:
            (message, omit_result_in_prompt)
        """
        if self._audience_resolver is None:
            return (
                append_inner_thought_to_message("発言しました。", args),
                True,
            )
        try:
            recipients = self._audience_resolver.resolve_audience(
                speaker_player_id=speaker_player_id,
                channel=channel,
            )
        except Exception:
            # resolver 失敗時は legacy fallback (speech 自体は止めない)
            return (
                append_inner_thought_to_message("発言しました。", args),
                True,
            )
        count = len(recipients)
        if count == 0:
            base = (
                "発言しました。ただし周囲に他のプレイヤーは聞こえる範囲におらず、"
                "あなたの声は誰にも届きませんでした。返事を期待せず、別の手段 "
                "(別の場所へ移動する / 接続先で再度 say する / whisper を使う) を検討してください。"
            )
        else:
            base = f"発言しました。あなたの声は {count} 名のプレイヤーに届く範囲です。"
        return (
            append_inner_thought_to_message(base, args),
            False,  # 重要情報なので prompt 表示する
        )

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
                # Issue #188: 発話内容は ``action_summary`` の引数部分に
                # 一人称で含まれており、result_summary 「囁きを送信しました。」
                # は情報量ゼロのノイズ。prompt 表示から省略する。
                omit_result_in_prompt=True,
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
        channel_arg = args.get("channel")
        try:
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content,
                    channel=channel_arg,
                )
            )
            # Issue #264 後続: audience_resolver があれば「届いた人数」を
            # result_summary に含める。これにより「speech が空振りした」事実が
            # agent に届き、別の手段 (移動 / whisper) に切り替える判断材料になる。
            channel_enum = (
                channel_arg
                if isinstance(channel_arg, SpeechChannel)
                else SpeechChannel.SAY
            )
            message, omit = self._format_say_result_message(
                speaker_player_id=player_id,
                channel=channel_enum,
                args=args,
            )
            return LlmCommandResultDto(
                success=True,
                message=message,
                omit_result_in_prompt=omit,
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return build_sanitized_exception_failure(
                exc=e,
                log_context=f"speech_say failure player_id={player_id}",
                public_message="発言に失敗しました。場所や状況を確認してください。",
                error_code=error_code,
            )
