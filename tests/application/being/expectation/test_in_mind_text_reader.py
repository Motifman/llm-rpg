"""MemoryStoreInMindTextReader が、プロンプトの想起と同じ store から頭にあった信念とエピソードの本文を引く挙動を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.expectation.grounds import (
    InMindStoreUnwired,
    MemoryStoreInMindTextReader,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)

RIO = BeingId("being-rio")
NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def _episode(episode_id: str, *, recall_text: str | None, what: str = "トムが麦束を焼いた") -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=1,
        being_id=RIO,
        occurred_at=NOW,
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=1),
        action=EpisodeAction(tool_name="speak"),
        who=("トム",),
        what=what,
        why=None,
        observed="浜",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
        recall_text=recall_text,
    )


def _reader(
    *, with_journal: bool = True
) -> tuple[
    MemoryStoreInMindTextReader,
    InMemorySemanticMemoryStore,
    InMemorySubjectiveEpisodeStore,
    InMemoryEpisodicReinterpretationJournalStore,
]:
    semantic = InMemorySemanticMemoryStore()
    episodes = InMemorySubjectiveEpisodeStore()
    journal = InMemoryEpisodicReinterpretationJournalStore()
    reader = MemoryStoreInMindTextReader(
        semantic_store=semantic,
        episode_store=episodes,
        journal_store=journal if with_journal else None,
    )
    return reader, semantic, episodes, journal


class TestBeliefText:
    """信念は、プロンプトの台帳に載る entry_id で本文を引く挙動を保証する。"""

    def test_reads_text_by_entry_id(self) -> None:
        """台帳に載った entry_id の信念の本文を返す。"""
        reader, semantic, _, _ = _reader()
        semantic.add_by_being(
            RIO,
            SemanticMemoryEntry(
                entry_id="sem-1",
                player_id=1,
                being_id=RIO,
                text="トムは頼めば麦束を焼いてくれる",
                evidence_episode_ids=(),
                confidence=0.6,
                created_at=NOW,
            ),
        )

        assert reader.belief_text(RIO, "sem-1") == "トムは頼めば麦束を焼いてくれる"

    def test_unknown_belief_returns_none(self) -> None:
        """見つからない信念は None を返す。"""
        reader, _, _, _ = _reader()

        assert reader.belief_text(RIO, "sem-unknown") is None

    def test_missing_store_raises_instead_of_reporting_not_found(self) -> None:
        """信念やエピソードの store が無いときは、ID が見つからないのと区別できるよう InMindStoreUnwired を投げる。"""
        no_store = MemoryStoreInMindTextReader(
            semantic_store=None, episode_store=None, journal_store=None
        )

        with pytest.raises(InMindStoreUnwired, match="semantic"):
            no_store.belief_text(RIO, "sem-1")
        with pytest.raises(InMindStoreUnwired, match="episode"):
            no_store.episode_text(RIO, "ep-1")


class TestEpisodeText:
    """エピソードは、プロンプトの想起と同じく再解釈を優先して本文を引く挙動を保証する。"""

    def test_active_reinterpretation_is_preferred_over_recall_text(self) -> None:
        """有効な再解釈があれば、元の想起文ではなく再解釈の文を返す。"""
        reader, _, episodes, journal = _reader()
        episodes.put_by_being(RIO, _episode("ep-1", recall_text="トムが麦束を焼いた"))
        journal.put_active_by_being(
            RIO,
            EpisodicReinterpretationEntry(
                entry_id="j-1",
                player_id=1,
                being_id=RIO,
                episode_id="ep-1",
                created_at=NOW,
                turn_index=3,
                current_interpretation="トムは親切だ",
                current_recall_text="トムが焼きたての麦束を分けてくれた",
                source_recall_ids=("r-1",),
            ),
        )

        assert reader.episode_text(RIO, "ep-1") == "トムが焼きたての麦束を分けてくれた"

    def test_recall_text_is_preferred_over_what_without_reinterpretation(self) -> None:
        """再解釈が無ければ、出来事の要約ではなく想起文を返す。"""
        reader, _, episodes, _ = _reader()
        episodes.put_by_being(RIO, _episode("ep-1", recall_text="浜でトムに麦束をもらった"))

        assert reader.episode_text(RIO, "ep-1") == "浜でトムに麦束をもらった"

    def test_what_is_used_when_recall_text_is_missing(self) -> None:
        """再解釈も想起文も無ければ、出来事の要約を返す。"""
        reader, _, episodes, _ = _reader()
        episodes.put_by_being(RIO, _episode("ep-1", recall_text=None))

        assert reader.episode_text(RIO, "ep-1") == "トムが麦束を焼いた"

    def test_unknown_episode_returns_none(self) -> None:
        """見つからないエピソードは None を返す。"""
        reader, _, _, _ = _reader()

        assert reader.episode_text(RIO, "ep-unknown") is None
