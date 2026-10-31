"""Being の短期記憶のいきさつを書く LLM の呼び出しのインタフェース (#1824)。

名前は、今の短期記憶の要約を書いていたころのまま。費用の記録 (``aux_llm_call``) の component も
``short_term_summary`` のままにして、前の run と比べられるようにしている。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IShortTermMemorySummaryCompletionPort(ABC):
    """いきさつを書くための、道具を使わない JSON の完了。"""

    @abstractmethod
    def complete_short_term_summary_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """messages を LLM へ送り、応答文字列を JSON にパースして dict で返す。

        Raises:
            LlmApiCallException: API 失敗 / 空応答 / JSON パース不能時。
                呼び出し元 (``LlmBackstoryWriter``) はそのまま投げ、いきさつを書く非同期の処理の失敗になる。
        """
        raise NotImplementedError


__all__ = [
    "IShortTermMemorySummaryCompletionPort",
]
