"""想起後再解釈用の in-memory ストア実装。

Phase 3 Step 3d-1 (Issue #470): being_id 版 API を並走追加。
内部に 2 つの独立した index を持つ:
- ``_pending`` / ``_entries`` / ``_active``: player_id 版 (= 旧 API、Step 3d-3 で撤去予定)
- ``_pending_by_being`` / ``_entries_by_being`` / ``_active_by_being``: being_id 版
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone

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


def _select_batch(
    rows: list[EpisodicRecallObservation],
    *,
    batch_size: int,
    max_contexts_per_episode: int,
) -> tuple[EpisodicRecallObservation, ...]:
    """recalled_at + recall_id でソート済 rows から episode-batched 結果を組む。"""
    rows = sorted(rows, key=lambda r: (_dt_key(r.recalled_at), r.recall_id))
    selected_episode_ids: list[str] = []
    counts: dict[str, int] = defaultdict(int)
    out: list[EpisodicRecallObservation] = []
    for row in rows:
        if row.episode_id not in counts:
            if len(selected_episode_ids) >= batch_size:
                continue
            selected_episode_ids.append(row.episode_id)
        if counts[row.episode_id] >= max_contexts_per_episode:
            continue
        counts[row.episode_id] += 1
        out.append(row)
    return tuple(out)


class InMemoryEpisodicRecallBufferStore(EpisodicRecallBufferRepository):
    """player ごとに pending recall observations を保持する。"""

    def __init__(self) -> None:
        self._pending: dict[int, list[EpisodicRecallObservation]] = defaultdict(list)
        # Phase 3 Step 3d-1: being_id 版並走 index
        self._pending_by_being: dict[BeingId, list[EpisodicRecallObservation]] = defaultdict(list)

    def append(self, observation: EpisodicRecallObservation) -> None:
        if not isinstance(observation, EpisodicRecallObservation):
            raise TypeError("observation must be EpisodicRecallObservation")
        self._pending[observation.player_id].append(observation)

    def peek_batch(
        self,
        player_id: int,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        if batch_size <= 0 or max_contexts_per_episode <= 0:
            return ()
        return _select_batch(
            list(self._pending.get(player_id, ())),
            batch_size=batch_size,
            max_contexts_per_episode=max_contexts_per_episode,
        )

    def mark_processed(self, player_id: int, recall_ids: tuple[str, ...]) -> None:
        if not recall_ids:
            return
        done = set(recall_ids)
        self._pending[player_id] = [
            row for row in self._pending.get(player_id, ()) if row.recall_id not in done
        ]

    def pending_count(self, player_id: int) -> int:
        return len(self._pending.get(player_id, ()))

    # ===== Phase 3 Step 3d-1: being_id 版を並走追加 =====

    def append_by_being(
        self, being_id: BeingId, observation: EpisodicRecallObservation
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(observation, EpisodicRecallObservation):
            raise TypeError("observation must be EpisodicRecallObservation")
        self._pending_by_being[being_id].append(observation)

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
        return _select_batch(
            list(self._pending_by_being.get(being_id, ())),
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
        self._pending_by_being[being_id] = [
            row
            for row in self._pending_by_being.get(being_id, ())
            if row.recall_id not in done
        ]

    def pending_count_by_being(self, being_id: BeingId) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return len(self._pending_by_being.get(being_id, ()))


class InMemoryEpisodicReinterpretationJournalStore(EpisodicReinterpretationJournalRepository):
    """再解釈履歴と active pointer を保持する。"""

    def __init__(self) -> None:
        self._entries: dict[int, list[EpisodicReinterpretationEntry]] = defaultdict(list)
        self._active: dict[int, dict[str, str]] = defaultdict(dict)
        # Phase 3 Step 3d-1: being_id 版並走 index
        self._entries_by_being: dict[BeingId, list[EpisodicReinterpretationEntry]] = defaultdict(list)
        self._active_by_being: dict[BeingId, dict[str, str]] = defaultdict(dict)

    def put_active(self, entry: EpisodicReinterpretationEntry) -> None:
        if not isinstance(entry, EpisodicReinterpretationEntry):
            raise TypeError("entry must be EpisodicReinterpretationEntry")
        if entry.status != EpisodicReinterpretationStatus.ACTIVE:
            raise ValueError("put_active requires an active entry")
        pid = entry.player_id
        old_entry_id = self._active.get(pid, {}).get(entry.episode_id)
        now = entry.created_at
        if old_entry_id is not None:
            bucket = self._entries.get(pid, [])
            for idx, old in enumerate(bucket):
                if old.entry_id == old_entry_id and old.status == EpisodicReinterpretationStatus.ACTIVE:
                    bucket[idx] = replace(
                        old,
                        status=EpisodicReinterpretationStatus.SUPERSEDED,
                        superseded_at=now,
                    )
                    break
        self._entries[pid].append(entry)
        self._active.setdefault(pid, {})[entry.episode_id] = entry.entry_id

    def get_active(
        self,
        player_id: int,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        entry_id = self._active.get(player_id, {}).get(episode_id)
        if entry_id is None:
            return None
        for entry in self._entries.get(player_id, ()):
            if entry.entry_id == entry_id and entry.status == EpisodicReinterpretationStatus.ACTIVE:
                return entry
        return None

    def list_by_episode(
        self,
        player_id: int,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        rows = [
            entry
            for entry in self._entries.get(player_id, ())
            if entry.episode_id == episode_id
        ]
        return sorted(rows, key=lambda e: (_dt_key(e.created_at), e.entry_id), reverse=True)

    # ===== Phase 3 Step 3d-1: being_id 版を並走追加 =====

    def put_active_by_being(
        self, being_id: BeingId, entry: EpisodicReinterpretationEntry
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry, EpisodicReinterpretationEntry):
            raise TypeError("entry must be EpisodicReinterpretationEntry")
        if entry.status != EpisodicReinterpretationStatus.ACTIVE:
            raise ValueError("put_active_by_being requires an active entry")
        old_entry_id = self._active_by_being.get(being_id, {}).get(entry.episode_id)
        now = entry.created_at
        if old_entry_id is not None:
            bucket = self._entries_by_being.get(being_id, [])
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
        self._entries_by_being[being_id].append(entry)
        self._active_by_being.setdefault(being_id, {})[entry.episode_id] = entry.entry_id

    def get_active_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        entry_id = self._active_by_being.get(being_id, {}).get(episode_id)
        if entry_id is None:
            return None
        for entry in self._entries_by_being.get(being_id, ()):
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
            for entry in self._entries_by_being.get(being_id, ())
            if entry.episode_id == episode_id
        ]
        return sorted(
            rows,
            key=lambda e: (_dt_key(e.created_at), e.entry_id),
            reverse=True,
        )


__all__ = [
    "InMemoryEpisodicRecallBufferStore",
    "InMemoryEpisodicReinterpretationJournalStore",
]
