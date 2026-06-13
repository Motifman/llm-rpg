"""想起後再解釈 buffer / journal / coordinator の検証。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import EpisodicReinterpretationEntry
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import IEpisodicRecallBufferStore
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
    EpisodicReinterpretationCoordinator,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _FakeReinterpretationPort(IEpisodicReinterpretationCompletionPort):
    def __init__(self, outcome: dict[str, Any] | BaseException) -> None:
        self.outcome = outcome
        self.calls: list[list[dict[str, Any]]] = []

    def complete_episodic_reinterpretation_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(messages)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _BrokenRecallBufferStore(IEpisodicRecallBufferStore):
    def append(self, observation: EpisodicRecallObservation) -> None:
        raise RuntimeError("broken")

    def peek_batch(
        self,
        player_id: int,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        raise RuntimeError("broken")

    def mark_processed(self, player_id: int, recall_ids: tuple[str, ...]) -> None:
        raise RuntimeError("broken")

    def pending_count(self, player_id: int) -> int:
        raise RuntimeError("broken")


def _episode(
    *,
    episode_id: str,
    player_id: int = 7,
    recall_text: str = "初期の一人称回想。",
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=datetime(2026, 5, 4, 1, 0, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-a",)),
        location=EpisodeLocation(spot_id=10),
        action=EpisodeAction(tool_name="world_no_op"),
        who=("player:self",),
        what="古い扉を調べた",
        why=None,
        observed="古い扉は固く閉ざされていた。",
        expected=None,
        outcome="未解決",
        prediction_error=None,
        felt="caution",
        interpreted="閉ざされた場所だと思った。",
        cues=(
            EpisodicCue(
                axis="place_spot",
                value="10",
                source=EpisodicCueSource.RUNTIME_CONTEXT,
            ),
        ),
        recall_text=recall_text,
    )


def _recall(
    *,
    recall_id: str,
    episode_id: str,
    at: datetime,
    turn_index: int,
    player_id: int = 7,
) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=player_id,
        episode_id=episode_id,
        recalled_at=at,
        source_axes=("temporal",),
        current_state_snapshot="現在地: 古い廊下",
        recent_events_snapshot="扉の前で立ち止まった。",
        persona_snapshot="一人称: 私",
        situation_cues=("place_spot:10",),
        turn_index=turn_index,
    )


class TestInMemoryEpisodicRecallBufferStore:
    """想起 observation を episode 単位で束ねる。"""

    def test_peek_batch_deduplicates_episode_and_caps_contexts(self) -> None:
        """同じ episode の想起は 1 episode として数え、contexts は上限で切る。"""
        base = datetime(2026, 5, 4, tzinfo=timezone.utc)
        store = InMemoryEpisodicRecallBufferStore()
        for i in range(5):
            store.append(
                _recall(
                    recall_id=f"r{i}",
                    episode_id="ep-a",
                    at=base + timedelta(minutes=i),
                    turn_index=i,
                )
            )
        store.append(
            _recall(
                recall_id="r-b",
                episode_id="ep-b",
                at=base + timedelta(minutes=10),
                turn_index=10,
            )
        )
        batch = store.peek_batch(7, batch_size=1, max_contexts_per_episode=3)
        assert [r.recall_id for r in batch] == ["r0", "r1", "r2"]
        assert store.pending_count(7) == 6


class TestInMemoryEpisodicReinterpretationJournalStore:
    """active entry だけが通常参照に残る。"""

    def test_put_active_supersedes_previous_active_entry(self) -> None:
        """新 active 保存時に旧 active は superseded となり get_active から外れる。"""
        store = InMemoryEpisodicReinterpretationJournalStore()
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        first = EpisodicReinterpretationEntry(
            entry_id="j1",
            player_id=7,
            episode_id="ep-a",
            created_at=t0,
            turn_index=1,
            current_interpretation="古い意味。",
            current_recall_text="古い回想。",
            source_recall_ids=("r1",),
        )
        second = EpisodicReinterpretationEntry(
            entry_id="j2",
            player_id=7,
            episode_id="ep-a",
            created_at=t0 + timedelta(minutes=1),
            turn_index=2,
            current_interpretation="新しい意味。",
            current_recall_text="新しい回想。",
            source_recall_ids=("r2",),
        )
        store.put_active(first)
        store.put_active(second)
        assert store.get_active(7, "ep-a") == second
        history = store.list_by_episode(7, "ep-a")
        assert [e.entry_id for e in history] == ["j2", "j1"]
        assert history[1].status.value == "superseded"


class TestEpisodicReinterpretationCoordinator:
    """10 ターンごとの flush と失敗時 pending 維持。"""

    def _stores(self) -> tuple[
        IEpisodicEpisodeStore,
        InMemoryEpisodicRecallBufferStore,
        InMemoryEpisodicReinterpretationJournalStore,
    ]:
        episodes = InMemorySubjectiveEpisodeStore()
        episodes.put(_episode(episode_id="ep-a"))
        episodes.put(_episode(episode_id="ep-b"))
        return (
            episodes,
            InMemoryEpisodicRecallBufferStore(),
            InMemoryEpisodicReinterpretationJournalStore(),
        )

    def test_after_turn_completed_flushes_only_on_tenth_turn(self) -> None:
        """9 ターン目までは LLM を呼ばず、10 ターン目で active entry を保存する。"""
        episodes, buffer, journal = self._stores()
        buffer.append(
            _recall(
                recall_id="r1",
                episode_id="ep-a",
                at=datetime(2026, 5, 4, tzinfo=timezone.utc),
                turn_index=0,
            )
        )
        port = _FakeReinterpretationPort(
            {
                "episode_updates": [
                    {
                        "episode_id": "ep-a",
                        "current_interpretation": "今なら、この扉は単なる障害ではなく合図に見える。",
                        "current_recall_text": "私はあの古い扉の前で、ただ立ち止まっていたわけではない。冷たい取っ手に触れたとき、閉ざされた先に何かが待つ気配を感じ、慎重になった。今思えば、その重さは道を拒む壁ではなく、私に準備を促す合図だったのだと思う。",
                    }
                ]
            }
        )
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=10,
        )
        for _ in range(9):
            coord.after_turn_completed(PlayerId(7))
        assert port.calls == []
        assert journal.get_active(7, "ep-a") is None
        coord.after_turn_completed(PlayerId(7))
        assert len(port.calls) == 1
        active = journal.get_active(7, "ep-a")
        assert active is not None
        assert "合図" in active.current_interpretation
        assert buffer.pending_count(7) == 0

    def test_llm_failure_keeps_pending_recall_and_existing_active(self) -> None:
        """LLM 失敗時は pending を消さず、既存 active entry も保持する。"""
        episodes, buffer, journal = self._stores()
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        buffer.append(_recall(recall_id="r1", episode_id="ep-a", at=t0, turn_index=0))
        old = EpisodicReinterpretationEntry(
            entry_id="old",
            player_id=7,
            episode_id="ep-a",
            created_at=t0,
            turn_index=0,
            current_interpretation="既存の意味。",
            current_recall_text="既存の回想。",
            source_recall_ids=("r0",),
        )
        journal.put_active(old)
        port = _FakeReinterpretationPort(
            LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")
        )
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=1,
        )
        coord.after_turn_completed(PlayerId(7))
        assert buffer.pending_count(7) == 1
        assert journal.get_active(7, "ep-a") == old

    def test_invalid_llm_json_keeps_pending_recall(self) -> None:
        """JSON shape 不正や必須 field 欠落では pending を消さず retry 可能にする。"""
        episodes, buffer, journal = self._stores()
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        buffer.append(_recall(recall_id="r1", episode_id="ep-a", at=t0, turn_index=0))
        port = _FakeReinterpretationPort({"episode_updates": []})
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=1,
        )
        assert coord.flush_player(PlayerId(7)) == 0
        assert buffer.pending_count(7) == 1
        assert journal.get_active(7, "ep-a") is None

    def test_partial_llm_updates_mark_only_successful_episode_recalls_processed(self) -> None:
        """batch の一部だけ成功したら、成功 episode の recall_id だけ pending から除く。"""
        episodes, buffer, journal = self._stores()
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        buffer.append(_recall(recall_id="r-a", episode_id="ep-a", at=t0, turn_index=0))
        buffer.append(
            _recall(
                recall_id="r-b",
                episode_id="ep-b",
                at=t0 + timedelta(minutes=1),
                turn_index=1,
            )
        )
        port = _FakeReinterpretationPort(
            {
                "episode_updates": [
                    {
                        "episode_id": "ep-a",
                        "current_interpretation": "ep-a だけ成功。",
                        "current_recall_text": "私は ep-a の出来事だけを、今の文脈から改めて思い返した。",
                    }
                ]
            }
        )
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=1,
        )
        assert coord.flush_player(PlayerId(7)) == 1
        assert journal.get_active(7, "ep-a") is not None
        pending = buffer.peek_batch(7, batch_size=8, max_contexts_per_episode=3)
        assert [row.recall_id for row in pending] == ["r-b"]

    def test_after_turn_completed_does_not_propagate_sidecar_store_failure(self) -> None:
        """再解釈 sidecar の store 例外は本体ターンへ伝播させない。"""
        episodes = InMemorySubjectiveEpisodeStore()
        episodes.put(_episode(episode_id="ep-a"))
        journal = InMemoryEpisodicReinterpretationJournalStore()
        port = _FakeReinterpretationPort({"episode_updates": []})
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=_BrokenRecallBufferStore(),
            journal_store=journal,
            completion=port,
            turn_interval=1,
        )
        coord.after_turn_completed(PlayerId(7))
