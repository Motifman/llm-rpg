from __future__ import annotations

import pytest

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    SubjectUnknownView,
    WithheldFromStrangers,
)
from ai_rpg_world.being.contract import EnvironmentEntry, Introduction
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ADA = PlayerId(1)
NOA = PlayerId(2)
STRANGER = PlayerId(9)
NAMES = {1: "エイダ", 2: "ノア", 3: "リオ"}


def _being(pid: PlayerId) -> BeingId | None:
    return BeingId(f"being_p{pid.value}") if pid.value in NAMES else None


def _make() -> tuple[PlayerAcquaintances, InMemoryAcquaintanceRepository, InMemoryMemoryTurnClock]:
    store = InMemoryAcquaintanceRepository()
    turns = InMemoryMemoryTurnClock()
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
            turn_reader=InMemoryMemoryTurnClock(),
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
                turn_reader=InMemoryMemoryTurnClock(),
                environment_name="島",
                names_by_player_id={1: "ノア", 2: "ノア"},
            )

    def test_blank_environment_name_is_rejected(self) -> None:
        """環境の名前が空なら作れない。実行中の観測ごとに記録が欠けるのではなく、起動時に止める。"""
        with pytest.raises(ValueError):
            PlayerAcquaintances(
                store=InMemoryAcquaintanceRepository(),
                being_id_of=_being,
                turn_reader=InMemoryMemoryTurnClock(),
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

def _entry(*introductions: Introduction) -> EnvironmentEntry:
    return EnvironmentEntry(
        environment_name="島", self_name="エイダ", introductions=introductions
    )


def _heard(speaker: str = "ノア") -> ObservationOutput:
    return ObservationOutput(
        prose=f"{speaker}の遠くの声が聞こえる: 「水門」",
        structured={"type": "player_spoke", "speaker": speaker, "content": "水門"},
        observation_category="social",
        schedules_turn=True,
        subject_name=speaker,
        if_subject_unknown=SubjectUnknownView(
            prose="誰かの遠くの声が聞こえる: 「水門」",
            structured={"type": "player_spoke", "content": "水門"},
        ),
    )


class TestViewForRecipient:
    """観測を受け手の記録に入れるとき、話し手を知っているかでどちらの版を記録するかを決めることを保証する。"""

    def test_unknown_speaker_is_recorded_as_someone(self) -> None:
        """知らない話し手の声は、伏せた本文と structured で記録され、ほかの欄は元の観測のまま保たれる。"""
        acquaintances, _, _ = _make()

        seen = acquaintances.view_for(ADA, _heard())

        assert seen.prose == "誰かの遠くの声が聞こえる: 「水門」"
        assert seen.structured == {"type": "player_spoke", "content": "水門"}
        assert (seen.observation_category, seen.schedules_turn) == ("social", True)
        assert (seen.subject_name, seen.if_subject_unknown) == (None, None)

    def test_known_speaker_is_recorded_by_name(self) -> None:
        """紹介された話し手の声は、名前の付いた元の本文で記録される。"""
        acquaintances, _, _ = _make()
        acquaintances.receive_entry(ADA, _entry(Introduction(name="ノア")))

        seen = acquaintances.view_for(ADA, _heard())

        assert seen.prose == "ノアの遠くの声が聞こえる: 「水門」"
        assert seen.structured["speaker"] == "ノア"
        assert (seen.subject_name, seen.if_subject_unknown) == (None, None)

    def test_observation_without_alternate_view_is_unchanged(self) -> None:
        """話し手で描き方が変わらない観測は、そのまま返す。"""
        acquaintances, _, _ = _make()
        plain = ObservationOutput(prose="雨が降り出した。", structured={"type": "weather"})

        assert acquaintances.view_for(ADA, plain) is plain

    def test_knowing_later_does_not_rewrite_what_was_recorded(self) -> None:
        """伏せて記録したあとで話し手と会っても、記録した観測は伏せたままで、そのあとの声から名前が付く。"""
        acquaintances, _, _ = _make()
        before = acquaintances.view_for(ADA, _heard())

        acquaintances.record_meeting(ADA, "ノア")
        after = acquaintances.view_for(ADA, _heard())

        assert before.prose.startswith("誰か")
        assert after.prose.startswith("ノア")

    def test_lookup_failure_hides_the_name(self) -> None:
        """知り合いの記録を引くところで例外が出ても観測は失われず、名前を伏せた版で記録される。"""
        def broken(_pid: PlayerId) -> BeingId | None:
            raise RuntimeError("lookup failed")

        acquaintances = PlayerAcquaintances(
            store=InMemoryAcquaintanceRepository(),
            being_id_of=broken,
            turn_reader=InMemoryMemoryTurnClock(),
            environment_name="島",
            names_by_player_id=NAMES,
        )

        assert acquaintances.view_for(ADA, _heard()).prose.startswith("誰か")


def _remote_revive(name: str) -> ObservationOutput:
    return ObservationOutput(
        prose="遠くで誰かが動けるようになった気配がした。",
        structured={"type": "player_revived", "actor": name},
        observation_category="social",
        schedules_turn=True,
        subject_name=name,
        if_subject_unknown=WithheldFromStrangers(),
    )


class TestViewForWithheld:
    """主体を知らない受け手には届けない観測を、知り合いの記録で届けるかどうか決めることを保証する。"""

    def test_unknown_subject_is_not_recorded(self) -> None:
        """知らない相手の遠くの気配は、受け手の記録に入れない (None を返す)。"""
        acquaintances, _, _ = _make()

        assert acquaintances.view_for(ADA, _remote_revive("ノア")) is None

    def test_known_subject_is_recorded_as_it_is(self) -> None:
        """紹介された相手の遠くの気配は、structured に名前を残したまま記録する。"""
        acquaintances, _, _ = _make()
        acquaintances.receive_entry(ADA, _entry(Introduction(name="ノア")))

        seen = acquaintances.view_for(ADA, _remote_revive("ノア"))

        assert seen is not None and seen.structured["actor"] == "ノア"

    def test_own_subject_counts_as_known(self) -> None:
        """自分が主体の観測は、自分を知り合いとして記録していなくても届く。"""
        acquaintances, _, _ = _make()

        seen = acquaintances.view_for(ADA, _remote_revive("エイダ"))

        assert seen is not None and seen.structured["actor"] == "エイダ"

    def test_lookup_failure_withholds(self) -> None:
        """知り合いの記録を引くところで例外が出たら、届けない側へ倒す。"""
        def broken(_pid: PlayerId) -> BeingId | None:
            raise RuntimeError("lookup failed")

        acquaintances = PlayerAcquaintances(
            store=InMemoryAcquaintanceRepository(),
            being_id_of=broken,
            turn_reader=InMemoryMemoryTurnClock(),
            environment_name="島",
            names_by_player_id=NAMES,
        )

        assert acquaintances.view_for(NOA, _remote_revive("リオ")) is None


class TestKnowsPlayer:
    """受け手の Being が、プレイヤー番号で指した相手を知っているかを答えることを保証する (#1531)。"""

    def test_introduced_player_is_known(self) -> None:
        """エイダは、入るときにノアを紹介されていれば、ノアを知っていると答える。"""
        acquaintances, _, _ = _make()
        acquaintances.receive_entry(ADA, _entry(Introduction(name="ノア")))

        assert acquaintances.knows(ADA, NOA) is True

    def test_unmet_player_is_not_known(self) -> None:
        """エイダは、ノアを紹介されても会ってもいなければ、知らないと答える。"""
        acquaintances, _, _ = _make()

        assert acquaintances.knows(ADA, NOA) is False

    def test_oneself_is_known(self) -> None:
        """エイダは、自分自身 (同じプレイヤー番号) を知っていると答える。知り合いの記録に自分が無くてもよい。"""
        acquaintances, _, _ = _make()

        assert acquaintances.knows(ADA, ADA) is True

    def test_non_participant_is_not_known(self) -> None:
        """シナリオの参加者に無いプレイヤー番号の相手は、知らないと答える。"""
        acquaintances, _, _ = _make()

        assert acquaintances.knows(ADA, STRANGER) is False

    def test_lookup_failure_is_not_known(self) -> None:
        """受け手の Being を引くところで例外が出たら、知らないと答える。知っていると答えると相手の存在が届くため。"""
        def broken(_pid: PlayerId) -> BeingId | None:
            raise RuntimeError("lookup failed")

        acquaintances = PlayerAcquaintances(
            store=InMemoryAcquaintanceRepository(),
            being_id_of=broken,
            turn_reader=InMemoryMemoryTurnClock(),
            environment_name="島",
            names_by_player_id=NAMES,
        )

        assert acquaintances.knows(ADA, NOA) is False
