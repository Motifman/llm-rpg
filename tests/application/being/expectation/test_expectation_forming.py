"""行動に書かれた予期を、Being のいまのターン数と頭にあった信念・想起とともに積む挙動を保証する (#1441)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.being.expectation.forming import (
    ExpectationFormingInterrupted,
    ExpectationFormingService,
    WrittenExpectation,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

_ME = BeingId("being-mori")


def _service(
    repository: InMemoryExpectationRepository,
    clock: InMemoryMemoryTurnClock,
) -> ExpectationFormingService:
    return ExpectationFormingService(
        repository, turn_reader=clock, undated_term_turns=5, dated_term_turns=30
    )


def _at_turn(turn: int) -> tuple[InMemoryExpectationRepository, InMemoryMemoryTurnClock]:
    clock = InMemoryMemoryTurnClock()
    for _ in range(turn):
        clock.advance_turn(_ME)
    return InMemoryExpectationRepository(), clock


def _form(
    service: ExpectationFormingService, *written: WrittenExpectation
) -> list:
    return service.form(
        _ME,
        written,
        formed_with="セナに話しかけた",
        beliefs_in_mind=("belief-1",),
        episodes_in_mind=("episode-7",),
    )


class TestFormedExpectations:
    """書かれた予期 1 件ごとに、清算待ちの予期が 1 件ずつ積まれることを保証する。"""

    def test_each_written_expectation_is_saved_as_open_with_the_current_turn(
        self,
    ) -> None:
        """Being のターン数が 3 のとき 2 件書くと、どちらもターン 3 に作られた清算待ちの予期として保存される。"""
        repository, clock = _at_turn(3)
        service = _service(repository, clock)

        _form(
            service,
            WrittenExpectation("セナが返事をする", None, Likelihood.PROBABLY),
            WrittenExpectation("夜に雨が降る", "今夜", Likelihood.MAYBE),
        )

        saved = repository.list_open_by_being(_ME)
        assert [(e.content, e.formed_at_turn) for e in saved] == [
            ("セナが返事をする", 3),
            ("夜に雨が降る", 3),
        ]

    def test_saved_expectation_carries_the_action_and_what_was_in_mind(self) -> None:
        """積んだ予期は、行動に添えた予期として、行動の文・期日・確からしさ・頭にあった信念と想起を持つ。"""
        repository, clock = _at_turn(1)

        _form(
            _service(repository, clock),
            WrittenExpectation("夜に雨が降る", "今夜", Likelihood.MAYBE),
        )

        (saved,) = repository.list_open_by_being(_ME)
        assert saved.origin is ExpectationOrigin.WITH_ACTION
        assert saved.formed_with == "セナに話しかけた"
        assert saved.due == "今夜"
        assert saved.likelihood is Likelihood.MAYBE
        assert saved.beliefs_in_mind == ("belief-1",)
        assert saved.episodes_in_mind == ("episode-7",)

    def test_undated_expectation_expires_after_the_undated_term(self) -> None:
        """期日の無い予期は、書いたターンから期日の無い予期の期限のターン数で期限を迎える。"""
        repository, clock = _at_turn(2)

        _form(
            _service(repository, clock),
            WrittenExpectation("セナが返事をする", None, Likelihood.PROBABLY),
        )

        (saved,) = repository.list_open_by_being(_ME)
        assert saved.expires_at_turn == 2 + 5

    def test_dated_expectation_expires_after_the_dated_term(self) -> None:
        """期日のある予期は、期日のある予期の期限のターン数で期限を迎える。"""
        repository, clock = _at_turn(2)

        _form(
            _service(repository, clock),
            WrittenExpectation("夜に雨が降る", "今夜", Likelihood.MAYBE),
        )

        (saved,) = repository.list_open_by_being(_ME)
        assert saved.expires_at_turn == 2 + 30

    def test_nothing_written_saves_nothing(self) -> None:
        """何も書かれていなければ何も保存せず、空を返す。"""
        repository, clock = _at_turn(1)

        formed = _form(_service(repository, clock))

        assert formed == []
        assert repository.list_all_by_being(_ME) == []


class TestExpectationIds:
    """予期の ID が、メモリ上の参照や連番の状態に頼らず、Being・ターン・書いた順から決まることを保証する。"""

    def test_id_is_built_from_being_turn_and_order(self) -> None:
        """ターン 4 に 2 件書くと、ID は Being の ID・ターン・書いた順を並べた文字列になる。"""
        repository, clock = _at_turn(4)

        formed = _form(
            _service(repository, clock),
            WrittenExpectation("a が起きる", None, Likelihood.EVEN),
            WrittenExpectation("b が起きる", None, Likelihood.EVEN),
        )

        assert [e.expectation_id.value for e in formed] == [
            "being-mori:t4:0",
            "being-mori:t4:1",
        ]

    def test_forming_twice_in_one_turn_fails_without_overwriting(self) -> None:
        """同じターンに 2 回積もうとすると、前に積んだ予期を上書きせずに ValueError を投げる。"""
        repository, clock = _at_turn(1)
        service = _service(repository, clock)
        _form(service, WrittenExpectation("a が起きる", None, Likelihood.EVEN))

        with pytest.raises(ValueError, match="already formed"):
            _form(service, WrittenExpectation("b が起きる", None, Likelihood.EVEN))

        assert [e.content for e in repository.list_all_by_being(_ME)] == ["a が起きる"]


class _FailsOnSecondSave(InMemoryExpectationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.saves = 0

    def save(self, expectation, events) -> None:  # type: ignore[no-untyped-def]
        self.saves += 1
        if self.saves == 2:
            raise RuntimeError("store is down")
        super().save(expectation, events)


class TestInterruptedSave:
    """保存の途中で失敗したとき、保存し終えた予期を呼び出し側に伝えることを保証する。"""

    def test_failure_on_the_second_save_reports_the_first_as_saved(self) -> None:
        """2 件目の保存で失敗すると、1 件目だけを保存済みとして ExpectationFormingInterrupted で伝え、元の例外を原因に持つ。"""
        repository = _FailsOnSecondSave()
        clock = InMemoryMemoryTurnClock()
        clock.advance_turn(_ME)

        with pytest.raises(ExpectationFormingInterrupted) as raised:
            _form(
                _service(repository, clock),
                WrittenExpectation("a が起きる", None, Likelihood.EVEN),
                WrittenExpectation("b が起きる", None, Likelihood.EVEN),
            )

        assert [e.content for e in raised.value.saved] == ["a が起きる"]
        assert isinstance(raised.value.__cause__, RuntimeError)
        assert [e.content for e in repository.list_all_by_being(_ME)] == ["a が起きる"]


class TestConstruction:
    """組めない期限の設定を、積む前に止めることを保証する。"""

    @pytest.mark.parametrize("name", ["undated_term_turns", "dated_term_turns"])
    def test_term_below_one_fails(self, name: str) -> None:
        """期限のターン数に 0 を渡すと ValueError を投げる。"""
        terms = {"undated_term_turns": 5, "dated_term_turns": 30, name: 0}

        with pytest.raises(ValueError, match=name):
            ExpectationFormingService(
                InMemoryExpectationRepository(),
                turn_reader=InMemoryMemoryTurnClock(),
                **terms,
            )
