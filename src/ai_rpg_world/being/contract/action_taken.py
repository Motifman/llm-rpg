from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from ai_rpg_world.being.contract.errors import ContractViolation, require_bool, require_text
from ai_rpg_world.being.contract.observation import ObservedTime, OccurrenceOrder
from ai_rpg_world.being.contract.text_with_people import TextWithPeople


@dataclass(frozen=True, kw_only=True)
class ActionTaken:
    """呼び出し 1 つに、環境が 1 件だけ返す「その行動をどう行ったか」。

    行為について本人が知ったことは、これとは別に、経路が ``OwnAction`` の観測で届く。``accepted`` が偽なら、
    環境はその行動を断った。``action_summary`` は、環境が要約を組み立てられなかったときに None。
    """

    call_id: str
    action_summary: str | TextWithPeople | None
    accepted: bool
    time: ObservedTime
    order: OccurrenceOrder | None = None

    def __post_init__(self) -> None:
        require_text(self.call_id, "call_id")
        if self.action_summary is not None and not isinstance(self.action_summary, TextWithPeople):
            require_text(self.action_summary, "action_summary")
        require_bool(self.accepted, "accepted")
        if not isinstance(self.time, ObservedTime):
            raise ContractViolation("time must be ObservedTime")
        if self.order is not None and not isinstance(self.order, OccurrenceOrder):
            raise ContractViolation("order must be OccurrenceOrder or None")

    def with_people_named(self, name: Callable[[TextWithPeople], str]) -> ActionTaken:
        if not isinstance(self.action_summary, TextWithPeople):
            return self
        return replace(self, action_summary=name(self.action_summary))

    def summary_text(self) -> str | None:
        if isinstance(self.action_summary, TextWithPeople):
            raise ContractViolation(
                "an action summary with people placeholders cannot be read before the people are filled in"
            )
        return self.action_summary
