"""MVP 用 SubjectiveEpisode のインメモリストア（SQLite・Passive Recall なし）。"""

from __future__ import annotations

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

    def put(self, episode: SubjectiveEpisode) -> None:
        pid = episode.player_id
        eid = episode.episode_id
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
        return self._episodes.get(player_id, {}).get(episode_id)

    def list_recent(self, player_id: int, limit: int) -> list[SubjectiveEpisode]:
        if limit <= 0:
            return []
        bucket = self._episodes.get(player_id)
        if not bucket:
            return []
        ordered = sorted(bucket.values(), key=_occurrence_sort_key, reverse=True)
        return ordered[:limit]

    def list_by_cue(self, player_id: int, cue: EpisodicCue, limit: int) -> list[SubjectiveEpisode]:
        if limit <= 0:
            return []
        canonical = cue.to_canonical()
        ids = self._cue_index.get(player_id, {}).get(canonical)
        if not ids:
            return []
        bucket = self._episodes.get(player_id, {})
        eps = [bucket[i] for i in ids if i in bucket]
        ordered = sorted(eps, key=_occurrence_sort_key, reverse=True)
        return ordered[:limit]

    def _remove_from_cue_index(self, player_id: int, episode_id: str) -> None:
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
