"""想起後再解釈用の in-memory ストア実装。

Phase 3 Step 3d-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみを
残した。

横断レビュー H-3/M2 で ``InMemoryEpisodicRecallBufferStore`` のみ thread-safe
化: ThreadPool の chunk 補完ワーカー (``episodic_subjective_completion_schedulers.py``)
が ``stamp_prediction_outcome_by_being`` (list → replace の read-modify-write)
/ ``list_episode_ids_by_prediction_context_by_being`` を叩く一方、メイン
thread は ``prompt_builder`` / ``episodic_reinterpretation_coordinator`` から
append / peek / mark_processed を行う。#309 と同じ ``threading.RLock``
パターンで公開メソッド全体を保護する。

``InMemoryEpisodicReinterpretationJournalStore`` はこのワーカー thread から
呼ばれる経路が無い (呼び出し元は ``episodic_reinterpretation_coordinator`` /
``belief_consolidation_coordinator`` 経由でメイン thread のみ) ため、今回は
lock 化の対象外とする。
"""

from __future__ import annotations

import threading
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
        # ワーカー thread (stamp_prediction_outcome_by_being 等) とメイン
        # thread (append / peek / mark_processed) が同じ dict / list を触るため、
        # 公開メソッド全体を 1 つの RLock で保護する (#309 と同じ粒度・同じ理由)。
        self._lock = threading.RLock()

    def append_by_being(
        self, being_id: BeingId, observation: EpisodicRecallObservation
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(observation, EpisodicRecallObservation):
            raise TypeError("observation must be EpisodicRecallObservation")
        with self._lock:
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
        with self._lock:
            snapshot = list(self._pending.get(being_id, ()))
        return select_episode_batched(
            snapshot,
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
        with self._lock:
            self._pending[being_id] = [
                row
                for row in self._pending.get(being_id, ())
                if row.recall_id not in done
            ]

    def pending_count_by_being(self, being_id: BeingId) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
            return len(self._pending.get(being_id, ()))

    def list_pending_by_being(
        self, being_id: BeingId
    ) -> list[EpisodicRecallObservation]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
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
        with self._lock:
            self._pending[being_id] = list(observations)

    def stamp_prediction_outcome_by_being(
        self,
        being_id: BeingId,
        prediction_context_id: str,
        prediction_error: str,
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(prediction_context_id, str) or not prediction_context_id.strip():
            raise ValueError("prediction_context_id must be a non-empty str")
        if not isinstance(prediction_error, str) or not prediction_error.strip():
            raise ValueError("prediction_error must be a non-empty str")
        with self._lock:
            rows = self._pending.get(being_id, [])
            updated: list[EpisodicRecallObservation] = []
            for row in rows:
                if (
                    row.prediction_context_id == prediction_context_id
                    and row.prediction_outcome_error is None
                ):
                    updated.append(
                        replace(row, prediction_outcome_error=prediction_error)
                    )
                else:
                    updated.append(row)
            self._pending[being_id] = updated

    def list_episode_ids_by_prediction_context_by_being(
        self,
        being_id: BeingId,
        prediction_context_id: str,
    ) -> tuple[str, ...]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if (
            not isinstance(prediction_context_id, str)
            or not prediction_context_id.strip()
        ):
            raise ValueError("prediction_context_id must be a non-empty str")
        with self._lock:
            seen: list[str] = []
            for row in self._pending.get(being_id, ()):
                if (
                    row.prediction_context_id == prediction_context_id
                    and row.episode_id not in seen
                ):
                    seen.append(row.episode_id)
            return tuple(seen)


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
