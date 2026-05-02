"""v2 SubjectiveEpisode 由来の Passive Recall（user ブロック／ルールベースのみ）。

ここで行うのは **想起候補のスコアリングと、保存済み主観文面からの短い要約行の組み立て** に限る。
計画における **Memory Reflection**（想起されたエピソードを、LLM で「いま」の視点から言い換え直す）とは別物で、
後者はプロンプト組み立てのクリティカルパスに載せず、非同期ジョブ等で行う想定。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Set, Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    PassiveRecallComposeResult,
    SubjectiveEpisode,
    subjective_episode_index_strings,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IPassiveSubjectiveRecallComposer,
    ISubjectiveEpisodeStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_RECALL_HEADER = "【ふと思い出したこと】"


def _tokenize_cues(text: str) -> Set[str]:
    if not text.strip():
        return set()
    text_l = text.lower()
    parts = re.findall(r"[a-z0-9_]{2,}|[\u3040-\u30ff\u4e00-\u9fff]+", text_l)
    return {p for p in parts if p}


def _normalized_episode_cues(ep: SubjectiveEpisode) -> Set[str]:
    return {k.strip().lower() for k in subjective_episode_index_strings(ep) if k.strip()}


def _recency_bonus(ep: SubjectiveEpisode, *, now: datetime) -> float:
    delta = (now - ep.created_at).total_seconds() / 3600.0
    if delta < 0:
        delta = 0.0
    return max(0.0, 18.0 - min(delta, 18.0))


def _importance_bonus(ep: SubjectiveEpisode) -> int:
    if ep.importance == "high":
        return 28
    if ep.importance == "medium":
        return 12
    return 0


def _goal_overlap_score(ep: SubjectiveEpisode, goal_tokens: Set[str]) -> int:
    if not goal_tokens:
        return 0
    blob = f"{ep.observed}\n{ep.interpreted}".lower()
    return sum(8 for t in goal_tokens if t in blob)


def _cue_hits_in_situation(situation_text: str, ep_cues: Set[str]) -> int:
    if not ep_cues or not situation_text.strip():
        return 0
    blob = situation_text.lower()
    return sum(1 for c in ep_cues if c and c in blob)


def score_episode_for_recall(
    ep: SubjectiveEpisode,
    *,
    situation_text: str,
    goal_tokens: Set[str],
    now: datetime,
) -> float:
    """デバッグ·テスト用に公開したスコア関数。"""
    ep_cues = _normalized_episode_cues(ep)
    overlap = _cue_hits_in_situation(situation_text, ep_cues)
    score = overlap * 44.0
    score += _importance_bonus(ep)
    score += _recency_bonus(ep, now=now)
    score += _goal_overlap_score(ep, goal_tokens)
    return score


def _one_line(text: str, max_len: int) -> str:
    s = text.strip().replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _format_recall_line(ep: SubjectiveEpisode) -> str:
    idx = subjective_episode_index_strings(ep)
    tags = " / ".join(idx[:5]) if idx else "—"
    obs = _one_line(ep.observed, 130)
    interp = _one_line(ep.interpreted, 72) if ep.interpreted.strip() else ""
    imp = ep.importance
    if interp:
        return f"[{imp}] タグ:{tags}｜{obs} — 当時の解釈:{interp}"
    return f"[{imp}] タグ:{tags}｜{obs}"


class PassiveSubjectiveRecallComposer(IPassiveSubjectiveRecallComposer):
    """`ISubjectiveEpisodeStore` を走査し、ルールで user 向け想起ブロックを返す。"""

    def __init__(
        self,
        *,
        subjective_episode_store: ISubjectiveEpisodeStore,
        max_scan: int = 120,
        max_hits: int = 3,
        min_score: float = 26.0,
        max_situation_chars: int = 8000,
    ) -> None:
        if not isinstance(subjective_episode_store, ISubjectiveEpisodeStore):
            raise TypeError("subjective_episode_store must be ISubjectiveEpisodeStore")
        if max_scan < 1:
            raise ValueError("max_scan must be >= 1")
        if max_hits < 1:
            raise ValueError("max_hits must be >= 1")
        if max_situation_chars < 1:
            raise ValueError("max_situation_chars must be >= 1")
        self._store = subjective_episode_store
        self._max_scan = max_scan
        self._max_hits = max_hits
        self._min_score = min_score
        self._max_situation_chars = max_situation_chars

    def compose_user_block(
        self,
        player_id: PlayerId,
        *,
        situation_text: str,
        current_goals_hint: str,
    ) -> PassiveRecallComposeResult:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(situation_text, str):
            raise TypeError("situation_text must be str")
        if not isinstance(current_goals_hint, str):
            raise TypeError("current_goals_hint must be str")
        trimmed = situation_text[: self._max_situation_chars]
        goal_tokens = _tokenize_cues(current_goals_hint)
        now = datetime.now()
        episodes = self._store.list_recent(player_id, self._max_scan)
        if not episodes:
            return PassiveRecallComposeResult(user_block="")
        scored: List[Tuple[float, SubjectiveEpisode]] = []
        for ep in episodes:
            s = score_episode_for_recall(
                ep,
                situation_text=trimmed,
                goal_tokens=goal_tokens,
                now=now,
            )
            if s >= self._min_score:
                scored.append((s, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        picked = [ep for _, ep in scored[: self._max_hits]]
        if not picked:
            return PassiveRecallComposeResult(user_block="")
        lines: List[str] = []
        episode_ids: List[str] = []
        for ep in picked:
            line = _format_recall_line(ep)
            if line:
                lines.append(line)
            episode_ids.append(ep.episode_id)
            self._store.record_passive_recall(player_id, ep.episode_id)
        if not lines:
            return PassiveRecallComposeResult(user_block="")
        body = "\n".join(f"- {ln}" for ln in lines)
        return PassiveRecallComposeResult(
            user_block=f"{_RECALL_HEADER}\n{body}",
            episode_ids_for_reflection=tuple(episode_ids),
        )
