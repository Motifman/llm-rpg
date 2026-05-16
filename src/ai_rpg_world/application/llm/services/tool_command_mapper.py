"""
ツール名＋引数からコマンドを組み立てて実行し、LlmCommandResultDto を返すマッパー。

handler map の組み立ては wiring 側（_build_tool_handler_map）で行う。
本クラスは tool_name → handler の辞書を受け取り、実行のみを担当する。

intent キュー経路 (opt-in)
--------------------------
``intent_resolution_service`` を constructor で渡された場合、``execute()`` は
直接 handler を呼ばず ``IntentResolutionService.submit_and_resolve_immediately``
に委譲する。queue を経由することで:

- intent_id ベースの ActionFailed 観測 (PR5)
- 将来の post-tick batching 解決 (PR6+)

への seam を確保する。

intent 経路を渡さなければ既存の直接実行パスがそのまま使われるため、後方互換。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ai_rpg_world.application.intent.intent_resolution_service import (
        IntentResolutionService,
    )


class ToolCommandMapper:
    """
    ツール名と引数からコマンドを組み立て、対応するハンドラを呼び出して
    LlmCommandResultDto を返す。失敗時は error_code と remediation を付与する。

    handler_map: tool_name をキー、 (player_id, args) -> LlmCommandResultDto の
    呼び出し可能オブジェクトを値とする辞書。wiring の _build_tool_handler_map で構築する。

    intent_resolution_service: 指定すると intent キュー経由で実行する (opt-in)。
    ``None`` (既定) なら従来通り handler_map を直接呼ぶ。
    """

    def __init__(
        self,
        handler_map: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]],
        intent_resolution_service: Optional["IntentResolutionService"] = None,
    ) -> None:
        if handler_map is None:
            raise TypeError("handler_map must not be None")
        if not isinstance(handler_map, dict):
            raise TypeError("handler_map must be dict")
        self._executor_map: Dict[str, Any] = dict(handler_map)
        self._intent_resolution_service = intent_resolution_service
        # intent 経路を使う場合、本クラスの handler_map は実行されないため
        # silent divergence (mapper 側だけ更新されて intent 経路では
        # UNKNOWN_TOOL になる) の罠を防ぐため警告を出す。
        if intent_resolution_service is not None and handler_map:
            logger.info(
                "ToolCommandMapper: intent_resolution_service is set; "
                "the handler_map passed here will NOT be used. "
                "Provide tools to IntentResolutionService instead."
            )

    def execute(
        self,
        player_id: int,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> LlmCommandResultDto:
        """
        ツールを実行し、結果を LlmCommandResultDto で返す。
        arguments は LLM の function call から渡される辞書（None の場合は {} として扱う）。

        intent_resolution_service が設定されていれば、その経路で実行する。
        """
        if not isinstance(player_id, int):
            raise TypeError("player_id must be int")
        if player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be str")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("arguments must be dict or None")
        args = arguments if arguments is not None else {}

        if self._intent_resolution_service is not None:
            return self._intent_resolution_service.submit_and_resolve_immediately(
                player_id, tool_name, args
            )

        executor = self._executor_map.get(tool_name)
        if executor is not None:
            return executor(player_id, args)
        return LlmCommandResultDto(
            success=False,
            message="未知のツールです。",
            error_code="UNKNOWN_TOOL",
            remediation=get_remediation("UNKNOWN_TOOL"),
        )
