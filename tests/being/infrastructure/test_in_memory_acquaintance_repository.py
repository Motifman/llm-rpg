from __future__ import annotations

from ai_rpg_world.being.domain.acquaintance import Acquaintance, HowKnown
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_ada")
KAI = BeingId("being_kai")


class TestInMemoryAcquaintanceRepository:
    """InMemoryAcquaintanceRepository が、Being ごとに環境の名前と相手の名前の組で知り合いを持つことを保証する。"""

    def test_first_meeting_creates_and_second_meeting_updates(self) -> None:
        """同じ相手と 2 回会うと、1 件の記録の回数が 2 になり、最後に会ったターンが進む。"""
        repo = InMemoryAcquaintanceRepository()

        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1)
        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=4)

        assert repo.list_by_being(ADA) == (
            Acquaintance(
                environment_name="島",
                name="ノア",
                how_known=HowKnown.MET,
                known_since_turn=1,
                first_met_turn=1,
                last_met_turn=4,
                met_count=2,
                name_learned_turn=1,
            ),
        )

    def test_same_name_in_another_environment_is_another_person(self) -> None:
        """同じ名前でも環境の名前が違えば別の記録になり、find はそれぞれを返す。"""
        repo = InMemoryAcquaintanceRepository()

        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1)
        repo.record_meeting(ADA, environment_name="山村", name="ノア", turn=9)

        island = repo.find(ADA, environment_name="島", name="ノア")
        village = repo.find(ADA, environment_name="山村", name="ノア")
        assert island is not None and island.first_met_turn == 1
        assert village is not None and village.first_met_turn == 9

    def test_other_beings_records_do_not_mix(self) -> None:
        """ある Being の会った記録は、別の Being の find や一覧に出ない。"""
        repo = InMemoryAcquaintanceRepository()

        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1)

        assert repo.find(KAI, environment_name="島", name="ノア") is None
        assert repo.list_by_being(KAI) == ()

    def test_replace_all_by_being_overwrites_only_that_being(self) -> None:
        """replace_all_by_being はその Being の記録だけを渡した記録で置き換え、他の Being には触れない。"""
        repo = InMemoryAcquaintanceRepository()
        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1)
        repo.record_meeting(KAI, environment_name="島", name="リオ", turn=2)
        restored = Acquaintance(
            environment_name="島",
            name="カイ",
            how_known=HowKnown.MET,
            known_since_turn=0,
            first_met_turn=0,
            last_met_turn=5,
            met_count=3,
            name_learned_turn=0,
        )

        repo.replace_all_by_being(ADA, [restored])

        assert repo.list_by_being(ADA) == (restored,)
        assert repo.find(KAI, environment_name="島", name="リオ") is not None

    def test_introduction_is_recorded_once_and_does_not_overwrite(self) -> None:
        """紹介は知らない相手にだけ記録を作り、すでに会って知っている相手や紹介済みの相手の記録は変えない。"""
        repo = InMemoryAcquaintanceRepository()
        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1)

        repo.record_introduction(ADA, environment_name="島", name="ノア", turn=2, relation_note="仲間")
        repo.record_introduction(ADA, environment_name="島", name="カイ", turn=2, relation_note="仲間")
        repo.record_introduction(ADA, environment_name="島", name="カイ", turn=3, relation_note=None)

        noa = repo.find(ADA, environment_name="島", name="ノア")
        kai = repo.find(ADA, environment_name="島", name="カイ")
        assert noa is not None and (noa.how_known, noa.relation_note) == (HowKnown.MET, None)
        assert kai is not None and (kai.how_known, kai.relation_note, kai.known_since_turn) == (
            HowKnown.INTRODUCED,
            "仲間",
            2,
        )

    def test_meeting_someone_introduced_counts_as_first_meeting(self) -> None:
        """紹介された相手に会うと、同じ記録の会った回数が 1 になる。"""
        repo = InMemoryAcquaintanceRepository()
        repo.record_introduction(ADA, environment_name="島", name="ノア", turn=0, relation_note=None)

        met = repo.record_meeting(ADA, environment_name="島", name="ノア", turn=3)

        assert (met.how_known, met.met_count, met.first_met_turn) == (HowKnown.INTRODUCED, 1, 3)


class TestRecordingNames:
    """InMemoryAcquaintanceRepository が、名前を知らずに会った相手と、あとで名前を知ったことを記録することを保証する (#1581)。"""

    def test_meeting_without_the_name_then_learning_it(self) -> None:
        """名前を知らずに会った相手の名前を知ると、同じ記録が名前を知った記録に置き換わる。"""
        repo = InMemoryAcquaintanceRepository()
        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1, knows_name=False)

        learned = repo.record_name_learned(ADA, environment_name="島", name="ノア", turn=3)

        assert learned is not None and learned.name_learned_turn == 3
        assert repo.find(ADA, environment_name="島", name="ノア") == learned

    def test_name_of_someone_never_met_is_not_learned(self) -> None:
        """会ったことの無い相手の名前は、知ったことにせず None を返し、記録も作らない。"""
        repo = InMemoryAcquaintanceRepository()

        assert repo.record_name_learned(ADA, environment_name="島", name="ノア", turn=3) is None
        assert repo.list_by_being(ADA) == ()

    def test_meeting_again_does_not_forget_the_name(self) -> None:
        """名前を知った相手に、名前を知らない扱いでもう一度会っても、名前は知ったまま。"""
        repo = InMemoryAcquaintanceRepository()
        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1, knows_name=False)
        repo.record_name_learned(ADA, environment_name="島", name="ノア", turn=2)

        again = repo.record_meeting(ADA, environment_name="島", name="ノア", turn=4, knows_name=False)

        assert again.knows_name

    def test_introducing_someone_met_without_the_name_teaches_it(self) -> None:
        """名前を知らずに会った相手を紹介されると、会った記録は保ったまま名前を知り、関係の注記は付かない。"""
        repo = InMemoryAcquaintanceRepository()
        repo.record_meeting(ADA, environment_name="島", name="ノア", turn=1, knows_name=False)

        known = repo.record_introduction(
            ADA, environment_name="島", name="ノア", turn=3, relation_note="あなたと同じ側"
        )

        assert (known.knows_name, known.name_learned_turn, known.met_count) == (True, 3, 1)
