"""subagent ツールの実行器。bindings を評価し、副 LLM で要約・教訓を取得する。"""

from typing import Callable, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    SubagentEvidenceEntry,
    SubagentResultDto,
)
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

# 制限（計画書 6.6）
MAX_BINDINGS_PER_CALL = 3
MAX_CHARS_PER_BINDING = 2000
MAX_TOTAL_CHARS_FOR_SUBAGENT = 4000

_SUBAGENT_SYSTEM = """あなたは与えられたデータを分析し、要約や教訓を抽出するアシスタントです。
データは JSON またはテキスト形式で渡されます。クエリに従って簡潔に回答してください。
回答は日本語で、3〜5文程度にまとめてください。"""


class SubagentRunner:
    """
    subagent を実行する。bindings を MemoryQueryExecutor で評価し、
    副 LLM に渡して要約を取得する。
    """

    def __init__(
        self,
        memory_query_executor: MemoryQueryExecutor,
        invoke_text: Callable[[str, str], str],
    ) -> None:
        if not isinstance(memory_query_executor, MemoryQueryExecutor):
            raise TypeError(
                "memory_query_executor must be MemoryQueryExecutor"
            )
        if not callable(invoke_text):
            raise TypeError("invoke_text must be callable")
        self._executor = memory_query_executor
        self._invoke_text = invoke_text

    def run(
        self,
        player_id: PlayerId,
        bindings: Dict[str, str],
        query: str,
    ) -> SubagentResultDto:
        """
        bindings を評価し、副 LLM でクエリに回答する。

        Args:
            player_id: プレイヤー ID
            bindings: 名前付き DSL 式。例: {"episodes": "episodic.take(20)"}
            query: 自然言語クエリ

        Returns:
            SubagentResultDto
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(bindings, dict):
            raise TypeError("bindings must be dict")
        if not isinstance(query, str):
            raise TypeError("query must be str")

        if len(bindings) > MAX_BINDINGS_PER_CALL:
            raise ValueError(
                f"bindings count must be <= {MAX_BINDINGS_PER_CALL}, got {len(bindings)}"
            )

        evaluated: Dict[str, str] = {}
        evidence_entries: List[SubagentEvidenceEntry] = []
        truncation_note: Optional[str] = None
        total_chars = 0

        for name, expr in bindings.items():
            if not isinstance(name, str) or not isinstance(expr, str):
                raise TypeError("bindings keys and values must be str")

            result = self._executor.execute(
                player_id, expr.strip(), output_mode="text"
            )
            text = result.get("result") or ""
            if len(text) > MAX_CHARS_PER_BINDING:
                text = text[:MAX_CHARS_PER_BINDING] + "... (truncated)"
                truncation_note = (
                    truncation_note or ""
                ) + f" {name} was truncated. "
            evaluated[name] = text
            total_chars += len(text)

            var_name = self._extract_source_var(expr)
            evidence_entries.append(
                SubagentEvidenceEntry(
                    binding_name=name,
                    source_var=var_name,
                    entry_ids=(),
                )
            )

        if total_chars > MAX_TOTAL_CHARS_FOR_SUBAGENT:
            truncation_note = (
                (truncation_note or "")
                + f" Total exceeded {MAX_TOTAL_CHARS_FOR_SUBAGENT} chars."
            )

        context_parts = [
            f"## {name}\n{text}" for name, text in evaluated.items()
        ]
        context_text = "\n\n".join(context_parts)
        user_content = f"【データ】\n{context_text}\n\n【クエリ】\n{query}"

        answer_summary = self._invoke_text(_SUBAGENT_SYSTEM, user_content)

        return SubagentResultDto(
            answer_summary=answer_summary.strip(),
            evidence=tuple(evidence_entries),
            used_bindings=tuple(evaluated.keys()),
            truncation_note=truncation_note.strip() if truncation_note else None,
        )

    def _extract_source_var(self, expr: str) -> str:
        """式から変数名を抽出。episodic.take(10) -> episodic"""
        expr = expr.strip()
        dot = expr.find(".")
        if dot >= 0:
            return expr[:dot].strip()
        return expr or "?"
