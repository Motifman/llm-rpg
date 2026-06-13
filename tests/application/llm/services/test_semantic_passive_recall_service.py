"""``SemanticPassiveRecallService`` のスコアリングと top-K テスト (Phase 1c)。

score = α * recency + β * importance + γ * relevance のランキング挙動と、
top_k = 0 / 空 store などの境界を検証する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
    DEFAULT_RECENCY_TAU_SEC,
    SemanticPassiveRecallService,
    SemanticRecallCandidate,
    format_semantic_recall_section,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _entry(
    *,
    entry_id: str,
    text: str = "なにかの学び",
    importance_score: int = 5,
    tags: tuple = (),
    created_at: datetime = _NOW,
    confidence: float = 0.6,
    evidence: tuple = ("ep-1",),
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=1,
        text=text,
        evidence_episode_ids=evidence,
        confidence=confidence,
        created_at=created_at,
        importance_score=importance_score,
        tags=tags,
    )


def _cue(value: str) -> EpisodicCue:
    return EpisodicCue(
        axis="place_spot", value=value, source=EpisodicCueSource.RUNTIME_CONTEXT
    )


# ──────────────────────────────────────────────────────────────────
# Boundaries: top_k / empty / disabled
# ──────────────────────────────────────────────────────────────────


class TestSemanticPassiveRecallBoundaries:
    """top_k と空入力の境界。"""

    def test_top_k_が_0_なら_空_list(self) -> None:
        """disabled 経路: top_k <= 0 で必ず空。"""
        store = InMemorySemanticMemoryStore()
        store.add(_entry(entry_id="s1"))
        svc = SemanticPassiveRecallService(store)
        assert svc.retrieve(player_id=1, situation_cues=(), top_k=0, now=_NOW) == []

    def test_top_k_が_負数_なら_空_list(self) -> None:
        store = InMemorySemanticMemoryStore()
        store.add(_entry(entry_id="s1"))
        svc = SemanticPassiveRecallService(store)
        assert svc.retrieve(player_id=1, situation_cues=(), top_k=-3, now=_NOW) == []

    def test_store_が_空_なら_空_list(self) -> None:
        svc = SemanticPassiveRecallService(InMemorySemanticMemoryStore())
        assert svc.retrieve(player_id=1, situation_cues=(_cue("3"),), top_k=5, now=_NOW) == []

    def test_top_k_が_候補数_より大きい場合_存在数だけ_返す(self) -> None:
        store = InMemorySemanticMemoryStore()
        for i in range(3):
            store.add(_entry(entry_id=f"s{i}", text=f"t{i}"))
        svc = SemanticPassiveRecallService(store)
        result = svc.retrieve(player_id=1, situation_cues=(), top_k=10, now=_NOW)
        assert len(result) == 3


# ──────────────────────────────────────────────────────────────────
# Scoring components
# ──────────────────────────────────────────────────────────────────


class TestSemanticPassiveRecallScoring:
    """recency / importance / relevance の各成分が独立に効く。"""

    def test_新しい_entry_の_方が_recency_が_高く_top_に来る(self) -> None:
        """importance が同点なら作成が新しいほうが上位。"""
        store = InMemorySemanticMemoryStore()
        store.add(_entry(entry_id="old", created_at=_NOW - timedelta(days=180)))
        store.add(_entry(entry_id="new", created_at=_NOW))
        svc = SemanticPassiveRecallService(store)
        result = svc.retrieve(player_id=1, situation_cues=(), top_k=2, now=_NOW)
        assert result[0].entry.entry_id == "new"

    def test_importance_score_が_高い_entry_が_上位(self) -> None:
        """recency / relevance が同点なら importance が分ける。"""
        store = InMemorySemanticMemoryStore()
        store.add(_entry(entry_id="low", importance_score=2))
        store.add(_entry(entry_id="high", importance_score=9))
        svc = SemanticPassiveRecallService(store)
        result = svc.retrieve(player_id=1, situation_cues=(), top_k=2, now=_NOW)
        assert result[0].entry.entry_id == "high"

    def test_cue_が_tag_と一致する_entry_が_relevance_で_上位(self) -> None:
        """tag マッチがあれば relevance>0 で順位に反映される。"""
        store = InMemorySemanticMemoryStore()
        store.add(_entry(entry_id="no_tag", tags=()))
        store.add(_entry(entry_id="match", tags=("3",)))
        svc = SemanticPassiveRecallService(store)
        result = svc.retrieve(
            player_id=1, situation_cues=(_cue("3"),), top_k=2, now=_NOW
        )
        assert result[0].entry.entry_id == "match"
        assert result[0].relevance > 0
        assert result[1].relevance == 0

    def test_cue_が_本文に_含まれていれば_relevance_に_寄与(self) -> None:
        """tag に無くても text に含まれていれば cheap lexical match で hit。"""
        store = InMemorySemanticMemoryStore()
        store.add(_entry(entry_id="text_match", text="北の洞窟は危険", tags=()))
        store.add(_entry(entry_id="other", text="海は穏やか", tags=()))
        svc = SemanticPassiveRecallService(store)
        result = svc.retrieve(
            player_id=1, situation_cues=(_cue("北の洞窟"),), top_k=2, now=_NOW
        )
        assert result[0].entry.entry_id == "text_match"

    def test_cue_未指定_なら_relevance_は_全件_0(self) -> None:
        store = InMemorySemanticMemoryStore()
        store.add(_entry(entry_id="x", tags=("anything",)))
        svc = SemanticPassiveRecallService(store)
        result = svc.retrieve(player_id=1, situation_cues=(), top_k=1, now=_NOW)
        assert result[0].relevance == 0.0

    def test_clock_skew_で_未来の_entry_でも_recency_は_1_0_でクランプ(self) -> None:
        """now より後の created_at でも score は崩れず recency=1.0。"""
        store = InMemorySemanticMemoryStore()
        future = _NOW + timedelta(days=1)
        store.add(_entry(entry_id="future", created_at=future))
        svc = SemanticPassiveRecallService(store)
        result = svc.retrieve(player_id=1, situation_cues=(), top_k=1, now=_NOW)
        assert result[0].recency == pytest.approx(1.0)


# ──────────────────────────────────────────────────────────────────
# Trace payload + section formatting
# ──────────────────────────────────────────────────────────────────


class TestSemanticRecallCandidateTracePayload:
    """trace event 用 dict が必要なフィールドを持つ。"""

    def test_to_trace_payload_が_必要キーを_含む(self) -> None:
        entry = _entry(
            entry_id="sem-1",
            text="タカシは信頼できる",
            importance_score=8,
            tags=("タカシ", "信頼"),
        )
        cand = SemanticRecallCandidate(
            entry=entry, score=2.5, recency=1.0, importance=0.8, relevance=0.7
        )
        p = cand.to_trace_payload()
        assert p["entry_id"] == "sem-1"
        assert p["score"] == pytest.approx(2.5)
        assert p["importance"] == pytest.approx(0.8)
        assert p["recency"] == pytest.approx(1.0)
        assert p["relevance"] == pytest.approx(0.7)
        assert p["text_snippet"] == "タカシは信頼できる"
        assert p["tags"] == ["タカシ", "信頼"]
        assert p["importance_score"] == 8


class TestFormatSemanticRecallSection:
    """prompt 用 §「【関連する学び】」の本文整形。"""

    def test_候補ゼロなら_空文字(self) -> None:
        assert format_semantic_recall_section([]) == ""

    def test_候補が_箇条書きで_並ぶ(self) -> None:
        entries = [
            SemanticRecallCandidate(
                entry=_entry(entry_id=f"s{i}", text=f"学び{i}"),
                score=1.0 - i * 0.1,
                recency=0.5,
                importance=0.5,
                relevance=0.0,
            )
            for i in range(3)
        ]
        text = format_semantic_recall_section(entries)
        assert text.splitlines() == ["- 学び0", "- 学び1", "- 学び2"]
