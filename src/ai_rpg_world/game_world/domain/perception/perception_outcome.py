from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol, final

from ai_rpg_world.being.contract import EnvironmentNotice, OwnActionCompleted, OwnBodyState, Route, SeenOrHeard
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesShapes
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceived_quality import (
    Completed,
    Felt,
    NoticedOnWaking,
    PerceivedQuality,
    Told,
)
from ai_rpg_world.game_world.domain.sound.hearing_quality import HearsClearly, HearsFaintly, HearsMuffled
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


class PerceptionRecipient(Protocol):
    def perceived(self, perceived: Perceived) -> None: ...

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None: ...

    def not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason) -> None: ...


@final
@dataclass(frozen=True)
class Perceived:
    perceiver: PersonId
    text: TextWithAssignedPeople
    quality: PerceivedQuality
    happened_at: WorldTick
    calls_attention: bool

    def hand_over(self, perceiver: PersonId, recipient: PerceptionRecipient) -> None:
        recipient.perceived(self)

    def route(self) -> Route:
        if isinstance(self.quality, Completed):
            return OwnActionCompleted(action_summary=self.quality.summary.for_being(), tool=self.quality.tool)
        return _ROUTES[type(self.quality)]


_ROUTES: Final[Mapping[type, Route]] = MappingProxyType(
    {
        SeesClearly: SeenOrHeard(),
        SeesShapes: SeenOrHeard(),
        HearsClearly: SeenOrHeard(),
        HearsMuffled: SeenOrHeard(),
        HearsFaintly: SeenOrHeard(),
        Felt: OwnBodyState(),
        Told: EnvironmentNotice(),
        NoticedOnWaking: EnvironmentNotice(),
    }
)


@final
@dataclass(frozen=True)
class NotPerceived:
    reason: NotPerceivedReason

    def hand_over(self, perceiver: PersonId, recipient: PerceptionRecipient) -> None:
        recipient.not_perceived(perceiver, self.reason)


@final
@dataclass(frozen=True)
class NoticedLater:
    notice: MissedNotice

    def hand_over(self, perceiver: PersonId, recipient: PerceptionRecipient) -> None:
        recipient.noticed_later(perceiver, self.notice)


PerceptionOutcome = Perceived | NotPerceived | NoticedLater
