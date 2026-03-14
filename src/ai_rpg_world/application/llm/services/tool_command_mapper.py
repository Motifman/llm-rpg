"""
ツール名＋引数からコマンドを組み立てて実行し、LlmCommandResultDto を返すマッパー。

handler map の組み立ては wiring 側（_build_tool_handler_map）で行う。
本クラスは tool_name → handler の辞書を受け取り、実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation


class ToolCommandMapper:
    """
    ツール名と引数からコマンドを組み立て、対応するハンドラを呼び出して
    LlmCommandResultDto を返す。失敗時は error_code と remediation を付与する。

    handler_map: tool_name をキー、 (player_id, args) -> LlmCommandResultDto の
    呼び出し可能オブジェクトを値とする辞書。wiring の _build_tool_handler_map で構築する。
    """

    def __init__(
        self,
        handler_map: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]],
    ) -> None:
        if handler_map is None:
            raise TypeError("handler_map must not be None")
        if not isinstance(handler_map, dict):
            raise TypeError("handler_map must be dict")
        self._executor_map: Dict[str, Any] = dict(handler_map)

    def execute(
        self,
        player_id: int,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> LlmCommandResultDto:
        """
        ツールを実行し、結果を LlmCommandResultDto で返す。
        arguments は LLM の function call から渡される辞書（None の場合は {} として扱う）。
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

        executor = self._executor_map.get(tool_name)
        if executor is not None:
            return executor(player_id, args)
        return LlmCommandResultDto(
            success=False,
            message="未知のツールです。",
            error_code="UNKNOWN_TOOL",
            remediation=get_remediation("UNKNOWN_TOOL"),
        )
