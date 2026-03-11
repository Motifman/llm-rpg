"""
TODO ツール（todo_add, todo_list, todo_complete）の実行。

ToolCommandMapper のサブマッパーとして、Todo 関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TodoToolExecutor:
    """
    TODO ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(self, todo_store: Optional[Any] = None) -> None:
        self._todo_store = todo_store

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。todo_store が None の場合は空辞書。"""
        if self._todo_store is None:
            return {}
        return {
            TOOL_NAME_TODO_ADD: self._execute_todo_add,
            TOOL_NAME_TODO_LIST: self._execute_todo_list,
            TOOL_NAME_TODO_COMPLETE: self._execute_todo_complete,
        }

    def _execute_todo_add(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._todo_store is None:
            return unknown_tool("TODO ツールはまだ利用できません。")
        try:
            content = (args.get("content") or "").strip()
            if not content:
                return LlmCommandResultDto(
                    success=False,
                    message="content が指定されていません。",
                    error_code="TODO_ERROR",
                    remediation=get_remediation("TODO_ERROR"),
                )
            todo_id = self._todo_store.add(PlayerId(player_id), content)
            return LlmCommandResultDto(
                success=True,
                message=f"TODO を追加しました（ID: {todo_id}）。",
            )
        except Exception as e:
            return exception_result(e)

    def _execute_todo_list(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        del args  # unused
        if self._todo_store is None:
            return unknown_tool("TODO ツールはまだ利用できません。")
        try:
            entries = self._todo_store.list_uncompleted(PlayerId(player_id))
            if not entries:
                return LlmCommandResultDto(
                    success=True,
                    message="未完了の TODO はありません。",
                )
            lines = [
                f"- [{e.id}] {e.content} (追加: {e.added_at.strftime('%Y-%m-%d %H:%M')})"
                for e in entries
            ]
            return LlmCommandResultDto(
                success=True,
                message="未完了の TODO:\n" + "\n".join(lines),
            )
        except Exception as e:
            return exception_result(e)

    def _execute_todo_complete(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._todo_store is None:
            return unknown_tool("TODO ツールはまだ利用できません。")
        try:
            todo_id = (args.get("todo_id") or "").strip()
            if not todo_id:
                return LlmCommandResultDto(
                    success=False,
                    message="todo_id が指定されていません。",
                    error_code="TODO_ERROR",
                    remediation=get_remediation("TODO_ERROR"),
                )
            ok = self._todo_store.complete(PlayerId(player_id), todo_id)
            if ok:
                return LlmCommandResultDto(
                    success=True,
                    message=f"TODO {todo_id} を完了にしました。",
                )
            return LlmCommandResultDto(
                success=False,
                message=f"TODO {todo_id} が見つかりません。",
                error_code="TODO_ERROR",
                remediation="正しい todo_id を指定してください。todo_list で一覧を確認できます。",
            )
        except Exception as e:
            return exception_result(e)
