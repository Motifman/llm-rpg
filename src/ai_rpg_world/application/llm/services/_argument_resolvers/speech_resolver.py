"""発言ツールの引数を、送信先と発言範囲へ解決する。"""
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.services._resolver_helpers import ToolArgumentResolutionException, require_target_type
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    SPEECH_CHANNEL_SAY,
    SPEECH_CHANNEL_SHOUT,
    SPEECH_CHANNEL_VALUES,
    SPEECH_CHANNEL_WHISPER,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


class SpeechArgumentResolver:
    """発言内容・範囲・囁き先の検証と解決を行う。"""

    def resolve_args(
        self,
        tool_name: str,
        args: dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> dict[str, Any] | None:
        if tool_name == TOOL_NAME_SPEECH:
            return self._resolve_speech(args, runtime_context)
        return None

    def _resolve_speech(
        self,
        args: dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> dict[str, Any]:
        """発言の範囲を検証し、囁き先ラベルをプレイヤーIDへ解決する。"""
        from ai_rpg_world.application.llm.contracts.dtos import PlayerToolRuntimeTargetDto

        channel_str = args.get("channel")
        if not isinstance(channel_str, str) or channel_str not in SPEECH_CHANNEL_VALUES:
            raise ToolArgumentResolutionException(
                f"channel は {list(SPEECH_CHANNEL_VALUES)!r} のいずれかを指定してください "
                f"(現在: {channel_str!r})",
                "INVALID_SPEECH_CHANNEL",
            )
        channel_map = {
            SPEECH_CHANNEL_WHISPER: SpeechChannel.WHISPER,
            SPEECH_CHANNEL_SAY: SpeechChannel.SAY,
            SPEECH_CHANNEL_SHOUT: SpeechChannel.SHOUT,
        }
        channel_enum = channel_map[channel_str]

        raw_it = args.get("inner_thought", "")
        inner = (
            raw_it.strip()
            if isinstance(raw_it, str)
            else (str(raw_it) if raw_it is not None else "")
        )

        result: dict[str, Any] = {
            "content": args.get("content", ""),
            "channel": channel_enum,
            "inner_thought": inner,
        }

        if channel_enum == SpeechChannel.WHISPER:
            label = args.get("target_label")
            if not isinstance(label, str) or not label:
                raise ToolArgumentResolutionException(
                    "channel=whisper のときは target_label が必須です。",
                    "INVALID_TARGET_LABEL",
                )
            target = require_target_type(
                label,
                runtime_context,
                "囁き先ラベル",
                (PlayerToolRuntimeTargetDto,),
            )
            if target.player_id is None:
                raise ToolArgumentResolutionException(
                    f"囁きはプレイヤー宛てにのみ送れます: {label}",
                    "INVALID_TARGET_KIND",
                )
            result["target_player_id"] = target.player_id

        return result
