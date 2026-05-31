"""MVP 用 SubjectiveEpisode のインメモリストア（SQLite・Passive Recall なし）。

PR #309 で thread-safe 化: 非同期スケジューラ
(``ThreadPoolEpisodicSubjectiveScheduler``) のワーカー thread が
``put`` で上書きする一方、メイン thread は ``list_recent`` / ``list_by_cue`` /
``get`` で読み続けるため、内部の dict / set を ``threading.RLock`` で保護する。
読み出しは内部状態のスナップショットを返してロック外に出す。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import IEpisodicEpisodeStore
from ai_rpg_world.application.llm.contracts.episodic_memory import EpisodicCue, SubjectiveEpisode


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


class InMemorySubjectiveEpisodeStore(IEpisodicEpisodeStore):
    """
    プレイヤーごとにエピソード本体と cue 逆引き索引を保持する。
    cue 照合は canonical（axis:value）のみ。EpisodicCue.source は索引に含めない。
    """

    def __init__(self) -> None:
        self._episodes: dict[int, dict[str, SubjectiveEpisode]] = {}
        self._cue_index: dict[int, dict[str, set[str]]] = {}
        self._episode_canonicals: dict[int, dict[str, frozenset[str]]] = {}
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
