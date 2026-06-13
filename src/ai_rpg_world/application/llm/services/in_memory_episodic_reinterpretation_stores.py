"""想起後再解釈用の in-memory ストア実装。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone

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
    """player ごとに pending recall observations を保持する。"""

    def __init__(self) -> None:
        self._pending: dict[int, list[EpisodicRecallObservation]] = defaultdict(list)

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
        rows = sorted(
            self._pending.get(player_id, ()),
            key=lambda r: (_dt_key(r.recalled_at), r.recall_id),
        )
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

    def mark_processed(self, player_id: int, recall_ids: tuple[str, ...]) -> None:
        if not recall_ids:
            return
        done = set(recall_ids)
        self._pending[player_id] = [
            row for row in self._pending.get(player_id, ()) if row.recall_id not in done
        ]

    def pending_count(self, player_id: int) -> int:
        return len(self._pending.get(player_id, ()))


class InMemoryEpisodicReinterpretationJournalStore(EpisodicReinterpretationJournalRepository):
    """再解釈履歴と active pointer を保持する。"""

    def __init__(self) -> None:
        self._entries: dict[int, list[EpisodicReinterpretationEntry]] = defaultdict(list)
        self._active: dict[int, dict[str, str]] = defaultdict(dict)

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


__all__ = [
    "InMemoryEpisodicRecallBufferStore",
    "InMemoryEpisodicReinterpretationJournalStore",
]
