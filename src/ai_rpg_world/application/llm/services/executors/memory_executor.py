"""
Memory ツール（memory_query, subagent, working_memory_append）の実行。

ToolCommandMapper のサブマッパーとして、Memory 関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.exceptions import (
    DslEvaluationException,
    DslParseException,
    InvalidOutputModeException,
)
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.memory_query_executor import MemoryQueryExecutor
from ai_rpg_world.application.llm.services.subagent_runner import SubagentRunner
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_QUERY,
    TOOL_NAME_SUBAGENT,
    TOOL_NAME_WORKING_MEMORY_APPEND,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class MemoryToolExecutor:
    """
    Memory ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(
        self,
        memory_query_executor: Optional[MemoryQueryExecutor] = None,
        subagent_runner: Optional[SubagentRunner] = None,
        working_memory_store: Optional[Any] = None,
    ) -> None:
        self._memory_query_executor = memory_query_executor
        self._subagent_runner = subagent_runner
        self._working_memory_store = working_memory_store

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。"""
        result: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {}
        if self._memory_query_executor is not None:
            result[TOOL_NAME_MEMORY_QUERY] = self._execute_memory_query
        if self._subagent_runner is not None:
            result[TOOL_NAME_SUBAGENT] = self._execute_subagent
        if self._working_memory_store is not None:
            result[TOOL_NAME_WORKING_MEMORY_APPEND] = self._execute_working_memory_append
        return result

    def _execute_memory_query(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._memory_query_executor is None:
            return unknown_tool("memory_query ツールはまだ利用できません。")
        try:
            expr = args.get("expr", "").strip()
            if not expr:
                return LlmCommandResultDto(
                    success=False,
                    message="expr が指定されていません。",
                    error_code="MEMORY_QUERY_DSL_PARSE_ERROR",
                    remediation=get_remediation("MEMORY_QUERY_DSL_PARSE_ERROR"),
                )
            output_mode = args.get("output_mode") or "text"
            result = self._memory_query_executor.execute(
                PlayerId(player_id), expr, output_mode
            )
            if "handle_id" in result:
                h_id = result.get("handle_id", "")
                count = result.get("count", "0")
                msg = (
                    f"handle_id: {h_id} (件数: {count}). "
                    f"subagent の bindings で handle:{h_id} として使用できます。"
                )
            else:
                msg = result.get("result") or result.get("count") or "（0件）"
            return LlmCommandResultDto(success=True, message=str(msg))
        except (DslParseException, DslEvaluationException, InvalidOutputModeException) as e:
            return exception_result(e)
        except Exception as e:
            return exception_result(e)

    def _execute_subagent(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._subagent_runner is None:
            return unknown_tool("subagent ツールはまだ利用できません。")
        try:
            bindings = args.get("bindings") or {}
            if not isinstance(bindings, dict):
                bindings = {}
            query = args.get("query", "").strip()
            if not query:
                return LlmCommandResultDto(
                    success=False,
                    message="query が指定されていません。",
                    error_code="SUBAGENT_ERROR",
                    remediation="query を指定してください。",
                )
            dto = self._subagent_runner.run(
                PlayerId(player_id), bindings, query
            )
            msg = dto.answer_summary
            if dto.truncation_note:
                msg = msg + "\n（注: " + dto.truncation_note + "）"
            return LlmCommandResultDto(success=True, message=msg)
        except Exception as e:
            return exception_result(e)

    def _execute_working_memory_append(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._working_memory_store is None:
            return unknown_tool("作業メモツールはまだ利用できません。")
        try:
            text = (args.get("text") or "").strip()
            if not text:
                return LlmCommandResultDto(
                    success=False,
                    message="text が指定されていません。",
                    error_code="WORKING_MEMORY_ERROR",
                    remediation="追加するテキストを指定してください。",
                )
            self._working_memory_store.append(PlayerId(player_id), text)
            return LlmCommandResultDto(
                success=True,
                message="作業メモに追加しました。",
            )
        except Exception as e:
            return exception_result(e)
