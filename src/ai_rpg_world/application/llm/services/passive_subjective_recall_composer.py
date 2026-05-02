"""v2 SubjectiveEpisode 由来の Passive Recall（user ブロック／ルールベースのみ）。

ここで行うのは **想起候補のスコアリングと、保存済み主観文面からの短い要約行の組み立て** に限る。
計画における **Memory Reflection**（想起されたエピソードを、LLM で「いま」の視点から言い換え直す）とは別物で、
後者はプロンプト組み立てのクリティカルパスに載せず、非同期ジョブ等で行う想定。

P3 では temporal / cue / goal の軸別寄与を `passive_subjective_recall_retrieval` に切り出し、
必要時に `pick_debug` で説明可能にする。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    PassiveRecallComposeResult,
    PassiveRecallPickDebug,
    SubjectiveEpisode,
    subjective_episode_index_strings,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IPassiveSubjectiveRecallComposer,
    ISubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.passive_subjective_recall_retrieval import (
    compute_passive_recall_score_breakdown,
    tokenize_passive_recall_text,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_RECALL_HEADER = "【ふと思い出したこと】"


def score_episode_for_recall(
    ep: SubjectiveEpisode,
    *,
    situation_text: str,
    goal_tokens: set[str],
    now: datetime,
) -> float:
    """デバッグ·テスト用に公開したスコア関数（list 位置ボーナスなしで旧呼び出し互換）。"""
    b = compute_passive_recall_score_breakdown(
        ep,
        situation_text=situation_text,
        goal_tokens=goal_tokens,
        now=now,
        list_index=0,
        max_scan=1,
    )
    return b.total - b.temporal_list_position


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
        include_pick_debug: bool = False,
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
        self._include_pick_debug = bool(include_pick_debug)

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
        goal_tokens = tokenize_passive_recall_text(current_goals_hint)
        now = datetime.now()
        episodes = self._store.list_recent(player_id, self._max_scan)
        if not episodes:
            return PassiveRecallComposeResult(user_block="")
        scored: List[Tuple[float, SubjectiveEpisode, PassiveRecallPickDebug]] = []
        for idx, ep in enumerate(episodes):
            breakdown = compute_passive_recall_score_breakdown(
                ep,
                situation_text=trimmed,
                goal_tokens=goal_tokens,
                now=now,
                list_index=idx,
                max_scan=self._max_scan,
            )
            if breakdown.total >= self._min_score:
                dbg = PassiveRecallPickDebug(
                    episode_id=ep.episode_id,
                    total=breakdown.total,
                    temporal_recency=breakdown.temporal_recency,
                    temporal_list_position=breakdown.temporal_list_position,
                    cue_hits=breakdown.cue_hits,
                    cue_weighted=breakdown.cue_weighted,
                    importance=breakdown.importance,
                    goal_weighted=breakdown.goal_weighted,
                )
                scored.append((breakdown.total, ep, dbg))
        scored.sort(key=lambda x: x[0], reverse=True)
        picked = scored[: self._max_hits]
        if not picked:
            return PassiveRecallComposeResult(user_block="")
        lines: List[str] = []
        episode_ids: List[str] = []
        pick_debug_rows: List[PassiveRecallPickDebug] = []
        for _, ep, dbg in picked:
            line = _format_recall_line(ep)
            if line:
                lines.append(line)
            episode_ids.append(ep.episode_id)
            if self._include_pick_debug:
                pick_debug_rows.append(dbg)
            self._store.record_passive_recall(player_id, ep.episode_id)
        if not lines:
            return PassiveRecallComposeResult(user_block="")
        body = "\n".join(f"- {ln}" for ln in lines)
        return PassiveRecallComposeResult(
            user_block=f"{_RECALL_HEADER}\n{body}",
            episode_ids_for_reflection=tuple(episode_ids),
            pick_debug=tuple(pick_debug_rows),
        )
