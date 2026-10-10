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
                environment_name="島", name="ノア", how_known=HowKnown.MET,
                known_since_turn=1, first_met_turn=1, last_met_turn=4, met_count=2,
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
            environment_name="島", name="カイ", how_known=HowKnown.MET,
            known_since_turn=0, first_met_turn=0, last_met_turn=5, met_count=3,
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
            HowKnown.INTRODUCED, "仲間", 2,
        )

    def test_meeting_someone_introduced_counts_as_first_meeting(self) -> None:
        """紹介された相手に会うと、同じ記録の会った回数が 1 になる。"""
        repo = InMemoryAcquaintanceRepository()
        repo.record_introduction(ADA, environment_name="島", name="ノア", turn=0, relation_note=None)

        met = repo.record_meeting(ADA, environment_name="島", name="ノア", turn=3)

        assert (met.how_known, met.met_count, met.first_met_turn) == (HowKnown.INTRODUCED, 1, 3)
