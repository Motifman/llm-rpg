"""PendingPrediction 用の in-memory ストア実装。

U10a (予測誤差統一設計 部品6)。``InMemoryBeliefEvidenceBufferStore`` と同型の
Being ごとの list 保持 + 容量上限 evict。

横断レビュー H-3/M2 で thread-safe 化: ThreadPool の chunk 補完ワーカー
(``episodic_subjective_completion_schedulers.py``) が ``add_by_being`` /
``resolve_pending_predictions_if_applicable`` (list → replace の
read-modify-write) を同一 thread 内で叩く一方、メイン thread も
``prompt_builder`` / ``episodic_chunk_coordinator`` から ``list_all_by_being``
を読む。#309 の ``InMemorySubjectiveEpisodeStore`` と同じ ``threading.RLock``
パターンで公開メソッド全体を保護する。
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.pending_prediction_repository import (
    PENDING_PREDICTION_DEFAULT_CAP,
    PendingPredictionRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)


class InMemoryPendingPredictionStore(PendingPredictionRepository):
    """Being ごとに ``PendingPrediction`` の list を保持する。"""

    def __init__(self, *, capacity: int = PENDING_PREDICTION_DEFAULT_CAP) -> None:
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be a positive int")
        self._capacity = capacity
        self._predictions: dict[BeingId, list[PendingPrediction]] = defaultdict(list)
        # ワーカー thread とメイン thread が同じ dict / list を触るため、
        # 公開メソッド全体を 1 つの RLock で保護する (#309 と同じ粒度・同じ理由)。
        self._lock = threading.RLock()

    def add_by_being(
        self, being_id: BeingId, pending: PendingPrediction
    ) -> Optional[PendingPrediction]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(pending, PendingPrediction):
            raise TypeError("pending must be PendingPrediction")
        with self._lock:
            bucket = self._predictions[being_id]
            evicted: Optional[PendingPrediction] = None
            if len(bucket) >= self._capacity:
                # 最も古い (= created_tick 最小、同値なら追加順が先の) 1 件を
                # evict。list は追加順を保っているので、created_tick で安定
                # sort した先頭が「最古」。sorted() は安定ソートなので同値は
                # 追加順のまま残る。
                oldest = min(range(len(bucket)), key=lambda i: bucket[i].created_tick)
                evicted = bucket.pop(oldest)
            bucket.append(pending)
            return evicted

    def list_all_by_being(self, being_id: BeingId) -> list[PendingPrediction]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
            return list(self._predictions.get(being_id, ()))

    def replace_all_by_being(
        self,
        being_id: BeingId,
        predictions: list[PendingPrediction],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(predictions, list):
            raise TypeError("predictions must be list")
        for p in predictions:
            if not isinstance(p, PendingPrediction):
                raise TypeError("predictions elements must be PendingPrediction")
        with self._lock:
            self._predictions[being_id] = list(predictions)


__all__ = ["InMemoryPendingPredictionStore"]
