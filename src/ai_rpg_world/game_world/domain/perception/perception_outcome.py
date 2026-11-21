from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, final

from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceived_quality import PerceivedQuality
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
