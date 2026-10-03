"""予期の状態が移ったときに返す出来事。

``BaseDomainEvent`` は世界の tick と実時刻を持つので使わない。予期は環境の
概念を持たず、本人のターン数だけで閉じる。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)


@dataclass(frozen=True)
class ProvisionallyMissed:
    """暫定で外れた。その場で気づく、場面を区切る、エピソードの salience に使う。"""

    expectation_id: ExpectationId
    holder: BeingId
    turn: int
    likelihood: Likelihood


@dataclass(frozen=True)
class ExpectationSettled:
    """当否が確定した。頭にあった信念への支持・反証と、思い出していたエピソードの見直しに使う。

    受け取る側は予期の保存先を引かずに材料を書けるよう、予期の文も運ぶ。
    """

    expectation_id: ExpectationId
    holder: BeingId
    turn: int
    content: str
    outcome: Outcome
    likelihood: Likelihood
    beliefs_in_mind: tuple[str, ...]
    episodes_in_mind: tuple[str, ...]


@dataclass(frozen=True)
class ExpectationDismissed:
    """形の判定で、清算に回さず外した。"""

    expectation_id: ExpectationId
    holder: BeingId
    turn: int
    shape: ShapeVerdict


@dataclass(frozen=True)
class ExpectationVoided:
    """照合で予期になっていないと判定され、確定させずに外した。"""

    expectation_id: ExpectationId
    holder: BeingId
    turn: int


@dataclass(frozen=True)
class ExpectationExpired:
    """当否が決まらないまま期限のターンを過ぎた。"""

    expectation_id: ExpectationId
    holder: BeingId
    turn: int


ExpectationEvent = Union[
    ProvisionallyMissed,
    ExpectationSettled,
    ExpectationDismissed,
    ExpectationVoided,
    ExpectationExpired,
]


__all__ = [
    "ExpectationDismissed",
    "ExpectationEvent",
    "ExpectationExpired",
    "ExpectationSettled",
    "ExpectationVoided",
    "ProvisionallyMissed",
]
