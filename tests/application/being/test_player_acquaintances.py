from __future__ import annotations

import pytest

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.being.contract import EnvironmentEntry, Introduction
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

    def test_window_boundary_is_inclusive(self) -> None:
        """最後に会ったターンから現在までがちょうど窓の幅なら含め、1 つ超えたら含めない。"""
        acquaintances, _, turns = _make()
        acquaintances.record_meeting(ADA, "ノア")
        for _ in range(3):
            turns.advance_turn(BeingId("being_p1"))

        assert acquaintances.recently_met_names(ADA, within_turns=3) == ("ノア",)
        assert acquaintances.recently_met_names(ADA, within_turns=2) == ()


class TestWhoCanBeMet:
    """会った相手として記録するのはシナリオの参加者だけで、名前の取り違えを起動時に止めることを保証する。"""

    def test_entering_non_participant_is_not_recorded(self) -> None:
        """参加者に無い名前 (モンスターや、名前を引けなかったときの代わりの名前) が入ってきても、知り合いにしない。"""
        acquaintances, store, _ = _make()

        acquaintances.on_observation(ADA, _entered("不明なプレイヤー"))
        acquaintances.on_observation(ADA, _entered("森の狼"))

        assert store.list_by_being(BeingId("being_p1")) == ()

    def test_actor_surrounded_by_spaces_is_the_same_person(self) -> None:
        """actor の前後に空白があっても、空白を落とした参加者の名前で双方に記録する。"""
        acquaintances, _, _ = _make()

        acquaintances.on_observation(ADA, _entered("  ノア "))

        assert acquaintances.find(ADA, "ノア") is not None
        assert acquaintances.find(NOA, "エイダ") is not None

    def test_one_side_failing_does_not_drop_the_other_side(self) -> None:
        """受け手の Being を引くところで例外が出ても、入ってきた人の側の記録は残る。"""

        def being_id_of(pid: PlayerId) -> BeingId | None:
            if pid == ADA:
                raise RuntimeError("being lookup failed")
            return _being(pid)

        acquaintances = PlayerAcquaintances(
            store=InMemoryAcquaintanceRepository(),
            being_id_of=being_id_of,
            turn_reader=InMemoryExpectationRepository(),
            environment_name="島",
            names_by_player_id=NAMES,
        )

        acquaintances.on_observation(ADA, _entered("ノア"))

        assert acquaintances.find(NOA, "エイダ") is not None

    def test_duplicate_participant_names_are_rejected(self) -> None:
        """同じ名前の参加者が 2 人いると、名前から人を引けないので作れない。"""
        with pytest.raises(ValueError):
            PlayerAcquaintances(
                store=InMemoryAcquaintanceRepository(),
                being_id_of=_being,
                turn_reader=InMemoryExpectationRepository(),
                environment_name="島",
                names_by_player_id={1: "ノア", 2: "ノア"},
            )

    def test_blank_environment_name_is_rejected(self) -> None:
        """環境の名前が空なら作れない。実行中の観測ごとに記録が欠けるのではなく、起動時に止める。"""
        with pytest.raises(ValueError):
            PlayerAcquaintances(
                store=InMemoryAcquaintanceRepository(),
                being_id_of=_being,
                turn_reader=InMemoryExpectationRepository(),
                environment_name=" ",
                names_by_player_id=NAMES,
            )


class TestIntroductionsAndKnownPeople:
    """入るときの紹介を Being の記録に移し、いま知っている人の文を Being の記録から描くことを保証する。"""

    def test_introductions_become_known_people_with_notes(self) -> None:
        """取り決めの紹介を受け取ると、紹介した順に名前と関係の注記で【知っている人】の文になる。"""
        acquaintances, _, _ = _make()

        acquaintances.receive_entry(
            ADA,
            _entry(Introduction(name="ノア", relation_note="あなたと同じ側"), Introduction(name="リオ")),
        )

        assert acquaintances.known_people_text(ADA) == "- ノア（あなたと同じ側）\n- リオ"

    def test_introduced_person_is_recorded_with_no_meetings(self) -> None:
        """紹介されただけの相手は、会った回数が 0 のまま記録される。"""
        acquaintances, _, _ = _make()

        acquaintances.receive_entry(ADA, _entry(Introduction(name="ノア")))

        met = acquaintances.find(ADA, "ノア")
        assert met is not None and met.met_count == 0

    def test_person_met_without_introduction_is_known_too(self) -> None:
        """紹介されていなくても、会った相手は【知っている人】に加わる。"""
        acquaintances, _, _ = _make()
        acquaintances.receive_entry(ADA, _entry(Introduction(name="ノア")))

        acquaintances.record_meeting(ADA, "リオ")

        assert acquaintances.known_people_text(ADA) == "- ノア\n- リオ"

    def test_meeting_introduced_people_again_and_again_keeps_the_text(self) -> None:
        """紹介された相手に何度会っても、【知っている人】の文は 1 行のまま、並びも文も変わらない。変わるとそこから後ろのキャッシュが切れる。"""
        acquaintances, _, turns = _make()
        acquaintances.receive_entry(ADA, _entry(Introduction(name="ノア"), Introduction(name="リオ")))
        before = acquaintances.known_people_text(ADA)

        acquaintances.record_meeting(ADA, "リオ")
        turns.advance_turn(BeingId("being_p1"))
        acquaintances.record_meeting(ADA, "リオ")
        acquaintances.record_meeting(ADA, "ノア")

        assert acquaintances.known_people_text(ADA) == before == "- ノア\n- リオ"

    def test_entry_of_another_environment_is_rejected(self) -> None:
        """記録している環境と違う名前の取り決めを渡すと、別の環境の記録に紛れ込ませずに ValueError を投げる。"""
        acquaintances, _, _ = _make()

        with pytest.raises(ValueError):
            acquaintances.receive_entry(
                ADA,
                EnvironmentEntry(
                    environment_name="山村", self_name="エイダ",
                    introductions=[Introduction(name="ノア")],
                ),
            )

    def test_introductions_without_a_being_are_rejected(self) -> None:
        """Being に結び付かないプレイヤーに紹介を渡すと、黙って捨てずに ValueError を投げる。紹介が無ければ何もしない。"""
        acquaintances, _, _ = _make()

        with pytest.raises(ValueError):
            acquaintances.receive_entry(STRANGER, _entry(Introduction(name="ノア")))
        acquaintances.receive_entry(STRANGER, _entry())

        assert acquaintances.known_people_text(STRANGER) == ""

    def test_introduced_but_unmet_person_is_not_recently_met(self) -> None:
        """紹介されただけでまだ会っていない相手は、直近に会った相手に入らない。"""
        acquaintances, _, _ = _make()
        acquaintances.receive_entry(ADA, _entry(Introduction(name="ノア")))

        assert acquaintances.recently_met_names(ADA, within_turns=5) == ()


def _entry(*introductions: Introduction) -> EnvironmentEntry:
    return EnvironmentEntry(
        environment_name="島", self_name="エイダ", introductions=introductions
    )
