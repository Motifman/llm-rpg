"""行動に書かれた予期を、Being の予期として積む (#1441)。

## 時刻は本人のターン数で持つ

作ったターンは Being のターン数から取る。世界の tick ではなく本人の歩みで時刻を
持つので、清算と同じ時計になる。ターン数は 1 手の処理より先に進めてあるので
(design_decisions D1440)、ここで読む値がこの手のターンになる。

## 期限は期日の有無で分ける

期日は環境の時間で書かれ、届いた出来事の時刻を Jev が読んで清算する。記憶は環境
の時計を持たないので、ターン数で切るのは本来は期日の無い予期だけ。期日のある予期
にもターン数の期限は要るので、長めに切る。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.repository.expectation_repository import (
    ExpectationRepository,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)


@dataclass(frozen=True)
class WrittenExpectation:
    """エージェントが行動に添えて書いた予期 1 件。"""

    what: str
    when: str | None
    likelihood: Likelihood


class ExpectationFormingInterrupted(Exception):
    """保存の途中で失敗した。``saved`` は失敗の前に保存し終えた予期。

    保存先には 1 件ずつ書くので、途中で失敗すると前の予期だけが残る。何が残った
    かを呼び出し側の trace に載せ、trace と保存先が食い違わないようにする。
    """

    def __init__(self, saved: tuple[Expectation, ...]) -> None:
        super().__init__(f"{len(saved)} expectation(s) were saved before the failure")
        self.saved = saved


class ExpectationFormingService:
    """書かれた予期を、清算待ちの予期として保存する。"""

    def __init__(
        self,
        repository: ExpectationRepository,
        *,
        turn_reader: MemoryTurnReader,
        undated_term_turns: int,
        dated_term_turns: int,
    ) -> None:
        if not isinstance(repository, ExpectationRepository):
            raise TypeError("repository must be ExpectationRepository")
        if not isinstance(turn_reader, MemoryTurnReader):
            raise TypeError("turn_reader must be MemoryTurnReader")
        for name, value in (
            ("undated_term_turns", undated_term_turns),
            ("dated_term_turns", dated_term_turns),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be int")
            if value < 1:
                raise ValueError(f"{name} must be 1 or greater")
        self._repository = repository
        self._turn_reader = turn_reader
        self._undated_term_turns = undated_term_turns
        self._dated_term_turns = dated_term_turns

    def form(
        self,
        being_id: BeingId,
        written: Sequence[WrittenExpectation],
        *,
        formed_with: str | None,
        beliefs_in_mind: tuple[str, ...],
        episodes_in_mind: tuple[str, ...],
    ) -> list[Expectation]:
        """いまのターン数で予期を作って保存し、作った予期を書かれた順に返す。

        同じターンに 2 回呼ぶと ``ValueError``。ID がターンと書いた順で決まるので、
        2 回目は前に積んだ予期を上書きしてしまう。保存の途中で失敗したら
        ``ExpectationFormingInterrupted`` を投げる。
        """
        if not written:
            return []
        turn = self._turn_reader.current_turn(being_id)
        prefix = f"{being_id.value}:t{turn}:"
        if any(
            e.expectation_id.value.startswith(prefix)
            for e in self._repository.list_open_by_being(being_id)
        ):
            raise ValueError(
                f"expectations of {being_id} at turn {turn} are already formed; "
                "form must be called once per move"
            )
        formed = [
            Expectation(
                expectation_id=ExpectationId(f"{prefix}{index}"),
                holder=being_id,
                content=item.what,
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=item.likelihood,
                formed_at_turn=turn,
                expires_at_turn=turn
                + (
                    self._undated_term_turns
                    if item.when is None
                    else self._dated_term_turns
                ),
                formed_with=formed_with,
                due=item.when,
                beliefs_in_mind=beliefs_in_mind,
                episodes_in_mind=episodes_in_mind,
            )
            for index, item in enumerate(written)
        ]
        saved: list[Expectation] = []
        try:
            for expectation in formed:
                self._repository.save(expectation, [])
                saved.append(expectation)
        except Exception as exc:
            raise ExpectationFormingInterrupted(tuple(saved)) from exc
        return formed


__all__ = [
    "ExpectationFormingInterrupted",
    "ExpectationFormingService",
    "WrittenExpectation",
]
