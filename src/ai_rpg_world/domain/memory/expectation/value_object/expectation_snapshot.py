from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_status import (
    ExpectationStatus,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)


@dataclass(frozen=True)
class ExpectationSnapshot:
    """予期を保存して戻すための値。``Expectation.snapshot()`` が返し、``Expectation.restore()`` が受け取る。

    規則と食い違わないかは、この値ではなく ``Expectation.restore()`` が確かめる。
    保存先から読んだ値は、集約に戻すまで信用しない。
    """

    expectation_id: ExpectationId
    holder: BeingId
    content: str
    origin: ExpectationOrigin
    likelihood: Likelihood
    formed_at_turn: int
    expires_at_turn: int
    shape: ShapeVerdict | None
    checks: tuple[Check, ...]
    status: ExpectationStatus
    closed_at_turn: int | None
    formed_with: str | None = None
    due: str | None = None
    beliefs_in_mind: tuple[str, ...] = ()
    episodes_in_mind: tuple[str, ...] = ()
    grounds: ExpectationGrounds | None = None


__all__ = ["ExpectationSnapshot"]
