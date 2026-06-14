"""想起後再解釈用の in-memory ストア実装。

Phase 3 Step 3d-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみを
残した。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone

from ai_rpg_world.application.llm.services._episodic_recall_batch import (
    select_episode_batched,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import EpisodicReinterpretationEntry
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import EpisodicReinterpretationStatus
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import EpisodicRecallBufferRepository
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import EpisodicReinterpretationJournalRepository


def _dt_key(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class InMemoryEpisodicRecallBufferStore(EpisodicRecallBufferRepository):
    """Being ごとに pending recall observations を保持する。"""

    def __init__(self) -> None:
        self._pending: dict[BeingId, list[EpisodicRecallObservation]] = defaultdict(list)

    def append_by_being(
        self, being_id: BeingId, observation: EpisodicRecallObservation
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(observation, EpisodicRecallObservation):
            raise TypeError("observation must be EpisodicRecallObservation")
        self._pending[being_id].append(observation)

    def peek_batch_by_being(
        self,
        being_id: BeingId,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if batch_size <= 0 or max_contexts_per_episode <= 0:
            return ()
        return select_episode_batched(
            list(self._pending.get(being_id, ())),
            batch_size=batch_size,
            max_contexts_per_episode=max_contexts_per_episode,
        )

    def mark_processed_by_being(
        self, being_id: BeingId, recall_ids: tuple[str, ...]
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not recall_ids:
            return
        done = set(recall_ids)
        self._pending[being_id] = [
            row
            for row in self._pending.get(being_id, ())
            if row.recall_id not in done
        ]

    def pending_count_by_being(self, being_id: BeingId) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return len(self._pending.get(being_id, ()))

    def list_pending_by_being(
        self, being_id: BeingId
    ) -> list[EpisodicRecallObservation]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return list(self._pending.get(being_id, ()))

    def replace_all_pending_by_being(
        self,
        being_id: BeingId,
        observations: list[EpisodicRecallObservation],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(observations, list):
            raise TypeError("observations must be list")
        for o in observations:
            if not isinstance(o, EpisodicRecallObservation):
                raise TypeError(
                    "observations elements must be EpisodicRecallObservation"
                )
        self._pending[being_id] = list(observations)


class InMemoryEpisodicReinterpretationJournalStore(EpisodicReinterpretationJournalRepository):
    """Being ごとに再解釈履歴と active pointer を保持する。"""

    def __init__(self) -> None:
        self._entries: dict[BeingId, list[EpisodicReinterpretationEntry]] = defaultdict(list)
        self._active: dict[BeingId, dict[str, str]] = defaultdict(dict)

    def put_active_by_being(
        self, being_id: BeingId, entry: EpisodicReinterpretationEntry
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry, EpisodicReinterpretationEntry):
            raise TypeError("entry must be EpisodicReinterpretationEntry")
        if entry.status != EpisodicReinterpretationStatus.ACTIVE:
            raise ValueError("put_active_by_being requires an active entry")
        old_entry_id = self._active.get(being_id, {}).get(entry.episode_id)
        now = entry.created_at
        if old_entry_id is not None:
            bucket = self._entries.get(being_id, [])
            for idx, old in enumerate(bucket):
                if (
                    old.entry_id == old_entry_id
                    and old.status == EpisodicReinterpretationStatus.ACTIVE
                ):
                    bucket[idx] = replace(
                        old,
                        status=EpisodicReinterpretationStatus.SUPERSEDED,
                        superseded_at=now,
                    )
                    break
        self._entries[being_id].append(entry)
        self._active.setdefault(being_id, {})[entry.episode_id] = entry.entry_id

    def get_active_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        entry_id = self._active.get(being_id, {}).get(episode_id)
        if entry_id is None:
            return None
        for entry in self._entries.get(being_id, ()):
            if (
                entry.entry_id == entry_id
                and entry.status == EpisodicReinterpretationStatus.ACTIVE
            ):
                return entry
        return None

    def list_by_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        rows = [
            entry
            for entry in self._entries.get(being_id, ())
            if entry.episode_id == episode_id
        ]
        return sorted(
            rows,
            key=lambda e: (_dt_key(e.created_at), e.entry_id),
            reverse=True,
        )


    def list_all_by_being(
        self, being_id: BeingId
    ) -> list[EpisodicReinterpretationEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        rows = list(self._entries.get(being_id, ()))
        # created_at 昇順 (= 古い→新しい) で snapshot に並べ替える。snapshot は
        # 「保存順を再現」が目的なので、新しい順の `list_by_episode_by_being`
        # とは並びが違って良い。
        return sorted(rows, key=lambda e: (_dt_key(e.created_at), e.entry_id))

    def replace_all_by_being(
        self,
        being_id: BeingId,
        entries: list[EpisodicReinterpretationEntry],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, EpisodicReinterpretationEntry):
                raise TypeError(
                    "entries elements must be EpisodicReinterpretationEntry"
                )
        self._entries[being_id] = list(entries)
        # active index を episode_id ごとに再構築 (= 最後の ACTIVE entry を採用)。
        active_map: dict[str, str] = {}
        for entry in entries:
            if entry.status == EpisodicReinterpretationStatus.ACTIVE:
                active_map[entry.episode_id] = entry.entry_id
        self._active[being_id] = active_map


__all__ = [
    "InMemoryEpisodicRecallBufferStore",
    "InMemoryEpisodicReinterpretationJournalStore",
]
