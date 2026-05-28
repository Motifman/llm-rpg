"""
Speech ツール (channel 引数で whisper/say/shout を切り替え) の実行。

Issue #264 後続: 旧 SAY/WHISPER の 2 tool を廃止し、channel 引数を持つ
単一 ``speech_speak`` tool に統合した (SHOUT も同時に LLM へ公開)。

audience_resolver (Optional) が注入されると、speech 実行直後に
「届いた player 数」を計算し、result_summary に channel ごとの
フィードバックを返す。これにより agent が「speech が届かなかった」事実を
次ターンで学習できる (旧実装は『発言しました。』を omit_result_in_prompt=True
で隠していたため、空振りに気付かなかった)。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.failure_helpers import (
    build_invalid_arg_failure,
    build_sanitized_exception_failure,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    SPEECH_CHANNEL_SAY,
    SPEECH_CHANNEL_SHOUT,
    SPEECH_CHANNEL_VALUES,
    SPEECH_CHANNEL_WHISPER,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    append_inner_thought_to_message,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceResolver,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


_CHANNEL_STRING_TO_ENUM: Dict[str, SpeechChannel] = {
    SPEECH_CHANNEL_WHISPER: SpeechChannel.WHISPER,
    SPEECH_CHANNEL_SAY: SpeechChannel.SAY,
    SPEECH_CHANNEL_SHOUT: SpeechChannel.SHOUT,
}


class SpeechToolExecutor:
    """単一 speech tool (channel: whisper/say/shout) の実行を担当するサブマッパー。

    Issue #264 後続で旧 SAY/WHISPER を統合した。channel ごとに以下のように分岐:
    - whisper: target_label 必須。同 spot 内の特定 1 人にだけ届く
    - say: 同 spot + 隣接 (1 hop) に届く
    - shout: 同 spot + 隣接 + 2 hop 先まで届く (大声)
    """

    def __init__(
        self,
        speech_service: Optional[PlayerSpeechApplicationService] = None,
        *,
        audience_resolver: Optional[SpeechAudienceResolver] = None,
    ) -> None:
        self._speech_service = speech_service
        self._audience_resolver = audience_resolver

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。speech_service が None の場合は空辞書。"""
        if self._speech_service is None:
            return {}
        return {
            TOOL_NAME_SPEECH: self._execute_speech,
        }

    def _execute_speech(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        """speech_speak の実行。channel で whisper/say/shout に分岐する。"""
        if self._speech_service is None:
            return LlmCommandResultDto(
                success=False,
                message="発話ツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )

        # channel 検証
        channel_str = args.get("channel")
        if not isinstance(channel_str, str) or channel_str not in SPEECH_CHANNEL_VALUES:
            return build_invalid_arg_failure(
                arg_name="channel",
                detail=(
                    f"channel は {list(SPEECH_CHANNEL_VALUES)!r} のいずれかを指定してください "
                    f"(現在: {channel_str!r})"
                ),
            )
        channel_enum = _CHANNEL_STRING_TO_ENUM[channel_str]

        # content 検証
        content = args.get("content", "")
        if not isinstance(content, str) or not content.strip():
            return build_invalid_arg_failure(
                arg_name="content",
                detail="非空の文字列で発話内容を指定してください",
            )

        # whisper 限定: target_player_id 必須
        target_player_id: Optional[int] = None
        if channel_enum == SpeechChannel.WHISPER:
            raw_target = args.get("target_player_id")
            if raw_target is None:
                # 古い prompt 経路や label 経由の whisper には target_label が
                # 入ってくる。runtime_manager 側で label→id 解決した結果が
                # target_player_id に入る前提なので、ここでは目に見える誤りのみ catch
                return build_invalid_arg_failure(
                    arg_name="target_player_id",
                    detail=(
                        "channel=whisper のときは囁き先プレイヤーの id (or label) が必須です"
                    ),
                )
            if not isinstance(raw_target, (int, float)):
                return build_invalid_arg_failure(
                    arg_name="target_player_id",
                    detail="囁きの宛先プレイヤー ID (正の整数) を指定してください",
                )
            target_player_id = int(raw_target)

        # 実行
        try:
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content,
                    channel=channel_enum,
                    target_player_id=target_player_id,
                )
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return build_sanitized_exception_failure(
                exc=e,
                log_context=(
                    f"speech failure player_id={player_id} channel={channel_str} "
                    f"target_player_id={target_player_id}"
                ),
                public_message=(
                    "囁きの送信に失敗しました。宛先プレイヤーの存在と状況を確認してください。"
                    if channel_enum == SpeechChannel.WHISPER
                    else "発話に失敗しました。場所や状況を確認してください。"
                ),
                error_code=error_code,
            )

        # 成功時: audience 情報を含む rich result_summary を組み立てる
        message, omit = self._format_result_message(
            speaker_player_id=player_id,
            channel=channel_enum,
            target_player_id=target_player_id,
            args=args,
        )
        return LlmCommandResultDto(
            success=True,
            message=message,
            omit_result_in_prompt=omit,
        )

    def _format_result_message(
        self,
        *,
        speaker_player_id: int,
        channel: SpeechChannel,
        target_player_id: Optional[int],
        args: Dict[str, Any],
    ) -> tuple[str, bool]:
        """channel ごとの result message + omit flag を返す。

        audience_resolver があれば「届いた人数」フィードバックを含む rich message。
        無ければ legacy の固定文 + omit_result_in_prompt=True にフォールバック。
        """
        legacy_base = {
            SpeechChannel.WHISPER: "囁きを送信しました。",
            SpeechChannel.SAY: "発言しました。",
            SpeechChannel.SHOUT: "叫びました。",
        }[channel]

        if self._audience_resolver is None:
            return (
                append_inner_thought_to_message(legacy_base, args),
                True,
            )

        try:
            recipients = self._audience_resolver.resolve_audience(
                speaker_player_id=speaker_player_id,
                channel=channel,
                target_player_id=target_player_id,
            )
        except Exception:
            return (
                append_inner_thought_to_message(legacy_base, args),
                True,
            )

        count = len(recipients)
        if count == 0:
            zero_audience_message = _zero_audience_message(channel)
            return (
                append_inner_thought_to_message(zero_audience_message, args),
                False,  # 重要情報なので prompt 表示する
            )

        # 1 名以上
        if channel == SpeechChannel.WHISPER:
            base = "囁きが届きました。"
        else:
            base = f"{legacy_base[:-1]}。あなたの声は {count} 名のプレイヤーに届く範囲です。"
        return (
            append_inner_thought_to_message(base, args),
            False,
        )


def _zero_audience_message(channel: SpeechChannel) -> str:
    """audience 0 時の channel-aware フィードバック文。

    agent に「現在の channel では届かなかった事実」と「次手の選択肢」を
    具体的に伝えることで、空振りループを抜けやすくする。
    """
    if channel == SpeechChannel.WHISPER:
        return (
            "囁きは同じスポット内の特定 1 人にしか届きませんが、対象が同じスポットに"
            "いません。声は届きませんでした。channel=say や channel=shout に切り替えるか、"
            "対象の居るスポットへ移動してください。"
        )
    if channel == SpeechChannel.SAY:
        return (
            "発言しました。ただし say は同じスポットと隣接スポット (1 hop) のみに届きますが、"
            "その範囲に他のプレイヤーはおらず、声は誰にも届きませんでした。"
            "channel=shout に切り替えると 2 hop 先まで届きます。それでも届かなければ、"
            "別の場所へ移動して相手の居るスポットに近づいてください。"
        )
    # SHOUT
    return (
        "叫びました。ただし shout は 2 hop 範囲まで届きますが、その範囲にも"
        "他のプレイヤーはおらず、声は誰にも届きませんでした。物理的に合流する以外に"
        "伝える手段がありません。別の場所へ移動してください。"
    )
