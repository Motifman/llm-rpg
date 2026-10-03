"""想起の記録が、確定して外れた予期のずれを、思い出していたエピソードの想起に出来事ごと 1 回だけ書き添える挙動を、全実装で保証する。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import (
    EpisodicRecallBufferRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.infrastructure.repository.sqlite_episodic_reinterpretation_store import (
    SqliteEpisodicReinterpretationStore,
)

BEING = BeingId("being-rio")
MISS = "たぶんと思っていた予期「干潟で貝が採れる」は外れた。"


def _in_memory() -> EpisodicRecallBufferRepository:
    return InMemoryEpisodicRecallBufferStore()


def _sqlite() -> EpisodicRecallBufferRepository:
    return SqliteEpisodicReinterpretationStore(sqlite3.connect(":memory:"))


STORES: list[Callable[[], EpisodicRecallBufferRepository]] = [_in_memory, _sqlite]


def _recall(
    recall_id: str, episode_id: str, *, stamped: str | None = None
) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=1,
        episode_id=episode_id,
        recalled_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        source_axes=("temporal",),
        current_state_snapshot="干潟",
        recent_events_snapshot="潮が引いた",
        persona_snapshot="リオ",
        situation_cues=(),
        turn_index=1,
        prediction_outcome_error=stamped,
    )


def _errors(store: EpisodicRecallBufferRepository) -> dict[str, str | None]:
    return {
        o.recall_id: o.prediction_outcome_error
        for o in store.list_pending_by_being(BEING)
    }


@pytest.mark.parametrize("make_store", STORES)
class TestStampForEpisodes:
    """``stamp_prediction_outcome_for_episodes_by_being`` の書き添えと受け取り済みの記録を保証する。"""

    def test_stamps_pending_recalls_of_episodes_in_mind_only(
        self, make_store: Callable[[], EpisodicRecallBufferRepository]
    ) -> None:
        """思い出していたエピソードの、まだ書き添えの無い想起だけにずれを書き、書いた想起の件数を返す。"""
        store = make_store()
        store.append_by_being(BEING, _recall("r-1", "ep-shore"))
        store.append_by_being(BEING, _recall("r-2", "ep-other"))
        store.append_by_being(BEING, _recall("r-3", "ep-shore", stamped="前のずれ"))

        stamped = store.stamp_prediction_outcome_for_episodes_by_being(
            BEING, ("ep-shore",), MISS, event_id="exp-1@5"
        )

        assert stamped == 1
        assert _errors(store) == {"r-1": MISS, "r-2": None, "r-3": "前のずれ"}
        assert store.list_received_event_ids_by_being(BEING) == ["exp-1@5"]

    def test_same_event_id_twice_does_not_stamp_later_recalls(
        self, make_store: Callable[[], EpisodicRecallBufferRepository]
    ) -> None:
        """同じ出来事の ID を二度受け取ると、間に増えた想起には書き添えず、None を返す。"""
        store = make_store()
        store.append_by_being(BEING, _recall("r-1", "ep-shore"))
        store.stamp_prediction_outcome_for_episodes_by_being(
            BEING, ("ep-shore",), MISS, event_id="exp-1@5"
        )
        store.append_by_being(BEING, _recall("r-4", "ep-shore"))

        stamped = store.stamp_prediction_outcome_for_episodes_by_being(
            BEING, ("ep-shore",), MISS, event_id="exp-1@5"
        )

        assert stamped is None
        assert _errors(store)["r-4"] is None

    def test_replace_received_event_ids_restores_receipts(
        self, make_store: Callable[[], EpisodicRecallBufferRepository]
    ) -> None:
        """snapshot から受け取り済みの ID を戻すと、その出来事ではもう書き添えない。"""
        store = make_store()
        store.append_by_being(BEING, _recall("r-1", "ep-shore"))

        store.replace_received_event_ids_by_being(BEING, ["exp-1@5"])

        assert store.list_received_event_ids_by_being(BEING) == ["exp-1@5"]
        assert (
            store.stamp_prediction_outcome_for_episodes_by_being(
                BEING, ("ep-shore",), MISS, event_id="exp-1@5"
            )
            is None
        )
        assert _errors(store)["r-1"] is None

    def test_no_pending_recall_returns_zero_and_still_records_receipt(
        self, make_store: Callable[[], EpisodicRecallBufferRepository]
    ) -> None:
        """書き添える想起が残っていなければ 0 を返し、出来事の ID は受け取り済みにする。"""
        store = make_store()

        stamped = store.stamp_prediction_outcome_for_episodes_by_being(
            BEING, ("ep-shore",), MISS, event_id="exp-1@5"
        )

        assert stamped == 0
        assert store.list_received_event_ids_by_being(BEING) == ["exp-1@5"]
