"""エピソード記憶グラフ上の拡散活性化（spreading activation）。"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from ai_rpg_world.application.llm.contracts.episodic_memory_link import (
    effective_link_strength,
    other_episode_id,
)
from ai_rpg_world.application.llm.contracts.episodic_memory_link_store_port import (
    IMemoryLinkStore,
)


def neighbor_priming_scores(
    *,
    player_id: int,
    seed_episode_ids: frozenset[str],
    link_store: IMemoryLinkStore,
    now: datetime,
    max_hops: int = 2,
    hop_decay: float = 0.5,
    min_score: float = 0.02,
) -> dict[str, float]:
    """
    シードからリンクを辿り、各ノードへの最大プライミング強度を返す（シード自身は含めない）。
    """
    best: dict[str, float] = {}
    q: deque[tuple[str, int, float]] = deque()
    for sid in seed_episode_ids:
        q.append((sid, 0, 1.0))

    while q:
        node, hop, act = q.popleft()
        if hop >= max_hops:
            continue
        for link in link_store.list_links_for_episode(
            player_id, node, now=now, limit=256
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
