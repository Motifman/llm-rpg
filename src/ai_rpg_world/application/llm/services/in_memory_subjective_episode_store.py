"""MVP 用 SubjectiveEpisode のインメモリストア（SQLite なし）。

PR #309 で thread-safe 化: 非同期スケジューラ
(``ThreadPoolEpisodicSubjectiveScheduler``) のワーカー thread が
``put_by_being`` で上書きする一方、メイン thread は ``list_recent_by_being`` /
``get_by_being`` で読み続けるため、内部の dict を ``threading.RLock`` で保護する。

Phase 3 Step 3e-3 (Issue #470): legacy player_id 版を撤去し、being_id 版
のみを残した。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import EpisodicEpisodeRepository
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _occurrence_sort_key(ep: SubjectiveEpisode) -> tuple[datetime, str]:
    """
    occurred_at が naive のときは UTC として解釈し、aware は UTC に寄せて比較可能にする。
    保存オブジェクトは変更しない（並び替え用キーのみ正規化）。
    """

    dt = ep.occurred_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return (dt, ep.episode_id)


class InMemorySubjectiveEpisodeStore(EpisodicEpisodeRepository):
    """Being ごとにエピソード本体を保持する。"""

    # 長走 (140+ tick × 複数 agent) で _episodes が膨らみ、list_recent の
    # O(n log n) ソートが後半 tick で二次関数的に遅くなる地雷を防ぐ。
    # 1 Being あたりの保有 episode 上限。超過時は最古から FIFO eviction
    # する (occurred_at で並べて古い方を削る)。
    # 長期 (14 日 = 140 tick) を想定し、tick 1 回 1 episode でも余裕がある
    # 数として 500 件に設定する。実験で「もっと持ちたい」となった場合は
    # 引き上げる。
    _MAX_EPISODES_PER_BEING = 500

    def __init__(self, max_episodes_per_player: int = _MAX_EPISODES_PER_BEING) -> None:
        # 引数名 max_episodes_per_player は legacy 時代の名残 (API 後方互換)。
        # 内部では being 単位の上限として扱う。3e-3 撤去後も呼出側の引数名は
        # 変えていないため、3 引数の改名は別 PR で。
        self._max_episodes_per_being = max(1, int(max_episodes_per_player))
        self._episodes_by_being: dict[BeingId, dict[str, SubjectiveEpisode]] = {}
        # 非同期スケジューラ (PR #309) のワーカー thread と本体 thread が
        # 同時に触るため、全 mutator / reader を 1 つの RLock で保護する。
        self._lock = threading.RLock()

    def put_by_being(self, being_id: BeingId, episode: SubjectiveEpisode) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        if episode.being_id != being_id:
            raise ValueError("episode.being_id must match store being_id")
        with self._lock:
            bucket = self._episodes_by_being.setdefault(being_id, {})
            bucket[episode.episode_id] = episode
            # 上限超過分を最古から evict する (long-run でのメモリ / sort 遅延対策)
            # NOTE: 端境のケースとして、被 put episode の ``occurred_at`` が既存
            # 最古より過去の場合、その episode 自体が即 evict される。これは
            # legacy ``put`` と同じ「occurred_at 単純比較」の意図的な挙動で、
            # 「過去時刻の補完 put は long-run 容量を圧迫しない」ことを優先
            # している (= 実運用では put は常に最新時刻なので影響ゼロ)。
            self._evict_oldest_over_cap(bucket)

    def get_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> SubjectiveEpisode | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
            return self._episodes_by_being.get(being_id, {}).get(episode_id)

    def list_recent_by_being(
        self,
        being_id: BeingId,
        limit: int,
    ) -> list[SubjectiveEpisode]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if limit <= 0:
            return []
        with self._lock:
            bucket = self._episodes_by_being.get(being_id)
            if not bucket:
                return []
            ordered = sorted(bucket.values(), key=_occurrence_sort_key, reverse=True)
            return ordered[:limit]

    def list_all_by_being(self, being_id: BeingId) -> list[SubjectiveEpisode]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
            bucket = self._episodes_by_being.get(being_id, {})
            return sorted(bucket.values(), key=_occurrence_sort_key)

    def replace_all_by_being(
        self, being_id: BeingId, episodes: list[SubjectiveEpisode]
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episodes, list):
            raise TypeError("episodes must be list")
        for ep in episodes:
            if not isinstance(ep, SubjectiveEpisode):
                raise TypeError("episodes elements must be SubjectiveEpisode")
            if ep.being_id != being_id:
                raise ValueError("episode.being_id must match store being_id")
        with self._lock:
            # max cap は再適用する (= snapshot に大量 episode が入っていた場合の安全策)。
            bucket = {ep.episode_id: ep for ep in episodes}
            self._episodes_by_being[being_id] = bucket
            self._evict_oldest_over_cap(bucket)

    def _evict_oldest_over_cap(self, bucket: dict[str, SubjectiveEpisode]) -> None:
        if len(bucket) <= self._max_episodes_per_being:
            return
        ordered = sorted(bucket.values(), key=_occurrence_sort_key)
        excess = len(bucket) - self._max_episodes_per_being
        for old in ordered[:excess]:
            bucket.pop(old.episode_id, None)
