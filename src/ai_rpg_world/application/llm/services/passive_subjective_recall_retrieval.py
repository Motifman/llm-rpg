"""P3: Passive Subjective Recall 用の軸別スコアの合成（temporal / cue / importance / goal）。

`PassiveSubjectiveRecallComposer` から切り出し、テストと説明可能性（どの軸が効いたか）を
取りやすくする。cue 軸は `subjective_episode_index_strings` と状況文の交差を数える。
importance 軸は `SubjectiveEpisode.importance` から段階ボーナス。
goal 軸は目標ヒントのトークンが observed/interpreted に含まれる件数×重み。
`axis:value` 形（P2 の `to_canonical`）は、値部分が状況文またはトークンに含まれれば一致とみなす。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Set

from ai_rpg_world.application.llm.contracts.dtos import (
    SubjectiveEpisode,
    subjective_episode_index_strings,
)


def tokenize_passive_recall_text(text: str) -> Set[str]:
    """目標文・状況文から単語トークンを取り出す（ASCII 識別子・日本語連続）。"""
    if not text.strip():
        return set()
    text_l = text.lower()
    parts = re.findall(r"[a-z0-9_]{2,}|[\u3040-\u30ff\u4e00-\u9fff]+", text_l)
    return {p for p in parts if p}


def episode_index_key_matches_situation(
    key_norm: str,
    *,
    situation_lower: str,
    situation_tokens: Set[str],
) -> bool:
    """正規化済み（lower）の 1 索引キーが、状況文に現れるとみなせるか。"""
    if not key_norm:
        return False
    if key_norm in situation_lower:
        return True
    if ":" in key_norm:
        _, _, rest = key_norm.partition(":")
        val = rest.strip()
        if val and (val in situation_lower or val in situation_tokens):
            return True
        return False
    return False


def count_cue_axis_hits(ep: SubjectiveEpisode, *, situation_text: str) -> int:
    """エピソードの索引キー列と状況文の一致本数（重複キーは 1 回ずつ）。"""
    trimmed = situation_text.strip()
    if not trimmed:
        return 0
    blob = trimmed.lower()
    tokens = tokenize_passive_recall_text(trimmed)
    n = 0
    seen: Set[str] = set()
    for raw in subjective_episode_index_strings(ep):
        k = raw.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        if episode_index_key_matches_situation(
            k, situation_lower=blob, situation_tokens=tokens
        ):
            n += 1
    return n


def temporal_recency_bonus(ep: SubjectiveEpisode, *, now: datetime) -> float:
    """直近ほど高いボーナス（時間ベース temporal 軸）。"""
    delta = (now - ep.created_at).total_seconds() / 3600.0
    if delta < 0:
        delta = 0.0
    return max(0.0, 18.0 - min(delta, 18.0))


def temporal_list_position_bonus(*, list_index: int, max_scan: int) -> float:
    """`list_recent` の順序に基づく小さな temporal 補正（若い index ほど新しい想定）。"""
    if max_scan < 1 or list_index < 0:
        return 0.0
    return float(max_scan - list_index) / float(max_scan) * 3.0


def importance_bonus(ep: SubjectiveEpisode) -> int:
    if ep.importance == "high":
        return 28
    if ep.importance == "medium":
        return 12
    return 0


def goal_axis_overlap_score(ep: SubjectiveEpisode, goal_tokens: Set[str]) -> int:
    """目標ヒントとエピソード本文の語レベル一致（goal 軸）。将来的に goal: 接頭辞へ寄せる。"""
    if not goal_tokens:
        return 0
    blob = f"{ep.observed}\n{ep.interpreted}".lower()
    return sum(8 for t in goal_tokens if t in blob)


@dataclass(frozen=True)
class PassiveRecallScoreBreakdown:
    """デバッグ・説明用の軸別寄与。"""

    total: float
    temporal_recency: float
    temporal_list_position: float
    cue_hits: int
    cue_weighted: float
    importance: int
    goal_weighted: float


def compute_passive_recall_score_breakdown(
    ep: SubjectiveEpisode,
    *,
    situation_text: str,
    goal_tokens: Set[str],
    now: datetime,
    list_index: int,
    max_scan: int,
    cue_hit_weight: float = 44.0,
) -> PassiveRecallScoreBreakdown:
    """軸別に分解したスコア。total は composer のしきい値 `min_score` と互換のスケール。"""
    tr = temporal_recency_bonus(ep, now=now)
    tl = temporal_list_position_bonus(list_index=list_index, max_scan=max_scan)
    cue_hits = count_cue_axis_hits(ep, situation_text=situation_text)
    cw = float(cue_hits) * cue_hit_weight
    imp = importance_bonus(ep)
    gw = float(goal_axis_overlap_score(ep, goal_tokens))
    total = cw + float(imp) + tr + tl + gw
    return PassiveRecallScoreBreakdown(
        total=total,
        temporal_recency=tr,
        temporal_list_position=tl,
        cue_hits=cue_hits,
        cue_weighted=cw,
        importance=imp,
        goal_weighted=gw,
    )
