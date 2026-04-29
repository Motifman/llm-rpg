"""主観エピソード（v2）の能動検索。`memory_query`（DSL）とは別ツール・別経路。"""

from __future__ import annotations

from typing import List

from ai_rpg_world.application.llm.contracts.dtos import SubjectiveEpisode
from ai_rpg_world.application.llm.contracts.interfaces import ISubjectiveEpisodeStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class SubjectiveMemoryRecallExecutor:
    """`ISubjectiveEpisodeStore` を走査し、キーワードで絞り込んでテキスト化する。"""

    def __init__(
        self,
        *,
        subjective_episode_store: ISubjectiveEpisodeStore,
        max_scan: int = 200,
    ) -> None:
        if not isinstance(subjective_episode_store, ISubjectiveEpisodeStore):
            raise TypeError("subjective_episode_store must be ISubjectiveEpisodeStore")
        if max_scan < 1:
            raise ValueError("max_scan must be >= 1")
        self._store = subjective_episode_store
        self._max_scan = max_scan

    def execute(
        self,
        player_id: PlayerId,
        *,
        keywords: str = "",
        limit: int = 10,
    ) -> str:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(keywords, str):
            raise TypeError("keywords must be str")
        if not isinstance(limit, int):
            raise TypeError("limit must be int")
        if limit < 1:
            limit = 1
        if limit > 50:
            limit = 50
        episodes = self._store.list_recent(player_id, self._max_scan)
        if not episodes:
            return "（主観エピソードはまだありません）"
        kw = keywords.strip().lower()
        picked: List[SubjectiveEpisode] = []
        if not kw:
            picked = list(episodes[:limit])
        else:
            for ep in episodes:
                blob = (
                    " ".join(ep.cue_keys)
                    + "\n"
                    + ep.observed
                    + "\n"
                    + ep.interpreted
                ).lower()
                if kw in blob:
                    picked.append(ep)
                if len(picked) >= limit:
                    break
        if not picked:
            return f"（キーワード「{keywords.strip()}」に合致する主観エピソードはありません）"
        lines: List[str] = []
        for ep in picked:
            cue = " / ".join(ep.cue_keys[:4]) if ep.cue_keys else "—"
            obs = ep.observed.strip().replace("\n", " ")[:140]
            lines.append(
                f"- id={ep.episode_id} importance={ep.importance} cues={cue} | {obs}"
            )
        return "【主観エピソード（検索結果）】\n" + "\n".join(lines)
