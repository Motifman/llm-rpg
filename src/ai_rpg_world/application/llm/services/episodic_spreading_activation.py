"""エピソード記憶グラフ上の拡散活性化（spreading activation）。"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    effective_link_strength,
    other_episode_id,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)


def neighbor_priming_scores(
    *,
    player_id: int,
    seed_episode_ids: frozenset[str],
    link_store: MemoryLinkRepository,
    now: datetime,
    max_hops: int = 2,
    hop_decay: float = 0.5,
    min_score: float = 0.02,
    being_id: Optional[BeingId] = None,
) -> dict[str, float]:
    """
    シードからリンクを辿り、各ノードへの最大プライミング強度を返す（シード自身は含めない）。

    Phase 3 Step 3c-2 (Issue #470): dual-path。``being_id`` が渡された場合は
    ``list_links_for_episode_by_being`` で読む。None なら legacy
    ``list_links_for_episode`` で読む。Step 3c-3 で legacy 経路撤去予定。
    """
    best: dict[str, float] = {}
    q: deque[tuple[str, int, float]] = deque()
    for sid in seed_episode_ids:
        q.append((sid, 0, 1.0))

    while q:
        node, hop, act = q.popleft()
        if hop >= max_hops:
            continue
        if being_id is not None:
            links = link_store.list_links_for_episode_by_being(
                being_id, node, now=now, limit=256
            )
        else:
            links = link_store.list_links_for_episode(
                player_id, node, now=now, limit=256
            )
        for link in links:
            other = other_episode_id(link, node)
            if other in seed_episode_ids:
                continue
            eff = effective_link_strength(link, now)
            n_score = act * eff * (hop_decay ** (hop + 1))
            if n_score < min_score:
                continue
            prev = best.get(other, 0.0)
            if n_score > prev:
                best[other] = n_score
                q.append((other, hop + 1, n_score))

    return best
