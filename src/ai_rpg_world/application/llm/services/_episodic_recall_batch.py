"""``peek_batch`` の episode-batched 選別ロジック共有 helper。

InMemory / SQLite 両方の ``EpisodicRecallBufferRepository`` 実装が同じ
セマンティクスで rows を episode 単位にバッチング (= ``batch_size`` 件の
distinct episode に絞り、各 episode ごと ``max_contexts_per_episode`` 件まで
採用) するため、Phase 3 Step 3d-1 のレビュー (#496 HIGH) を受けて helper を
分離した。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)


def _dt_key(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def select_episode_batched(
    rows: list[EpisodicRecallObservation],
    *,
    batch_size: int,
    max_contexts_per_episode: int,
) -> tuple[EpisodicRecallObservation, ...]:
    """``(recalled_at_key, recall_id)`` 昇順でソート済 (= 内部で再ソート) の
    rows から、distinct episode を最大 ``batch_size`` 件選び、各 episode から
    最大 ``max_contexts_per_episode`` 件まで採用して返す。

    早期 return: ``batch_size <= 0`` または ``max_contexts_per_episode <= 0`` の
    場合は空 tuple。呼出側のチェック後にも防御として残してある。
    """
    if batch_size <= 0 or max_contexts_per_episode <= 0:
        return ()
    rows_sorted = sorted(rows, key=lambda r: (_dt_key(r.recalled_at), r.recall_id))
    selected_episode_ids: list[str] = []
    counts: dict[str, int] = {}
    out: list[EpisodicRecallObservation] = []
    for row in rows_sorted:
        if row.episode_id not in counts:
            if len(selected_episode_ids) >= batch_size:
                continue
            selected_episode_ids.append(row.episode_id)
            counts[row.episode_id] = 0
        if counts[row.episode_id] >= max_contexts_per_episode:
            continue
        counts[row.episode_id] += 1
        out.append(row)
    return tuple(out)


__all__ = ["select_episode_batched"]
