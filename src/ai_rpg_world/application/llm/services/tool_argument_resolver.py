"""LLM の UI 向けラベル引数を canonical args に解決する。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.contracts.interfaces import IToolArgumentResolver
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


class ToolArgumentResolutionException(Exception):
    """UI ラベル引数を解決できないときの例外。"""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


class DefaultToolArgumentResolver(IToolArgumentResolver):
    """ツール名ごとに UI ラベルを既存アプリケーション層の引数へ解決する。"""

    def resolve(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be str")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("arguments must be dict or None")
        if not isinstance(runtime_context, ToolRuntimeContextDto):
            raise TypeError("runtime_context must be ToolRuntimeContextDto")

        args = arguments or {}

        if tool_name == TOOL_NAME_NO_OP:
            return {}
        if tool_name == TOOL_NAME_MOVE_TO_DESTINATION:
            return self._resolve_move_to_destination(args, runtime_context)
        if tool_name == TOOL_NAME_WHISPER:
            return self._resolve_whisper(args, runtime_context)
        return dict(args)

    def _resolve_move_to_destination(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("destination_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "移動先ラベルが指定されていません。",
                "INVALID_DESTINATION_LABEL",
            )
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された移動先ラベルは現在の候補にありません: {label}",
                "INVALID_DESTINATION_LABEL",
            )
        if target.kind != "destination" or target.spot_id is None:
            raise ToolArgumentResolutionException(
                f"移動先として使えないラベルです: {label}",
                "INVALID_DESTINATION_KIND",
            )
        return {
            "destination_type": target.destination_type or "spot",
            "target_spot_id": target.spot_id,
            "target_location_area_id": target.location_area_id,
        }

    def _resolve_whisper(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "囁き先ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された対象ラベルは現在の候補にありません: {label}",
                "INVALID_TARGET_LABEL",
            )
        if target.kind != "player" or target.player_id is None:
            raise ToolArgumentResolutionException(
                f"囁きはプレイヤー宛てにのみ送れます: {label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "content": args.get("content", ""),
            "channel": SpeechChannel.WHISPER,
            "target_player_id": target.player_id,
        }
