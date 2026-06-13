"""Semantic memory の状況連想 top-K 想起サービス (Phase 1c)。

Generative Agents 風の score = α * recency + β * importance + γ * relevance で
``SemanticMemoryEntry`` をランキングし、上位 K 件を返す。

設計指針:

- **scale する**: semantic store が数千件に増えても prompt に出るのは top_k
  件のみ。docs/memory_system/semantic_memory_activation_plan.md §4 と一致
- **deterministic**: 同 situation_cues / now でランキングは再現可能
- **fail-safe**: cue / entry のどれかが欠けても 0 score で生き残る
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    ISemanticMemoryStore,
)


_logger = logging.getLogger(__name__)


# recency の指数減衰時定数 (秒)。30 日で 1/e 程度になる。
# 短期 (~1 日内) と長期 (~数か月) を区別するのが目的。
DEFAULT_RECENCY_TAU_SEC: float = 30.0 * 24.0 * 3600.0

# 重み (α / β / γ)。Generative Agents は importance を最重視するが、本
# プロジェクトはまだ importance_score の絶対基準が安定していないので等重み
# から始める。実験 #25 後続で実測して調整。
DEFAULT_WEIGHT_RECENCY: float = 1.0
DEFAULT_WEIGHT_IMPORTANCE: float = 1.0
DEFAULT_WEIGHT_RELEVANCE: float = 1.0

# relevance 計算で「最大何件マッチすれば 1.0 とみなすか」。
# 普通の semantic entry は tags 1-4 件なので 3 件マッチで satured と扱う。
RELEVANCE_SATURATION_HITS: int = 3


@dataclass(frozen=True)
class SemanticRecallCandidate:
    """top-K 結果 1 件。score の内訳を残して trace で可視化可能にする。"""

    entry: SemanticMemoryEntry
    score: float
    recency: float
    importance: float
    relevance: float

    def to_trace_payload(self) -> dict:
        """trace event 用の薄い dict (Phase 1c の SEMANTIC_PASSIVE_RECALL)。"""
        return {
            "entry_id": self.entry.entry_id,
            "score": round(self.score, 4),
            "recency": round(self.recency, 4),
            "importance": round(self.importance, 4),
            "relevance": round(self.relevance, 4),
            "text_snippet": (self.entry.text or "")[:60],
            "tags": list(self.entry.tags),
            "importance_score": self.entry.importance_score,
        }


class SemanticPassiveRecallService:
    """状況連想で semantic store から top-K を取り出す。

    呼出側は ``retrieve(player_id, situation_cues, top_k, now)`` で list を
    受け取り、prompt に整形する。top_k <= 0 なら空 list を返す (= disable)。
    """

    def __init__(
        self,
        semantic_store: ISemanticMemoryStore,
        *,
        recency_tau_sec: float = DEFAULT_RECENCY_TAU_SEC,
        weight_recency: float = DEFAULT_WEIGHT_RECENCY,
        weight_importance: float = DEFAULT_WEIGHT_IMPORTANCE,
        weight_relevance: float = DEFAULT_WEIGHT_RELEVANCE,
    ) -> None:
        if semantic_store is None:
            raise TypeError("semantic_store must not be None")
        if recency_tau_sec <= 0:
            raise ValueError("recency_tau_sec must be positive")
        self._store = semantic_store
        self._tau = recency_tau_sec
        self._w_rec = weight_recency
        self._w_imp = weight_importance
        self._w_rel = weight_relevance

    def retrieve(
        self,
        *,
        player_id: int,
        situation_cues: Sequence[EpisodicCue],
        top_k: int,
        now: datetime | None = None,
    ) -> list[SemanticRecallCandidate]:
        """player の semantic store を top_k 件にランキングして返す。

        - top_k <= 0 なら空 list (disable 経路)
        - now=None なら ``datetime.now(tz=utc)``
        - 候補が top_k より少なければ存在数だけ返す
        """
        if top_k <= 0:
            return []
        effective_now = now if now is not None else datetime.now(timezone.utc)
        entries = list(self._store.list_for_player(player_id))
        if not entries:
            return []

        cue_values = self._extract_cue_values(situation_cues)
        ranked: list[SemanticRecallCandidate] = []
        for entry in entries:
            try:
                rec = self._recency(entry, effective_now)
                imp = self._importance(entry)
                rel = self._relevance(entry, cue_values)
                score = (
                    self._w_rec * rec
                    + self._w_imp * imp
                    + self._w_rel * rel
                )
                ranked.append(
                    SemanticRecallCandidate(
                        entry=entry,
                        score=score,
                        recency=rec,
                        importance=imp,
                        relevance=rel,
                    )
                )
            except Exception as e:
                # 個別 entry のスコアリング失敗で全体を倒さない
                _logger.warning(
                    "Failed to score semantic entry %s: %s",
                    getattr(entry, "entry_id", "?"),
                    e,
                )

        # tie-breaker: 同 score なら新しい entry を優先 (created_at 降順)
        ranked.sort(
            key=lambda c: (c.score, c.entry.created_at),
            reverse=True,
        )
        return ranked[:top_k]

    def _recency(self, entry: SemanticMemoryEntry, now: datetime) -> float:
        delta = (now - entry.created_at).total_seconds()
        if delta < 0:
            delta = 0.0  # clock skew で entry が未来になっても 1.0
        return math.exp(-delta / self._tau)

    def _importance(self, entry: SemanticMemoryEntry) -> float:
        # importance_score は 1-10 で保証されている。正規化して [0.1, 1.0]
        return float(entry.importance_score) / 10.0

    def _relevance(self, entry: SemanticMemoryEntry, cue_values: frozenset[str]) -> float:
        if not cue_values:
            return 0.0
        # tag マッチ + 本文中の cue 文字列出現を見る (cheap な lexical match)。
        # 将来 embedding に置き換える余地あり。
        hits = 0
        for cue_val in cue_values:
            if not cue_val:
                continue
            if any(cue_val == tag for tag in entry.tags):
                hits += 1
                continue
            if cue_val in entry.text:
                hits += 1
        if hits == 0:
            return 0.0
        return min(hits / RELEVANCE_SATURATION_HITS, 1.0)

    @staticmethod
    def _extract_cue_values(situation_cues: Sequence[EpisodicCue]) -> frozenset[str]:
        values: set[str] = set()
        for cue in situation_cues or ():
            try:
                if cue.value:
                    values.add(cue.value)
            except Exception:
                continue
        return frozenset(values)


def format_semantic_recall_section(
    candidates: Sequence[SemanticRecallCandidate],
) -> str:
    """prompt § "【関連する学び】" の本体を組み立てる。

    候補ゼロなら空文字 (= section ごと省略される)。
    """
    if not candidates:
        return ""
    lines: list[str] = []
    for cand in candidates:
        text = (cand.entry.text or "").strip()
        if not text:
            continue
        lines.append(f"- {text}")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_RECENCY_TAU_SEC",
    "DEFAULT_WEIGHT_IMPORTANCE",
    "DEFAULT_WEIGHT_RECENCY",
    "DEFAULT_WEIGHT_RELEVANCE",
    "SemanticPassiveRecallService",
    "SemanticRecallCandidate",
    "format_semantic_recall_section",
]
