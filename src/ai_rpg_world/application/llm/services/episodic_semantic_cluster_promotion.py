"""強リンククラスタ検出とセマンティック記憶への昇格（MVP: 決定論要約）。"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Set
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import IEpisodicEpisodeStore
from ai_rpg_world.application.llm.contracts.episodic_memory import SubjectiveEpisode
from ai_rpg_world.application.llm.contracts.episodic_memory_link import effective_link_strength
from ai_rpg_world.application.llm.contracts.episodic_memory_link_store_port import IMemoryLinkStore
from ai_rpg_world.application.llm.contracts.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.application.llm.contracts.semantic_memory_store_port import ISemanticMemoryStore
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import EpisodicPromotionFrontier

MIN_CLUSTER_SIZE = 3
MIN_RECALL_COUNT = 3
MIN_EFFECTIVE_STRENGTH = 0.5


def _env_force_full_scan() -> bool:
    v = (os.environ.get("EPISODIC_PROMOTION_FORCE_FULL_SCAN") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _default_expansion_hops() -> int:
    raw = (os.environ.get("EPISODIC_PROMOTION_EXPANSION_HOPS") or "").strip()
    if not raw:
        return 4
    try:
        return max(0, int(raw))
    except ValueError:
        return 4


def _evidence_signature(episode_ids: Set[str]) -> str:
    return ",".join(sorted(episode_ids))


def _build_strong_adjacency(
    player_id: int,
    link_store: IMemoryLinkStore,
    now: datetime,
) -> Dict[str, Set[str]]:
    """実効強度 >= 閾値の無向辺を隣接リスト化する。"""
    adj: Dict[str, Set[str]] = {}
    for ln in link_store.list_all_links_for_player(player_id):
        eff = effective_link_strength(ln, now)
        if eff < MIN_EFFECTIVE_STRENGTH:
            continue
        a = ln.episode_id_a
        b = ln.episode_id_b
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _expand_frontier_nodes(
    player_id: int,
    link_store: IMemoryLinkStore,
    seeds: Set[str],
    now: datetime,
    max_hops: int,
) -> Set[str]:
    """強リンクのみを辿り、シードから最大 max_hops ホップで到達するノード集合。"""
    seeds_clean = {s.strip() for s in seeds if s.strip()}
    if not seeds_clean:
        return set()
    nodes = set(seeds_clean)
    frontier = set(seeds_clean)
    for _ in range(max(0, max_hops)):
        nxt: Set[str] = set()
        for n in frontier:
            for ln in link_store.list_all_incident_links(player_id, n, now=now):
                if effective_link_strength(ln, now) < MIN_EFFECTIVE_STRENGTH:
                    continue
                other = ln.episode_id_b if ln.episode_id_a == n else ln.episode_id_a
                if other not in nodes:
                    nxt.add(other)
        if not nxt:
            break
        nodes |= nxt
        frontier = nxt
    return nodes


def _build_strong_adjacency_for_nodes(
    player_id: int,
    link_store: IMemoryLinkStore,
    nodes: Set[str],
    now: datetime,
) -> Dict[str, Set[str]]:
    """nodes に含まれる頂点のみを対象に、強リンクで誘導する無向グラフの隣接リスト。"""
    adj: Dict[str, Set[str]] = {}
    for n in nodes:
        for ln in link_store.list_all_incident_links(player_id, n, now=now):
            if effective_link_strength(ln, now) < MIN_EFFECTIVE_STRENGTH:
                continue
            other = ln.episode_id_b if ln.episode_id_a == n else ln.episode_id_a
            if other in nodes:
                adj.setdefault(n, set()).add(other)
                adj.setdefault(other, set()).add(n)
    return adj


def _connected_components(adj: Dict[str, Set[str]]) -> list[Set[str]]:
    seen: Set[str] = set()
    out: list[Set[str]] = []
    for start in adj:
        if start in seen:
            continue
        comp: Set[str] = set()
        q: deque[str] = deque([start])
        while q:
            n = q.popleft()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            for nb in adj.get(n, ()):
                if nb not in seen:
                    q.append(nb)
        if comp:
            out.append(comp)
    return out


def _deterministic_gist(episodes: list[SubjectiveEpisode]) -> str:
    parts: list[str] = []
    for ep in episodes:
        body = (ep.interpreted or ep.recall_text or ep.what or "").strip()
        if body:
            parts.append(body)
    if not parts:
        return "（要約不能: 解釈文が空）"
    joined = " / ".join(parts)
    return joined[:1200]


@dataclass
class EpisodicSemanticClusterPromotionService:
    """
    プレイヤーのリンクグラフから閾値以上のクラスタを探し、セマンティックストアへ書き込む。
    LLM 脱文脈化は未接続時はスキップし、決定論要約のみ行う。
    """

    episode_store: IEpisodicEpisodeStore
    link_store: IMemoryLinkStore
    semantic_store: ISemanticMemoryStore
    promotion_frontier: EpisodicPromotionFrontier | None = None
    expansion_hops: int = field(default_factory=_default_expansion_hops)

    def on_after_tool_turn(self, player_id: int, *, now: datetime | None = None) -> None:
        """LLM ツール実行 1 回成功後に呼び、昇格候補があればストアへ追加する。"""
        now = now or datetime.now(timezone.utc)
        force_full = _env_force_full_scan()
        if force_full or self.promotion_frontier is None:
            adj = _build_strong_adjacency(player_id, self.link_store, now)
        else:
            seeds = self.promotion_frontier.drain(player_id)
            if not seeds:
                adj = _build_strong_adjacency(player_id, self.link_store, now)
            else:
                nodes = _expand_frontier_nodes(
                    player_id,
                    self.link_store,
                    seeds,
                    now,
                    self.expansion_hops,
                )
                adj = _build_strong_adjacency_for_nodes(
                    player_id,
                    self.link_store,
                    nodes,
                    now,
                )
        if not adj:
            return
        for comp in _connected_components(adj):
            if len(comp) < MIN_CLUSTER_SIZE:
                continue
            eps: list[SubjectiveEpisode] = []
            cluster_ok = True
            for eid in comp:
                ep = self.episode_store.get(player_id, eid)
                if ep is None or ep.recall_count < MIN_RECALL_COUNT:
                    cluster_ok = False
                    break
                eps.append(ep)
            if not cluster_ok or len(eps) < MIN_CLUSTER_SIZE:
                continue
            sig = _evidence_signature(comp)
            if not self.semantic_store.register_cluster_signature_if_new(player_id, sig):
                continue
            confidence = min(1.0, 0.4 + 0.1 * len(eps))
            text = _deterministic_gist(sorted(eps, key=lambda e: e.occurred_at))
            entry = SemanticMemoryEntry(
                entry_id=f"sem-{uuid4().hex}",
                player_id=player_id,
                text=text,
                evidence_episode_ids=tuple(sorted(comp)),
                confidence=confidence,
                created_at=now,
            )
            self.semantic_store.add(entry)
