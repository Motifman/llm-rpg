"""予期と、その出来事を Being ごとに持つ保存先の interface。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (
    UndeliveredExpectationEvent,
)


class ExpectationRepository(ABC):
    """予期の状態と、その変化で返った出来事を、同じ保存の単位で持つ。

    確定は取り消せず信念を直す処理につながるので、予期だけ保存されて出来事が
    失われる形にしない。出来事は未配信として積み、配信できたら印を付ける。

    予期のターンは Being の記憶のターン数 (``MemoryTurnClock``) で数えるが、
    ターン数そのものはここに持たない。
    """

    @abstractmethod
    def save(
        self,
        expectation: Expectation,
        events: Sequence[ExpectationEvent],
    ) -> None:
        """予期の状態と、その変化で返った出来事を未配信として、まとめて保存する。

        出来事を返さなかった変化なら空で渡す。次のどれかに当たるときは、何も
        保存せずに ``ExpectationValidationException`` を投げる。

        - 出来事がこの予期のものでない
        - 同じ出来事がすでに未配信にある
        - 清算待ちだった予期を終わった状態で保存するのに、終わったターンの
          終わりを告げる出来事が無い。確定の出来事を渡し忘れて失うのを防ぐ

        配信済みの印を付けた出来事は覚えていないので、同じ出来事をもう一度
        渡すと未配信として積み直す。
        """

    @abstractmethod
    def list_open_by_being(self, being_id: BeingId) -> list[Expectation]:
        """清算待ちの予期を、保存した順に返す。"""

    @abstractmethod
    def list_all_by_being(self, being_id: BeingId) -> list[Expectation]:
        """終わった予期も含めて、保存した順に返す。snapshot の capture 用。"""

    @abstractmethod
    def list_undelivered_by_being(
        self, being_id: BeingId
    ) -> list[UndeliveredExpectationEvent]:
        """まだ配信済みの印が付いていない出来事を、保存した順に返す。"""

    @abstractmethod
    def mark_delivered(self, being_id: BeingId, event_id: ExpectationEventId) -> None:
        """出来事に配信済みの印を付ける。未配信に無いときは ``ExpectationEventNotFoundException``。"""

    @abstractmethod
    def replace_all_by_being(
        self,
        being_id: BeingId,
        *,
        expectations: Sequence[Expectation],
        undelivered_events: Sequence[UndeliveredExpectationEvent],
        turn: int,
    ) -> None:
        """snapshot の復元用に、予期と未配信の出来事をまとめて置き換える (design_decisions 27)。

        ``turn`` は一緒に戻す記憶のターン数で、予期や出来事がそれより後のターンに
        ないかを確かめるためだけに受け取る。``require_restorable`` に通らない組
        なら、何も変えずに ``ExpectationValidationException`` を投げる。
        """


__all__ = ["ExpectationRepository"]
