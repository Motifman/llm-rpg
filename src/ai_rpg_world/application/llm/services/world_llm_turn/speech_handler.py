"""Speech tool handler と auxiliary tool handler。"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    resolve_player_target,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.failure_helpers import list_player_labels
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    SPEECH_CHANNEL_SAY,
    SPEECH_CHANNEL_SHOUT,
    SPEECH_CHANNEL_VALUES,
    SPEECH_CHANNEL_WHISPER,
)
from ai_rpg_world.application.speech.services.audience_feedback import (
    compact_audience_summary_text,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

def handle_speech(
    wiring,
    player_id: PlayerId,
    arguments: dict[str, Any],
    runtime_context: Any,
) -> LlmCommandResultDto:
    """Issue #264 後続: 単一 speech_speak tool の dispatch。

    ``channel`` 引数 (whisper/say/shout) で挙動を分岐する。
    - whisper: ``target_label`` 必須 (同 spot 内の特定プレイヤー)
    - say: 同 spot + 隣接 (1 hop)
    - shout: 同 spot + 隣接 + 2 hop
    """
    channel_str = str(arguments.get("channel", "")).lower()
    if channel_str not in SPEECH_CHANNEL_VALUES:
        return LlmCommandResultDto(
            success=False,
            message=(
                f"channel が不正です: {channel_str!r}。"
                f"{list(SPEECH_CHANNEL_VALUES)!r} のいずれかを指定してください。"
            ),
            error_code="INVALID_SPEECH_CHANNEL",
        )
    content = str(arguments.get("content", "")).strip()
    if not content:
        return LlmCommandResultDto(
            success=False,
            message="発話内容 (content) が空です。",
            error_code="INVALID_SPEECH_CONTENT",
        )

    channel_map = {
        SPEECH_CHANNEL_WHISPER: SpeechChannel.WHISPER,
        SPEECH_CHANNEL_SAY: SpeechChannel.SAY,
        SPEECH_CHANNEL_SHOUT: SpeechChannel.SHOUT,
    }
    channel_enum = channel_map[channel_str]

    target_player_id_obj: Optional[PlayerId] = None
    if channel_enum == SpeechChannel.WHISPER:
        targets = getattr(runtime_context, "targets", {})
        target_label = str(arguments.get("target_label", ""))
        target = resolve_whisper_target(wiring, target_label, targets)
        if target is None or target.player_id is None:
            valid_players = list_player_labels(targets)
            detail = (
                f"target_label={target_label!r} が見つかりません。"
                f"有効な target_label: {valid_players or '(同 spot に他プレイヤーなし)'}"
            )
            return LlmCommandResultDto(
                success=False,
                message=f"囁きを送れませんでした: {detail}",
                error_code="INVALID_WHISPER",
                remediation=(
                    "channel=whisper のときは target_label に同じスポット内の "
                    "相手の名前を指定してください。"
                ),
            )
        target_player_id_obj = PlayerId(target.player_id)
        outcome_registry = getattr(wiring.runtime, "_player_outcome_registry", None)
        if outcome_registry is not None:
            if outcome_registry.get_outcome(
                target_player_id_obj
            ).is_eliminated:
                target_name = getattr(target, "display_name", "") or "相手"
                return LlmCommandResultDto(
                    success=False,
                    message=(
                        f"囁きを送れませんでした: {target_name}は死亡しており、"
                        "囁きは届きません。"
                    ),
                    error_code="INVALID_WHISPER",
                    remediation=(
                        "channel=whisper は生存している同じスポット内の相手にだけ"
                        "届きます。別の相手を選ぶか、say / shout を使ってください。"
                    ),
                )

    wiring.runtime.do_speech(player_id, content, channel_enum, target_player_id_obj)

    audience_suffix = build_audience_summary(
        wiring, player_id, channel_enum, target_player_id_obj
    )
    return LlmCommandResultDto(
        success=True,
        message=audience_suffix or "（発話した）",
    )

def resolve_whisper_target(
    wiring,
    target_label: str,
    targets: dict[str, Any],
) -> Optional[Any]:
    """本家 resolver の ``resolve_player_target`` を呼び、解決できなければ

    None を返す。

    ``resolve_player_target`` は失敗を例外で返すようになったが、whisper は
    ``INVALID_WHISPER`` + 有効な target_label 一覧 + 対処法という **専用の
    失敗文面** を持っており、そちらの方が LLM にとって有益である。そこで
    ここで例外を捕まえて None に変換し、呼び出し側 (`_handle_speech`) が
    専用文面を組み立てる。

    None への変換をこの 1 箇所に閉じ込めるのが要点で、「暗黙に None が
    返る」のではなく「ここで明示的に変換している」ことをコード上で見える
    ようにしている。``_handle_speech`` は resolver 例外を
    ``LlmCommandResultDto`` に変換するアダプタを通さず生で登録されている
    ため、例外をそのまま投げると広い except に落ちて
    ``LLM_TOOL_EXECUTION_FAILED`` + スタックトレースに劣化する。
    """
    # 既存呼び出しは targets 単体を渡してくるので、runtime_context を
    # 偽装する単純な namespace で fallback の resolver API に合わせる。
    rtc = type("_RTCStub", (), {"targets": targets})()
    try:
        return resolve_player_target(target_label, rtc)  # type: ignore[arg-type]
    except ToolArgumentResolutionException:
        return None

def build_audience_summary(
    wiring,
    player_id: PlayerId,
    channel: Any,
    target_player_id: Optional[PlayerId],
) -> str:
    """speech 発火直後の audience 情報を message に追記する suffix を返す。

    Issue #264 B1: agent に「あなたの声が届いた範囲」を明示することで、
    返事の有無を待たずに次手を考えられるようにする。
    channel ごとに 0 audience 時の次手提案も含める。
    """
    if wiring.speech_audience_resolver is None:
        return ""
    try:
        members = wiring.speech_audience_resolver.resolve_audience_with_clarity(
            speaker_player_id=int(player_id.value),
            channel=channel,
            target_player_id=(
                int(target_player_id.value)
                if target_player_id is not None
                else None
            ),
        )
    except Exception:
        logger.exception("speech_audience_resolver.resolve_audience_with_clarity failed")
        return ""
    return f"（{compact_audience_summary_text(channel, members)}）"
