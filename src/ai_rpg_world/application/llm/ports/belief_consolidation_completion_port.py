"""固着パス (belief journal への統合) 用の無ツール JSON 完了ポート (U3b)。

``BeliefConsolidationCoordinator`` が evidence batch + shortlist を渡し、
belief journal への decisions (create / strengthen / revise / contradict /
discard) を JSON で受け取るための LLM 完了。返却 JSON のスキーマは
semantic_learning_consolidation_design.md 「固着パス」節の decisions と
同一:

::

    {
      "decisions": [
        {"action": "create", "text": str, "importance": int, "tags": [str]},
        {"action": "strengthen", "belief_id": str, "evidence_ids": [str]},
        {"action": "revise", "belief_id": str, "text": str, "reason": str},
        {"action": "contradict", "belief_id": str, "evidence_ids": [str]},
        {"action": "discard", "evidence_ids": [str], "reason": str}
      ]
    }

詳細は docs/memory_system/semantic_learning_consolidation_design.md
「固着パス: BeliefConsolidationCoordinator」節。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IBeliefConsolidationCompletionPort(ABC):
    """evidence batch + shortlist → decisions (JSON object) の無ツール完了。"""

    @abstractmethod
    def complete_belief_consolidation_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """messages を LLM へ送り、応答文字列を JSON にパースして dict で返す。

        Raises:
            LlmApiCallException: API 失敗・空応答・JSON パース不能時。
                呼び出し元 (``BeliefConsolidationCoordinator``) は evidence を
                buffer に残したまま次周期に再試行する (決定論 fallback で
                belief を作らない、という設計の共通方針)。
        """
        raise NotImplementedError


__all__ = ["IBeliefConsolidationCompletionPort"]
