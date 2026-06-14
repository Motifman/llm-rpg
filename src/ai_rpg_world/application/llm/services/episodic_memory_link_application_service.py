"""エピソード記憶リンクの作成・強化・想起メタデータ更新。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from typing import Optional

from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
    effective_link_strength,
    normalize_episode_pair,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallCandidate,
)
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import (
    EpisodicPromotionFrontier,
)

DEFAULT_TEMPORAL_INITIAL_STRENGTH = 0.5
DEFAULT_CO_RECALL_INITIAL_STRENGTH = 0.3
DEFAULT_DECAY_RATE = 0.01
MAX_LINKS_PER_EPISODE = 256
CO_RECALL_EPISODE_CAP = 8
HEBBIAN_ETA = 0.1
ACTIVATION_PASSIVE = 0.8
ACTIVATION_META_EXPLORE = 1.0
ACTIVATION_PRIMING = 0.3
DECAY_REDUCTION_ON_COACTIVATION = 0.85


class EpisodicMemoryLinkApplicationService:
    """
    時間的近接リンク・共想起リンクの記録、ヘブ則強化、想起カウンタ更新。
    """

    def __init__(
        self,
        episode_store: EpisodicEpisodeRepository,
        link_store: MemoryLinkRepository,
        *,
        promotion_frontier: EpisodicPromotionFrontier | None = None,
        temporal_initial: float = DEFAULT_TEMPORAL_INITIAL_STRENGTH,
        co_recall_initial: float = DEFAULT_CO_RECALL_INITIAL_STRENGTH,
        decay_rate_initial: float = DEFAULT_DECAY_RATE,
        max_links_per_episode: int = MAX_LINKS_PER_EPISODE,
        co_recall_episode_cap: int = CO_RECALL_EPISODE_CAP,
        being_attachment_resolver: Optional[BeingAttachmentResolver] = None,
        default_world_id: Optional[WorldId] = None,
    ) -> None:
        if not isinstance(episode_store, EpisodicEpisodeRepository):
            raise TypeError("episode_store must be EpisodicEpisodeRepository")
        if not isinstance(link_store, MemoryLinkRepository):
            raise TypeError("link_store must be MemoryLinkRepository")
        # Phase 3 Step 3c-2: Resolver+WorldId 注入時は being_id 経路、未注入なら
        # legacy player_id 経路。link 更新は turn の副作用なので Being 未解決時は
        # silent no-op (= 次回 turn で再試行) を許容する設計。
        if being_attachment_resolver is not None and not isinstance(
            being_attachment_resolver, BeingAttachmentResolver
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if default_world_id is not None and not isinstance(default_world_id, WorldId):
            raise TypeError("default_world_id must be WorldId")
        self._episodes = episode_store
        self._links = link_store
        self._promotion_frontier = promotion_frontier
        self._temporal_initial = temporal_initial
        self._co_recall_initial = co_recall_initial
        self._decay_rate_initial = decay_rate_initial
        self._max_links = max_links_per_episode
        self._co_cap = co_recall_episode_cap
        self._resolver = being_attachment_resolver
        self._default_world_id = default_world_id

    def _resolve_being_id(self, player_id: int) -> Optional[BeingId]:
        """Resolver+WorldId が両方注入されていれば being_id を引く。

        Phase 3 Step 3c-2: dual-path。未注入 or Being 未 provision なら None
        (= legacy 経路へ fallback)。Step 3c-3 で legacy 撤去予定。
        """
        if self._resolver is None or self._default_world_id is None:
            return None
        return self._resolver.resolve_being_id(
            self._default_world_id, PlayerId(player_id)
        )

    # --- dual-path link store wrappers ---

    def _count_links(self, player_id: int, episode_id: str) -> int:
        being_id = self._resolve_being_id(player_id)
        if being_id is not None:
            return self._links.count_links_for_episode_by_being(being_id, episode_id)
        return self._links.count_links_for_episode(player_id, episode_id)

    def _remove_weakest(
        self, player_id: int, episode_id: str, *, now: datetime
    ) -> bool:
        being_id = self._resolve_being_id(player_id)
        if being_id is not None:
            return self._links.remove_weakest_link_for_episode_by_being(
                being_id, episode_id, now=now
            )
        return self._links.remove_weakest_link_for_episode(
            player_id, episode_id, now=now
        )

    def _get_link(
        self,
        player_id: int,
        episode_id_a: str,
        episode_id_b: str,
        link_type: MemoryLinkType,
    ) -> MemoryLink | None:
        being_id = self._resolve_being_id(player_id)
        if being_id is not None:
            return self._links.get_link_by_being(
                being_id, episode_id_a, episode_id_b, link_type
            )
        return self._links.get_link(player_id, episode_id_a, episode_id_b, link_type)

    def _upsert_link(self, player_id: int, link: MemoryLink) -> None:
        being_id = self._resolve_being_id(player_id)
        if being_id is not None:
            self._links.upsert_link_by_being(being_id, link)
            return
        self._links.upsert_link(link)

    def on_episode_committed(self, episode: SubjectiveEpisode, *, now: datetime | None = None) -> None:
        """直近の別エピソードとの TEMPORAL リンクを 1 本作成する。"""
        now = now or datetime.now(timezone.utc)
        pid = episode.player_id
        recent = self._episodes.list_recent(pid, 2)
        if len(recent) < 2:
            return
        newest, prev = recent[0], recent[1]
        if newest.episode_id != episode.episode_id:
            return
        self._ensure_capacity_before_link(pid, newest.episode_id, prev.episode_id, now)
        self._put_fresh_link(
            player_id=pid,
            ep_a=newest.episode_id,
            ep_b=prev.episode_id,
            link_type=MemoryLinkType.TEMPORAL,
            initial_strength=self._temporal_initial,
            now=now,
        )

    def on_passive_recall_candidates(
        self,
        player_id: int,
        candidates: Sequence[EpisodicPassiveRecallCandidate],
        *,
        now: datetime | None = None,
    ) -> None:
        """Passive Recall 候補について CO_RECALL リンクと recall メタデータを更新する。"""
        now = now or datetime.now(timezone.utc)
        if self._promotion_frontier is not None:
            for c in candidates:
                self._promotion_frontier.add(player_id, c.episode.episode_id)
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for c in candidates:
            eid = c.episode.episode_id
            if eid not in seen:
                seen.add(eid)
                ordered_ids.append(eid)
        capped = ordered_ids[: self._co_cap]
        self._bump_recall_counts(player_id, capped, now)
        for i in range(len(capped)):
            for j in range(i + 1, len(capped)):
                self._ensure_capacity_before_link(player_id, capped[i], capped[j], now)
                self._merge_co_recall(player_id, capped[i], capped[j], now)

    def note_promotion_frontier_episodes(
        self,
        player_id: int,
        episode_ids: Sequence[str],
    ) -> None:
        """能動探索など、リンク更新以外で触れたエピソードを昇格フロンティアに記録する。"""
        if self._promotion_frontier is None:
            return
        self._promotion_frontier.add_many(player_id, episode_ids)

    def strengthen_from_meta_exploration(
        self,
        player_id: int,
        center_episode_id: str,
        neighbor_episode_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        """memory_explore_related 等で辿った隣接エピソード間を強化する。"""
        now = now or datetime.now(timezone.utc)
        for lt in (MemoryLinkType.CO_RECALL, MemoryLinkType.TEMPORAL):
            self._hebbian_strengthen_pair(
                player_id,
                center_episode_id,
                neighbor_episode_id,
                link_type=lt,
                activation_a=ACTIVATION_META_EXPLORE,
                activation_b=ACTIVATION_META_EXPLORE,
                now=now,
            )

    def _bump_recall_counts(self, player_id: int, episode_ids: Sequence[str], now: datetime) -> None:
        for eid in episode_ids:
            ep = self._episodes.get(player_id, eid)
            if ep is None:
                continue
            updated = replace(
                ep,
                recall_count=ep.recall_count + 1,
                last_recalled_at=now,
            )
            self._episodes.put(updated)

    def _ensure_capacity_before_link(
        self,
        player_id: int,
        episode_id_a: str,
        episode_id_b: str,
        now: datetime,
    ) -> None:
        for eid in (episode_id_a, episode_id_b):
            while self._count_links(player_id, eid) >= self._max_links:
                removed = self._remove_weakest(player_id, eid, now=now)
                if self._promotion_frontier is not None:
                    self._promotion_frontier.add(player_id, eid)
                if not removed:
                    break

    def _put_fresh_link(
        self,
        *,
        player_id: int,
        ep_a: str,
        ep_b: str,
        link_type: MemoryLinkType,
        initial_strength: float,
        now: datetime,
    ) -> None:
        a, b = normalize_episode_pair(ep_a, ep_b)
        existing = self._get_link(player_id, a, b, link_type)
        if existing is not None:
            self._hebbian_strengthen_existing(
                existing,
                activation_a=ACTIVATION_PASSIVE,
                activation_b=ACTIVATION_PASSIVE,
                now=now,
            )
            return
        link = MemoryLink(
            link_id=f"memlink-{uuid4().hex}",
            player_id=player_id,
            episode_id_a=a,
            episode_id_b=b,
            link_type=link_type,
            strength=initial_strength,
            co_activation_count=1,
            created_at=now,
            last_activated_at=now,
            decay_rate=self._decay_rate_initial,
        )
        self._upsert_link(player_id, link)
        if self._promotion_frontier is not None:
            self._promotion_frontier.add(player_id, a)
            self._promotion_frontier.add(player_id, b)

    def _merge_co_recall(self, player_id: int, ep_a: str, ep_b: str, now: datetime) -> None:
        a, b = normalize_episode_pair(ep_a, ep_b)
        existing = self._get_link(player_id, a, b, MemoryLinkType.CO_RECALL)
        if existing is None:
            self._put_fresh_link(
                player_id=player_id,
                ep_a=a,
                ep_b=b,
                link_type=MemoryLinkType.CO_RECALL,
                initial_strength=self._co_recall_initial,
                now=now,
            )
            return
        self._hebbian_strengthen_existing(
            existing,
            activation_a=ACTIVATION_PASSIVE,
            activation_b=ACTIVATION_PASSIVE,
            now=now,
        )

    def _hebbian_strengthen_existing(
        self,
        link: MemoryLink,
        *,
        activation_a: float,
        activation_b: float,
        now: datetime,
    ) -> None:
        eff = effective_link_strength(link, now)
        delta = HEBBIAN_ETA * activation_a * activation_b
        new_strength = min(1.0, eff + delta)
        new_co = link.co_activation_count + 1
        new_decay = link.decay_rate * DECAY_REDUCTION_ON_COACTIVATION
        updated = replace(
            link,
            strength=new_strength,
            co_activation_count=new_co,
            last_activated_at=now,
            decay_rate=new_decay,
        )
        self._upsert_link(updated.player_id, updated)
        if self._promotion_frontier is not None:
            self._promotion_frontier.add(updated.player_id, updated.episode_id_a)
            self._promotion_frontier.add(updated.player_id, updated.episode_id_b)

    def _hebbian_strengthen_pair(
        self,
        player_id: int,
        ep_a: str,
        ep_b: str,
        *,
        link_type: MemoryLinkType,
        activation_a: float,
        activation_b: float,
        now: datetime,
    ) -> None:
        a, b = normalize_episode_pair(ep_a, ep_b)
        existing = self._get_link(player_id, a, b, link_type)
        if existing is None:
            return
        self._hebbian_strengthen_existing(
            existing,
            activation_a=activation_a,
            activation_b=activation_b,
            now=now,
        )
