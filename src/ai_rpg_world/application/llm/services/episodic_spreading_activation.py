"""エピソード記憶グラフ上の拡散活性化（spreading activation）。

Phase 3 Step 3c-3 (Issue #470): legacy player_id 経路を撤去し、being_id 経路
のみに統一。``being_id=None`` の呼出は許容せず、呼出側が解決して渡す責務とする。
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

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
    being_id: BeingId,
    seed_episode_ids: frozenset[str],
    link_store: MemoryLinkRepository,
    now: datetime,
    max_hops: int = 2,
    hop_decay: float = 0.5,
    min_score: float = 0.02,
) -> dict[str, float]:
    """シードからリンクを辿り、各ノードへの最大プライミング強度を返す
    (シード自身は含めない)。

    Phase 3 Step 3c-3 で being_id keyed only。``being_id`` は必須引数。
    """
    if not isinstance(being_id, BeingId):
        raise TypeError("being_id must be BeingId")
    best: dict[str, float] = {}
    q: deque[tuple[str, int, float]] = deque()
    for sid in seed_episode_ids:
        q.append((sid, 0, 1.0))

    while q:
        node, hop, act = q.popleft()
        if hop >= max_hops:
            continue
        for link in link_store.list_links_for_episode_by_being(
            being_id, node, now=now, limit=256
        ):
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
