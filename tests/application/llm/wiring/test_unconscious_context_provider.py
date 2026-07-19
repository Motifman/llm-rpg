"""``build_unconscious_context_provider`` (U7) の belief 整形・cap・縮退挙動を検証する。

provider 自体は ``EpisodicChunkSubjectiveFieldsService`` から独立して単体テスト
できるよう wiring 層の純粋関数として切り出してある。実 semantic store
(``InMemorySemanticMemoryStore`` + ``SemanticPassiveRecallService``) を使い、
「belief 取得は既存の passive recall service を再利用する」設計を保証する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
    SemanticPassiveRecallService,
)
from ai_rpg_world.application.llm.wiring.unconscious_context_provider import (
    DEFAULT_UNCONSCIOUS_CONTEXT_BELIEF_TOP_K,
    build_unconscious_context_provider,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from tests.application.llm._semantic_being_test_helpers import make_semantic_being_setup

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _entry(
    *,
    entry_id: str,
    text: str,
    confidence: float,
    created_at: datetime = _NOW,
    tags: tuple = ("trap",),
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=1,
        text=text,
        evidence_episode_ids=("ep-1",),
        confidence=confidence,
        created_at=created_at,
        tags=tags,
    )


def _cue(value: str = "trap") -> tuple[EpisodicCue, ...]:
    return (EpisodicCue(axis="tag", value=value, source=EpisodicCueSource.RUNTIME_CONTEXT),)


class TestBeliefFormatting:
    def test_belief(self) -> None:
        """belief が確信度付きで箇条書きになる。"""
        setup = make_semantic_being_setup()
        setup.provision(1)
        setup.populate(1, _entry(entry_id="b1", text="チェストはよく罠だ", confidence=0.85))
        svc = SemanticPassiveRecallService(
            setup.semantic_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: svc,
            now_provider=lambda: _NOW,
        )

        text = provider(1, _cue())

        assert text == "- チェストはよく罠だ (確信度: 0.85)"

    def test_belief_empty_string(self) -> None:
        """belief が無ければ空文字。"""
        setup = make_semantic_being_setup()
        setup.provision(1)
        svc = SemanticPassiveRecallService(
            setup.semantic_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: svc,
            now_provider=lambda: _NOW,
        )

        assert provider(1, _cue()) == ""

    def test_semantic_recall_service_none_belief_line_not_rendered_l5_line_rendered(
        self,
    ) -> None:
        """semantic recall service が None なら belief行は出ないが L5行は出る。"""
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: None,
            long_summary_text_provider=lambda pid: "私について: 慎重",
        )

        assert provider(1, _cue()) == "私について: 慎重"


class TestTopKCap:
    def test_belief_top_k_not_rendered(self) -> None:
        """belief は top k 件までしか出ない。"""
        setup = make_semantic_being_setup()
        setup.provision(1)
        for i in range(8):
            setup.populate(
                1,
                _entry(
                    entry_id=f"b{i}",
                    text=f"学び{i}",
                    confidence=0.5,
                    created_at=_NOW - timedelta(seconds=i),
                ),
            )
        svc = SemanticPassiveRecallService(
            setup.semantic_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: svc,
            now_provider=lambda: _NOW,
        )

        text = provider(1, _cue())

        assert len(text.splitlines()) == DEFAULT_UNCONSCIOUS_CONTEXT_BELIEF_TOP_K == 5

    def test_top_k(self) -> None:
        """top k を明示指定できる。"""
        setup = make_semantic_being_setup()
        setup.provision(1)
        for i in range(8):
            setup.populate(
                1,
                _entry(
                    entry_id=f"b{i}",
                    text=f"学び{i}",
                    confidence=0.5,
                    created_at=_NOW - timedelta(seconds=i),
                ),
            )
        svc = SemanticPassiveRecallService(
            setup.semantic_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: svc,
            now_provider=lambda: _NOW,
            top_k=2,
        )

        text = provider(1, _cue())

        assert len(text.splitlines()) == 2

    def test_top_k_zero_raises_value_error(self) -> None:
        """top k が 0以下なら ValueError。"""
        with pytest.raises(ValueError):
            build_unconscious_context_provider(
                semantic_recall_service_provider=lambda: None, top_k=0
            )


class TestL5Appendix:
    def test_l5_last(self) -> None:
        """L5テキストが末尾に足される。"""
        setup = make_semantic_being_setup()
        setup.provision(1)
        setup.populate(1, _entry(entry_id="b1", text="チェストはよく罠だ", confidence=0.5))
        svc = SemanticPassiveRecallService(
            setup.semantic_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: svc,
            long_summary_text_provider=lambda pid: "私について: 慎重\nこの世界について: 罠が多い",
            now_provider=lambda: _NOW,
        )

        text = provider(1, _cue())

        assert text == (
            "- チェストはよく罠だ (確信度: 0.50)\n"
            "私について: 慎重\nこの世界について: 罠が多い"
        )

    def test_returns_l5_line_not_rendered_long_summary_text_provider_empty_string_when(self) -> None:
        """long summary text provider が空文字を返せばL5行は出ない。"""
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: None,
            long_summary_text_provider=lambda pid: "",
        )

        assert provider(1, _cue()) == ""

    def test_long_summary_text_provider_none_l5_line(self) -> None:
        """long summary text provider が None ならL5行を試みない。"""
        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: None,
        )

        assert provider(1, _cue()) == ""


class TestDegradation:
    """belief / L5 取得の失敗は空文字に縮退し、chunk 補完を止めない。"""

    def test_semantic_recall_service_provider_empty_string_raises_exception(self) -> None:
        """semantic recall service provider が例外を投げても空文字。"""
        def _raise() -> None:
            raise RuntimeError("resolver not ready")

        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=_raise,  # type: ignore[arg-type]
        )

        assert provider(1, _cue()) == ""

    def test_retrieve_exception_falls_back_to_empty_string(self) -> None:
        """retrieve が例外を投げても空文字に縮退する。"""
        class _RaisingService:
            def retrieve(self, **kwargs):
                raise RuntimeError("store down")

        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: _RaisingService(),  # type: ignore[arg-type]
        )

        assert provider(1, _cue()) == ""

    def test_long_summary_text_provider_belief_raises_exception(self) -> None:
        """long summary text provider が例外を投げても belief行は出る。"""
        setup = make_semantic_being_setup()
        setup.provision(1)
        setup.populate(1, _entry(entry_id="b1", text="チェストはよく罠だ", confidence=0.5))
        svc = SemanticPassiveRecallService(
            setup.semantic_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )

        def _raising_l5(player_id: int) -> str:
            raise RuntimeError("sliding_window down")

        provider = build_unconscious_context_provider(
            semantic_recall_service_provider=lambda: svc,
            long_summary_text_provider=_raising_l5,
            now_provider=lambda: _NOW,
        )

        text = provider(1, _cue())

        assert text == "- チェストはよく罠だ (確信度: 0.50)"
