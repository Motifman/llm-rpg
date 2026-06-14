"""MVP 用 SubjectiveEpisode のインメモリストア（SQLite・Passive Recall なし）。

PR #309 で thread-safe 化: 非同期スケジューラ
(``ThreadPoolEpisodicSubjectiveScheduler``) のワーカー thread が
``put`` で上書きする一方、メイン thread は ``list_recent`` / ``list_by_cue`` /
``get`` で読み続けるため、内部の dict / set を ``threading.RLock`` で保護する。
読み出しは内部状態のスナップショットを返してロック外に出す。

Phase 3 Step 3e-1 (Issue #470): being_id 版 API を並走追加。
内部に 2 つの独立した index を持つ:
- ``_episodes`` / ``_cue_index`` / ``_episode_canonicals``: player_id 版 (= 旧 API、3e-3 で撤去予定)
- ``_episodes_by_being`` 等: being_id 版 (= 新 API)
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import EpisodicEpisodeRepository
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
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
    """
    プレイヤーごとにエピソード本体と cue 逆引き索引を保持する。
    cue 照合は canonical（axis:value）のみ。EpisodicCue.source は索引に含めない。
    """

    # 長走 (140+ tick × 複数 agent) で _episodes が膨らみ、list_recent の
    # O(n log n) ソートが後半 tick で二次関数的に遅くなる地雷を防ぐ。
    # plyaer 1 人あたりの保有 episode 上限。超過時は最古から FIFO eviction
    # する (occurred_at で並べて古い方を削る)。recent recall は最新数件を
    # 見るだけなので、過去の episode を捨ててもプロンプト品質への影響は限定的。
    # 長期 (14 日 = 140 tick) を想定し、tick 1 回 1 episode でも余裕がある
    # 数として 500 件に設定する。実験で「もっと持ちたい」となった場合は
    # 引き上げる。
    _MAX_EPISODES_PER_PLAYER = 500

    def __init__(self, max_episodes_per_player: int = _MAX_EPISODES_PER_PLAYER) -> None:
        self._max_episodes_per_player = max(1, int(max_episodes_per_player))
        self._episodes: dict[int, dict[str, SubjectiveEpisode]] = {}
        self._cue_index: dict[int, dict[str, set[str]]] = {}
        self._episode_canonicals: dict[int, dict[str, frozenset[str]]] = {}
        # Phase 3 Step 3e-1: being_id 版並走 index (player_id 版と同じ構造)
        self._episodes_by_being: dict[BeingId, dict[str, SubjectiveEpisode]] = {}
        self._cue_index_by_being: dict[BeingId, dict[str, set[str]]] = {}
        self._episode_canonicals_by_being: dict[
            BeingId, dict[str, frozenset[str]]
        ] = {}
        # 非同期スケジューラ (PR #309) のワーカー thread と本体 thread が
        # 同時に触るため、全 mutator / reader を 1 つの RLock で保護する。
        # RLock にしているのは _remove_from_cue_index を put 内から呼ぶため
        # (再入を許す)。コンテンション無しでは RLock の overhead は無視できる。
        self._lock = threading.RLock()

    def put(self, episode: SubjectiveEpisode) -> None:
        pid = episode.player_id
        eid = episode.episode_id
        with self._lock:
            self._episodes.setdefault(pid, {})
            if eid in self._episodes[pid]:
                self._remove_from_cue_index(pid, eid)
            self._episodes[pid][eid] = episode
            keys = frozenset(c.to_canonical() for c in episode.cues)
            self._episode_canonicals.setdefault(pid, {})
            self._episode_canonicals[pid][eid] = keys
            self._cue_index.setdefault(pid, {})
            for ck in keys:
                self._cue_index[pid].setdefault(ck, set()).add(eid)
            # 上限超過分を最古から evict する (long-run でのメモリ / sort 遅延対策)
            bucket = self._episodes[pid]
            if len(bucket) > self._max_episodes_per_player:
                # occurred_at 昇順 = 古い順。超過 N 件を捨てる。
                ordered = sorted(bucket.values(), key=_occurrence_sort_key)
                excess = len(bucket) - self._max_episodes_per_player
                for old in ordered[:excess]:
                    self._remove_from_cue_index(pid, old.episode_id)
                    bucket.pop(old.episode_id, None)

    def get(self, player_id: int, episode_id: str) -> SubjectiveEpisode | None:
        with self._lock:
            return self._episodes.get(player_id, {}).get(episode_id)

    def list_recent(self, player_id: int, limit: int) -> list[SubjectiveEpisode]:
        if limit <= 0:
            return []
        with self._lock:
            bucket = self._episodes.get(player_id)
            if not bucket:
                return []
            # values() のスナップショットを作ってからロック外でソートしたいが、
            # ソート中に同じ episode が put で書き換わっても返却済みオブジェクト
            # は不変 (frozen dataclass) なので、ロック内で完結させた方が単純。
            ordered = sorted(bucket.values(), key=_occurrence_sort_key, reverse=True)
            return ordered[:limit]

    def list_by_cue(self, player_id: int, cue: EpisodicCue, limit: int) -> list[SubjectiveEpisode]:
        if limit <= 0:
            return []
        canonical = cue.to_canonical()
        with self._lock:
            ids = self._cue_index.get(player_id, {}).get(canonical)
            if not ids:
                return []
            bucket = self._episodes.get(player_id, {})
            eps = [bucket[i] for i in ids if i in bucket]
            ordered = sorted(eps, key=_occurrence_sort_key, reverse=True)
            return ordered[:limit]

    def _remove_from_cue_index(self, player_id: int, episode_id: str) -> None:
        # _lock 保持中の private helper (put からのみ呼ばれる)。
        keys = self._episode_canonicals.get(player_id, {}).pop(episode_id, frozenset())
        cidx = self._cue_index.get(player_id)
        if not cidx:
            return
        for ck in keys:
            s = cidx.get(ck)
            if not s:
                continue
            s.discard(episode_id)
            if not s:
                del cidx[ck]

    # ===== Phase 3 Step 3e-1: being_id 版を並走追加 =====

    def put_by_being(self, being_id: BeingId, episode: SubjectiveEpisode) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        eid = episode.episode_id
        with self._lock:
            self._episodes_by_being.setdefault(being_id, {})
            if eid in self._episodes_by_being[being_id]:
                self._remove_from_cue_index_by_being(being_id, eid)
            self._episodes_by_being[being_id][eid] = episode
            keys = frozenset(c.to_canonical() for c in episode.cues)
            self._episode_canonicals_by_being.setdefault(being_id, {})
            self._episode_canonicals_by_being[being_id][eid] = keys
            self._cue_index_by_being.setdefault(being_id, {})
            for ck in keys:
                self._cue_index_by_being[being_id].setdefault(ck, set()).add(eid)
            # 上限超過分を最古から evict する (long-run でのメモリ / sort 遅延対策)
            bucket = self._episodes_by_being[being_id]
            if len(bucket) > self._max_episodes_per_player:
                ordered = sorted(bucket.values(), key=_occurrence_sort_key)
                excess = len(bucket) - self._max_episodes_per_player
                for old in ordered[:excess]:
                    self._remove_from_cue_index_by_being(being_id, old.episode_id)
                    bucket.pop(old.episode_id, None)

    def get_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> SubjectiveEpisode | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
            return self._episodes_by_being.get(being_id, {}).get(episode_id)

    def list_recent_by_being(
        self, being_id: BeingId, limit: int
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

    def list_by_cue_by_being(
        self, being_id: BeingId, cue: EpisodicCue, limit: int
    ) -> list[SubjectiveEpisode]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if limit <= 0:
            return []
        canonical = cue.to_canonical()
        with self._lock:
            ids = self._cue_index_by_being.get(being_id, {}).get(canonical)
            if not ids:
                return []
            bucket = self._episodes_by_being.get(being_id, {})
            eps = [bucket[i] for i in ids if i in bucket]
            ordered = sorted(eps, key=_occurrence_sort_key, reverse=True)
            return ordered[:limit]

    def _remove_from_cue_index_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> None:
        # _lock 保持中の private helper (put_by_being からのみ呼ばれる)
        keys = self._episode_canonicals_by_being.get(being_id, {}).pop(
            episode_id, frozenset()
        )
        cidx = self._cue_index_by_being.get(being_id)
        if not cidx:
            return
        for ck in keys:
            s = cidx.get(ck)
            if not s:
                continue
            s.discard(episode_id)
            if not s:
                del cidx[ck]
