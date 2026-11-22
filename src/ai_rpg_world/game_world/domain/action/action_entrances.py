from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.built_in_attempts import (
        EnterSectionAttempt,
        GroundItemPickupAttempt,
        GroupDecisionBallotAttempt,
        HoldItemAttempt,
        ItemDropAttempt,
        ItemHandOverAttempt,
        ItemUseAttempt,
        LeaveSectionAttempt,
        ListeningAttempt,
        PutAwayItemAttempt,
        SpeechAttempt,
        SpotSearchAttempt,
        TendAttempt,
        TravelAttempt,
        WaitAttempt,
    )
    from ai_rpg_world.game_world.domain.action.interaction_attempts import (
        CarriedItemInteractionAttempt,
        ObjectInteractionAttempt,
        PersonInteractionAttempt,
    )

_Reply = TypeVar("_Reply", covariant=True)


class ActionEntrances(Protocol[_Reply]):
    def travel(self, attempt: TravelAttempt) -> _Reply: ...

    def speak(self, attempt: SpeechAttempt) -> _Reply: ...

    def listen(self, attempt: ListeningAttempt) -> _Reply: ...

    def wait(self, attempt: WaitAttempt) -> _Reply: ...

    def tend(self, attempt: TendAttempt) -> _Reply: ...

    def hand_over(self, attempt: ItemHandOverAttempt) -> _Reply: ...

    def pick_up(self, attempt: GroundItemPickupAttempt) -> _Reply: ...

    def drop(self, attempt: ItemDropAttempt) -> _Reply: ...

    def search_spot(self, attempt: SpotSearchAttempt) -> _Reply: ...

    def use_item(self, attempt: ItemUseAttempt) -> _Reply: ...

    def enter_section(self, attempt: EnterSectionAttempt) -> _Reply: ...

    def leave_section(self, attempt: LeaveSectionAttempt) -> _Reply: ...

    def hold(self, attempt: HoldItemAttempt) -> _Reply: ...

    def put_away(self, attempt: PutAwayItemAttempt) -> _Reply: ...

    def cast_ballot(self, attempt: GroupDecisionBallotAttempt) -> _Reply: ...

    def interact_with_object(self, attempt: ObjectInteractionAttempt) -> _Reply: ...

    def interact_with_carried_item(self, attempt: CarriedItemInteractionAttempt) -> _Reply: ...

    def interact_with_person(self, attempt: PersonInteractionAttempt) -> _Reply: ...

    def misfit(self, text: str) -> _Reply: ...
