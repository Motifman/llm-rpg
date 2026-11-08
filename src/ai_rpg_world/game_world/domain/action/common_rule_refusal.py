from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import final


class CommonRuleRefusalKind(Enum):
    ACTOR_CANNOT_ACT = "ACTOR_CANNOT_ACT"
    BUSY = "BUSY"
    NOT_TOGETHER = "NOT_TOGETHER"
    OUT_OF_REACH = "OUT_OF_REACH"
    TOO_TIRED = "TOO_TIRED"
    NOT_ALLOWED_IN_THIS_STAGE = "NOT_ALLOWED_IN_THIS_STAGE"
    NO_ONE_FOUND_IN_THE_DARK = "NO_ONE_FOUND_IN_THE_DARK"


@final
@dataclass(frozen=True)
class ActorCannotAct:
    def kind(self) -> CommonRuleRefusalKind:
        return CommonRuleRefusalKind.ACTOR_CANNOT_ACT


@final
@dataclass(frozen=True)
class Busy:
    def kind(self) -> CommonRuleRefusalKind:
        return CommonRuleRefusalKind.BUSY


@final
@dataclass(frozen=True)
class NotTogether:
    def kind(self) -> CommonRuleRefusalKind:
        return CommonRuleRefusalKind.NOT_TOGETHER


@final
@dataclass(frozen=True)
class OutOfReach:
    def kind(self) -> CommonRuleRefusalKind:
        return CommonRuleRefusalKind.OUT_OF_REACH


@final
@dataclass(frozen=True)
class TooTired:
    def kind(self) -> CommonRuleRefusalKind:
        return CommonRuleRefusalKind.TOO_TIRED


@final
@dataclass(frozen=True)
class NotAllowedInThisStage:
    def kind(self) -> CommonRuleRefusalKind:
        return CommonRuleRefusalKind.NOT_ALLOWED_IN_THIS_STAGE


@final
@dataclass(frozen=True)
class NoOneFoundInTheDark:
    def kind(self) -> CommonRuleRefusalKind:
        return CommonRuleRefusalKind.NO_ONE_FOUND_IN_THE_DARK


CommonRuleRefusal = ActorCannotAct | Busy | NotTogether | OutOfReach | TooTired | NotAllowedInThisStage | NoOneFoundInTheDark
