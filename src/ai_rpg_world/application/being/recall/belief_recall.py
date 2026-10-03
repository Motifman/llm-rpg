"""状況の欄を選んだマスクごとに信念を引き、結果を混ぜずに持つ (#1414)。

## 点は 1 段目の手法の点だけ

作った時刻による新しさと重要度は入れない。どのマスクにも一致しない信念が、新しさと
重要度だけで頭に載る経路を作らない。2 段目の並べ直しは確かめ方の結果で決める。

## 枠は一覧から順番に 1 件ずつ取る

一覧どうしの点は問い合わせ文が違うので比べられない。点で混ぜて並べ直すと、長い
問い合わせ文の一覧が枠を取り切る。重複は先の一覧に残し、後の一覧から除いてから件数を切る。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.being.recall.situation import (
    FieldSelection,
    RecallMask,
    Situation,
)
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
class MaskBeliefs:
    """1 つのマスクで引けた信念。``duplicates`` は先の一覧にあったので外した信念で、``hits`` に入らない。"""

    mask: RecallMask
    query: str
    hits: tuple[RankedCandidate, ...]
    entries: tuple[SemanticMemoryEntry, ...]
    duplicates: tuple[str, ...]

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "fields": self.mask.to_trace_payload(),
            "query": self.query,
            "hits": [
                {"entry_id": hit.key, "score": round(hit.score, 4), "text": hit.text}
                for hit in self.hits
            ],
            "duplicates": list(self.duplicates),
        }


@dataclass(frozen=True)
class SituationBeliefRecallResult:
    selection: FieldSelection
    narrower: str
    lists: tuple[MaskBeliefs, ...]
    chosen: tuple[SemanticMemoryEntry, ...]
    candidate_count: int

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            **self.selection.to_trace_payload(),
            "narrower": self.narrower,
            "candidate_count": self.candidate_count,
            "masks": [beliefs.to_trace_payload() for beliefs in self.lists],
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
        self,
        being_id: BeingId,
        situation: Situation,
        selection: FieldSelection,
        *,
        top_k: int,
    ) -> SituationBeliefRecallResult:
        """各マスクで、先の一覧と重ならない信念を最大 ``top_k`` 件ずつ引き、頭に載せる ``top_k`` 件を選ぶ。

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
        candidates = [TextCandidate(key, entry.text) for key, entry in active.items()]
        seen: set[str] = set()
        lists: list[MaskBeliefs] = []
        for mask in selection.masks():
            query = mask.query(situation)
            lists.append(self._narrow(mask, query, candidates, active, seen, top_k))
        return SituationBeliefRecallResult(
            selection=selection,
            narrower=self._narrower.name,
            lists=tuple(lists),
            chosen=_take_in_turn(lists, top_k),
            candidate_count=len(candidates),
        )

    def _narrow(
        self,
        mask: RecallMask,
        query: str,
        candidates: list[TextCandidate],
        active: dict[str, SemanticMemoryEntry],
        seen: set[str],
        top_k: int,
    ) -> MaskBeliefs:
        # 先の一覧と重なった分を余分に引いてから切る。重なったまま切ると、場所の文しか
        # 違わない 2 本目の一覧が空になり、別の場所での似た経験が取れない。
        if not query:
            return MaskBeliefs(mask, query, (), (), ())
        ranked = self._narrower.narrow(query, candidates, top_k=top_k + len(seen))
        hits: list[RankedCandidate] = []
        duplicates: list[str] = []
        entries: list[SemanticMemoryEntry] = []
        for hit in ranked:
            if len(entries) >= top_k:
                break
            if hit.key not in active:
                raise ValueError(
                    f"narrower {self._narrower.name} returned unknown key {hit.key!r}"
                )
            if hit.key in seen:
                duplicates.append(hit.key)
                continue
            hits.append(hit)
            entries.append(active[hit.key])
        seen.update(entry.entry_id for entry in entries)
        return MaskBeliefs(mask, query, tuple(hits), tuple(entries), tuple(duplicates))


def _take_in_turn(
    lists: list[MaskBeliefs], top_k: int
) -> tuple[SemanticMemoryEntry, ...]:
    chosen: list[SemanticMemoryEntry] = []
    depth = max((len(beliefs.entries) for beliefs in lists), default=0)
    for rank in range(depth):
        for beliefs in lists:
            if rank < len(beliefs.entries) and len(chosen) < top_k:
                chosen.append(beliefs.entries[rank])
    return tuple(chosen)


__all__ = [
    "MaskBeliefs",
    "SituationBeliefRecall",
    "SituationBeliefRecallResult",
]
