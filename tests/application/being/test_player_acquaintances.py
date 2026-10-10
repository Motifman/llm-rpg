from __future__ import annotations

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

ADA = PlayerId(1)
NOA = PlayerId(2)
STRANGER = PlayerId(9)
NAMES = {1: "エイダ", 2: "ノア", 3: "リオ"}


def _being(pid: PlayerId) -> BeingId | None:
    return BeingId(f"being_p{pid.value}") if pid.value in NAMES else None


def _make() -> tuple[PlayerAcquaintances, InMemoryAcquaintanceRepository, InMemoryExpectationRepository]:
    store = InMemoryAcquaintanceRepository()
    turns = InMemoryExpectationRepository()
    acquaintances = PlayerAcquaintances(
        store=store,
        being_id_of=_being,
        turn_reader=turns,
        environment_name="島",
        names_by_player_id=NAMES,
    )
    return acquaintances, store, turns


def _entered(actor: str | None) -> ObservationOutput:
    structured: dict = {"type": "entity_entered_spot", "spot_name": "浜"}
    if actor is not None:
        structured["actor"] = actor
    return ObservationOutput(
        prose=f"{actor or '誰か'}がやってきた。",
        structured=structured,
        observation_category="social",
    )


class TestRecordMeeting:
    """PlayerAcquaintances.record_meeting が、プレイヤーの Being に Being のターン数で会った記録を残すことを保証する。"""

    def test_meeting_is_recorded_in_the_beings_current_turn(self) -> None:
        """会った記録のターンは世界の tick ではなく、その Being の記憶のターン数になる。"""
        acquaintances, store, turns = _make()
        for _ in range(3):
            turns.advance_turn(BeingId("being_p1"))

        acquaintances.record_meeting(ADA, "ノア")

        met = store.find(BeingId("being_p1"), environment_name="島", name="ノア")
        assert met is not None and met.first_met_turn == 3

    def test_player_without_being_records_nothing(self) -> None:
        """Being に結び付かないプレイヤーなら、例外を出さずに何も記録しない。"""
        acquaintances, _, _ = _make()

        acquaintances.record_meeting(STRANGER, "ノア")

        assert acquaintances.find(STRANGER, "ノア") is None

    def test_meeting_oneself_is_not_recorded(self) -> None:
        """自分の名前を相手として渡しても、自分を知り合いとして記録しない。"""
        acquaintances, store, _ = _make()

        acquaintances.record_meeting(ADA, "エイダ")

        assert store.list_by_being(BeingId("being_p1")) == ()


class TestOnObservation:
    """人が入ってきた観測から、受け手と入ってきた人の双方に会った記録を残すことを保証する。"""

    def test_someone_entering_is_met_by_both_sides(self) -> None:
        """ノアが入ってきた観測をエイダが受けると、エイダはノアに、ノアはエイダに会ったことになる。"""
        acquaintances, _, _ = _make()

        acquaintances.on_observation(ADA, _entered("ノア"))

        assert acquaintances.find(ADA, "ノア") is not None
        assert acquaintances.find(NOA, "エイダ") is not None

    def test_hidden_actor_is_not_met(self) -> None:
        """暗がりなどで入ってきた人の名前が伏せられた観測では、誰とも会ったことにしない。"""
        acquaintances, store, _ = _make()

        acquaintances.on_observation(ADA, _entered(None))

        assert store.list_by_being(BeingId("being_p1")) == ()

    def test_other_observation_types_are_ignored(self) -> None:
        """人が入ってきた観測以外は、actor があっても会った記録に使わない。"""
        acquaintances, store, _ = _make()
        spoke = ObservationOutput(
            prose="ノアの声がした。",
            structured={"type": "player_spoke", "actor": "ノア"},
            observation_category="social",
        )

        acquaintances.on_observation(ADA, spoke)

        assert store.list_by_being(BeingId("being_p1")) == ()


class TestRecentlyMetNames:
    """recently_met_names が、Being のターン数で数えた直近に会った相手だけを返すことを保証する。"""

    def test_only_people_met_within_the_window_are_returned(self) -> None:
        """最後に会ったターンが現在のターンから窓の幅以内の相手だけを、初めて会った順に返す。"""
        acquaintances, _, turns = _make()
        ada = BeingId("being_p1")
        acquaintances.record_meeting(ADA, "リオ")
        for _ in range(4):
            turns.advance_turn(ada)
        acquaintances.record_meeting(ADA, "ノア")
        turns.advance_turn(ada)
        turns.advance_turn(ada)

        assert acquaintances.recently_met_names(ADA, within_turns=2) == ("ノア",)
        assert acquaintances.recently_met_names(ADA, within_turns=6) == ("リオ", "ノア")
