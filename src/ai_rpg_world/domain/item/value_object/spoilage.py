from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

STATE_KEY_ACQUIRED_AT_TICK = "acquired_at_tick"
STATE_KEY_SPOILED = "spoiled"


class SpoilageAdvanceKind(Enum):
    UNCHANGED = "unchanged"
    ACQUIRED_AT_RECORDED = "acquired_at_recorded"
    NEWLY_SPOILED = "newly_spoiled"
    INVALID_ACQUIRED_AT = "invalid_acquired_at"


@dataclass(frozen=True)
class SpoilageAdvanceResult:
    kind: SpoilageAdvanceKind

    @property
    def state_changed(self) -> bool:
        return self.kind in (
            SpoilageAdvanceKind.ACQUIRED_AT_RECORDED,
            SpoilageAdvanceKind.NEWLY_SPOILED,
        )

    @property
    def newly_spoiled(self) -> bool:
        return self.kind is SpoilageAdvanceKind.NEWLY_SPOILED
