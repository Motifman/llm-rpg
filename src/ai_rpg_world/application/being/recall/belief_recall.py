"""いまの状況の全部の項目をつなげて 1 本で問い合わせ、信念の上位を引く (#1414)。

点は検索の手法の点だけにする。作った時刻による新しさと重要度は入れない。状況に
一致しない信念が、新しさと重要度だけで頭に載る経路を作らない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.being.recall.situation import Situation
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    ITextCandidateNarrower,
    RankedCandidate,
    TextCandidate,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    SemanticMemoryRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SEMANTIC_MEMORY_STATUS_ACTIVE,
    SemanticMemoryEntry,
)


@dataclass(frozen=True)
class SituationBeliefRecallResult:
    narrower: str
    query: str
    hits: tuple[RankedCandidate, ...]
    chosen: tuple[SemanticMemoryEntry, ...]
    candidate_count: int

    def to_trace_payload(self) -> dict[str, Any]:
        """候補の数があれば、何も載らなかったときに信念が無かったのか一致しなかったのかを分けられる。"""
        return {
            "narrower": self.narrower,
            "query": self.query,
            "candidate_count": self.candidate_count,
            "hits": [
                {"entry_id": hit.key, "score": round(hit.score, 4), "text": hit.text}
                for hit in self.hits
            ],
            "chosen": [entry.entry_id for entry in self.chosen],
        }


class SituationBeliefRecall:
    def __init__(
        self, store: SemanticMemoryRepository, narrower: ITextCandidateNarrower
    ) -> None:
        if not isinstance(store, SemanticMemoryRepository):
            raise TypeError("store must be SemanticMemoryRepository")
        if not isinstance(narrower, ITextCandidateNarrower):
            raise TypeError("narrower must be ITextCandidateNarrower")
        self._store = store
        self._narrower = narrower

    def retrieve(
        self, being_id: BeingId, situation: Situation, *, top_k: int
    ) -> SituationBeliefRecallResult:
        """有効な信念から、状況の問い合わせ文に近い順に最大 ``top_k`` 件を返す。

        Raises:
            ValueError: ``top_k`` が 1 未満か、手法が候補に無い信念を返した
        """
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        active = {
            entry.entry_id: entry
            for entry in self._store.list_for_being(being_id)
            if entry.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        }
        query = situation.query()
        candidates = [TextCandidate(key, entry.text) for key, entry in active.items()]
        # 値の無い状況は手法に渡さない。埋め込みの手法は空の文にも何かを返しうる。
        hits = self._narrower.narrow(query, candidates, top_k=top_k) if query else ()
        unknown = [hit.key for hit in hits if hit.key not in active]
        if unknown:
            raise ValueError(
                f"narrower {self._narrower.name} returned unknown keys {unknown!r}"
            )
        return SituationBeliefRecallResult(
            narrower=self._narrower.name,
            query=query,
            hits=tuple(hits),
            chosen=tuple(active[hit.key] for hit in hits),
            candidate_count=len(candidates),
        )


__all__ = ["SituationBeliefRecall", "SituationBeliefRecallResult"]
