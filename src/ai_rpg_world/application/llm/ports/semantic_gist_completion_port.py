"""セマンティック gist 生成用の無ツール JSON 完了ポート (Phase 1b)。

エピソードクラスタから「学び・教訓・関係性の理解」を 1 つ抽象化するための
LLM 完了。返却 JSON のスキーマは ``SemanticGistResult`` に対応する:

::

    {
      "gist_text": str,            # 50 字以内の命題
      "importance_score": int,     # 1-10
      "tags": list[str]            # 検索用 (例: ["タカシ", "信頼"])
    }

詳細は docs/memory_system/semantic_memory_activation_plan.md §3。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ISemanticGistCompletionPort(ABC):
    """エピソードクラスタ → 抽象 gist (JSON object) の無ツール完了。"""

    @abstractmethod
    def complete_semantic_gist_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """messages を LLM へ送り、応答文字列を JSON にパースして dict で返す。

        Raises:
            LlmApiCallException: API 失敗・空応答・JSON パース不能時。
                呼び出し元 (``SemanticGistService``) は決定論 gist にフォールバック。
        """
        raise NotImplementedError


__all__ = ["ISemanticGistCompletionPort"]
