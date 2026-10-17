"""エピソード記憶の時間的近接リンクの作成と強化。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
    effective_link_strength,
    normalize_episode_pair,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode

DEFAULT_TEMPORAL_INITIAL_STRENGTH = 0.5
DEFAULT_DECAY_RATE = 0.01
MAX_LINKS_PER_EPISODE = 256
HEBBIAN_ETA = 0.1
ACTIVATION_PASSIVE = 0.8
DECAY_REDUCTION_ON_COACTIVATION = 0.85


class EpisodicMemoryLinkApplicationService:
    """
    時間的近接リンクの記録とヘブ則強化。
    """

    def __init__(
        self,
        episode_store: EpisodicEpisodeRepository,
        link_store: MemoryLinkRepository,
        *,
        temporal_initial: float = DEFAULT_TEMPORAL_INITIAL_STRENGTH,
        decay_rate_initial: float = DEFAULT_DECAY_RATE,
        max_links_per_episode: int = MAX_LINKS_PER_EPISODE,
    ) -> None:
        if not isinstance(episode_store, EpisodicEpisodeRepository):
            raise TypeError("episode_store must be EpisodicEpisodeRepository")
        if not isinstance(link_store, MemoryLinkRepository):
            raise TypeError("link_store must be MemoryLinkRepository")
        self._episodes = episode_store
        self._links = link_store
        self._temporal_initial = temporal_initial
        self._decay_rate_initial = decay_rate_initial
        self._max_links = max_links_per_episode

    def on_episode_committed(
        self,
        episode: SubjectiveEpisode,
        *,
        now: datetime | None = None,
    ) -> None:
        """直近の別エピソードとの TEMPORAL リンクを 1 本作成する。"""
        now = now or datetime.now(timezone.utc)
        being_id = episode.being_id
        pid = episode.player_id
        recent = self._list_recent_episodes(being_id, limit=2)
        if len(recent) < 2:
            return
        newest, prev = recent[0], recent[1]
        if newest.episode_id != episode.episode_id:
            return
        self._ensure_capacity_before_link(
            being_id, pid, newest.episode_id, prev.episode_id, now
        )
        self._put_fresh_link(
            being_id=being_id,
            player_id=pid,
            ep_a=newest.episode_id,
            ep_b=prev.episode_id,
            link_type=MemoryLinkType.TEMPORAL,
            initial_strength=self._temporal_initial,
            now=now,
        )

    def _list_recent_episodes(
        self,
        being_id: BeingId,
        limit: int,
    ) -> list[SubjectiveEpisode]:
        """being_id 経路で episode の list_recent を取得する。"""
        return self._episodes.list_recent_by_being(being_id, limit)

    def _ensure_capacity_before_link(
        self,
        being_id: BeingId,
        player_id: int,
        episode_id_a: str,
        episode_id_b: str,
        now: datetime,
    ) -> None:
        for eid in (episode_id_a, episode_id_b):
            while self._links.count_links_for_episode_by_being(being_id, eid) >= self._max_links:
                removed = self._links.remove_weakest_link_for_episode_by_being(
                    being_id, eid, now=now
                )
                if not removed:
                    break

    def _put_fresh_link(
        self,
        *,
        being_id: BeingId,
        player_id: int,
        ep_a: str,
        ep_b: str,
        link_type: MemoryLinkType,
        initial_strength: float,
        now: datetime,
    ) -> None:
        a, b = normalize_episode_pair(ep_a, ep_b)
        existing = self._links.get_link_by_being(being_id, a, b, link_type)
        if existing is not None:
            self._hebbian_strengthen_existing(
                being_id,
                existing,
                activation_a=ACTIVATION_PASSIVE,
                activation_b=ACTIVATION_PASSIVE,
                now=now,
            )
            return
        link = MemoryLink(
            link_id=f"memlink-{uuid4().hex}",
            player_id=player_id,
            being_id=being_id,
            episode_id_a=a,
            episode_id_b=b,
            link_type=link_type,
            strength=initial_strength,
            co_activation_count=1,
            created_at=now,
            last_activated_at=now,
            decay_rate=self._decay_rate_initial,
        )
        self._links.upsert_link_by_being(being_id, link)

    def _hebbian_strengthen_existing(
        self,
        being_id: BeingId,
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
        self._links.upsert_link_by_being(being_id, updated)
