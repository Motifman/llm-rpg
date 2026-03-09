"""memory_query ツールの実行器。変数解決と DSL 評価を行う。"""

from typing import Callable, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IEpisodeMemoryStore,
    ILongTermMemoryStore,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    IWorkingMemoryStore,
)
from ai_rpg_world.application.llm.exceptions import (
    DslEvaluationException,
    DslParseException,
    InvalidOutputModeException,
)
from ai_rpg_world.application.llm.services.dsl_evaluator import eval_expr
from ai_rpg_world.application.llm.services.memory_variable_serializer import (
    episodes_to_dicts,
    facts_to_dicts,
    laws_to_dicts,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

# 変数解決時のデフォルト取得件数（DSL で take する前の最大）
_DEFAULT_EPISODE_LIMIT = 100
_DEFAULT_FACT_LIMIT = 50
_DEFAULT_LAW_LIMIT = 50
_DEFAULT_RECENT_OBSERVATIONS = 50
_DEFAULT_RECENT_ACTIONS = 50
_DEFAULT_WORKING_MEMORY_LIMIT = 50

_VALID_OUTPUT_MODES = frozenset({"text", "count", "preview"})


class MemoryQueryExecutor:
    """
    memory_query の式を評価し、結果を返す。
    変数: episodic, facts, laws, recent_events, state, working_memory
    """

    def __init__(
        self,
        episode_store: IEpisodeMemoryStore,
        long_term_store: ILongTermMemoryStore,
        sliding_window: ISlidingWindowMemory,
        action_result_store: IActionResultStore,
        working_memory_store: IWorkingMemoryStore,
        state_provider: Callable[[PlayerId], str],
        recent_events_formatter: IRecentEventsFormatter,
    ) -> None:
        if not isinstance(episode_store, IEpisodeMemoryStore):
            raise TypeError("episode_store must be IEpisodeMemoryStore")
        if not isinstance(long_term_store, ILongTermMemoryStore):
            raise TypeError("long_term_store must be ILongTermMemoryStore")
        if not isinstance(sliding_window, ISlidingWindowMemory):
            raise TypeError("sliding_window must be ISlidingWindowMemory")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        if not isinstance(working_memory_store, IWorkingMemoryStore):
            raise TypeError("working_memory_store must be IWorkingMemoryStore")
        if not callable(state_provider):
            raise TypeError("state_provider must be callable")
        if not isinstance(recent_events_formatter, IRecentEventsFormatter):
            raise TypeError(
                "recent_events_formatter must be IRecentEventsFormatter"
            )
        self._episode_store = episode_store
        self._long_term_store = long_term_store
        self._sliding_window = sliding_window
        self._action_result_store = action_result_store
        self._working_memory_store = working_memory_store
        self._state_provider = state_provider
        self._recent_events_formatter = recent_events_formatter

        self._known_vars = frozenset(
            {
                "episodic",
                "facts",
                "laws",
                "recent_events",
                "state",
                "working_memory",
            }
        )

    def execute(
        self,
        player_id: PlayerId,
        expr: str,
        output_mode: str = "text",
    ) -> Dict[str, Optional[str]]:
        """
        式を評価し、output_mode に応じた結果を返す。

        Args:
            player_id: プレイヤー ID
            expr: DSL 式。例: "episodic.take(10)", "facts.take(5)"
            output_mode: "preview" | "count" | "text"

        Returns:
            {"result": "...", "count": "N"} など output_mode に応じたキーを含む dict
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(expr, str):
            raise TypeError("expr must be str")
        if not isinstance(output_mode, str):
            raise TypeError("output_mode must be str")
        expr = expr.strip()
        if not expr:
            raise DslParseException("expr must not be empty", expr=expr)
        if output_mode not in _VALID_OUTPUT_MODES:
            raise InvalidOutputModeException(
                f"output_mode must be one of {', '.join(sorted(_VALID_OUTPUT_MODES))}",
                output_mode=output_mode,
            )

        var_name = self._extract_var_name(expr)

        if var_name not in self._known_vars:
            raise DslParseException(
                f"Unknown variable: {var_name!r}. "
                f"Available: {', '.join(sorted(self._known_vars))}",
                expr=expr,
            )

        if var_name in ("state", "recent_events"):
            result = self._resolve_scalar(player_id, var_name)
            return self._format_output_scalar(result, output_mode)

        data = self._resolve_list_var(player_id, var_name)
        evaluated = eval_expr(expr, data)
        return self._format_output_list(evaluated, output_mode)

    def _extract_var_name(self, expr: str) -> str:
        """式から変数名を抽出する。episodic.take(10) -> episodic"""
        dot = expr.find(".")
        if dot >= 0:
            return expr[:dot].strip()
        return expr.strip()

    def _resolve_scalar(self, player_id: PlayerId, var_name: str) -> str:
        """スカラ変数（state, recent_events）を解決する。"""
        if var_name == "state":
            return self._state_provider(player_id)
        if var_name == "recent_events":
            observations = self._sliding_window.get_recent(
                player_id, _DEFAULT_RECENT_OBSERVATIONS
            )
            action_results = self._action_result_store.get_recent(
                player_id, _DEFAULT_RECENT_ACTIONS
            )
            return self._recent_events_formatter.format(
                observations, action_results
            )
        raise ValueError(f"Unknown scalar var: {var_name}")

    def _resolve_list_var(
        self, player_id: PlayerId, var_name: str
    ) -> List[Dict]:
        """リスト変数を解決し、dict のリストを返す。"""
        if var_name == "episodic":
            entries = self._episode_store.get_recent(
                player_id, _DEFAULT_EPISODE_LIMIT
            )
            return episodes_to_dicts(entries)
        if var_name == "facts":
            entries = self._long_term_store.search_facts(
                player_id, keywords=None, limit=_DEFAULT_FACT_LIMIT
            )
            return facts_to_dicts(entries)
        if var_name == "laws":
            entries = self._long_term_store.find_laws(
                player_id, subject=None, action_name=None, limit=_DEFAULT_LAW_LIMIT
            )
            return laws_to_dicts(entries)
        if var_name == "working_memory":
            texts = self._working_memory_store.get_recent(
                player_id, _DEFAULT_WORKING_MEMORY_LIMIT
            )
            return [{"text": t} for t in texts]
        raise ValueError(f"Unknown list var: {var_name}")

    def _format_output_scalar(
        self, value: str, output_mode: str
    ) -> Dict[str, Optional[str]]:
        """スカラ値の出力をフォーマットする。"""
        if output_mode == "count":
            return {"count": str(len(value)), "result": value[:500]}
        if output_mode == "preview":
            preview = value[:500] + ("..." if len(value) > 500 else "")
            return {"preview": preview, "result": value}
        return {"result": value}

    def _format_output_list(
        self, data: List[Dict], output_mode: str
    ) -> Dict[str, Optional[str]]:
        """リスト値の出力をフォーマットする。"""
        count = len(data)
        if output_mode == "count":
            return {"count": str(count), "result": None}

        lines = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                parts = [f"{k}={v!r}" for k, v in item.items()]
                lines.append(f"  [{i+1}] " + ", ".join(parts))
            else:
                lines.append(f"  [{i+1}] {item!r}")

        text = "\n".join(lines) if lines else "（0件）"

        if output_mode == "preview":
            preview_lines = lines[:5]
            if len(lines) > 5:
                preview_lines.append(f"  ... 他 {len(lines)-5} 件")
            preview = "\n".join(preview_lines)
            return {"preview": preview, "result": text, "count": str(count)}

        return {"result": text, "count": str(count)}
