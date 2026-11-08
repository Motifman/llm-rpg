from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.spot_declaration_exception import (
    DuplicatePassageStateNameException,
    InitialPassageStateNotDeclaredException,
    NoPassageStatesException,
    PassageEndsAtSameSpotException,
    UndeclaredPassageStateException,
)
from ai_rpg_world.game_world.domain.sound import SoundLoss
from ai_rpg_world.game_world.domain.value_object import DisplayName, PassageId, PassageStateName, SpotId, Ticks


@final
@dataclass(frozen=True)
class PassageStateDeclaration:
    name: PassageStateName
    display_name: DisplayName
    traversable: bool
    sound_loss: SoundLoss


@final
@dataclass(frozen=True)
class PassageDeclaration:
    passage_id: PassageId
    ends: tuple[SpotId, SpotId]
    two_way: bool
    travel_ticks: Ticks
    states: tuple[PassageStateDeclaration, ...]
    initial_state: PassageStateName
    hidden_until_revealed: bool

    def __post_init__(self) -> None:
        if self.ends[0] == self.ends[1]:
            raise PassageEndsAtSameSpotException(
                f"PassageDeclaration {self.passage_id.value} leads from {self.ends[0].value!r} back to itself"
            )
        if not self.states:
            raise NoPassageStatesException(f"PassageDeclaration {self.passage_id.value} declares no state")
        names = [state.name for state in self.states]
        if len(set(names)) != len(names):
            raise DuplicatePassageStateNameException(
                f"PassageDeclaration {self.passage_id.value} declares a state name more than once"
            )
        if all(state.name != self.initial_state for state in self.states):
            raise InitialPassageStateNotDeclaredException(
                f"PassageDeclaration {self.passage_id.value} starts in {self.initial_state.value!r}, "
                f"which is not among its states"
            )

    def far_end_from(self, here: SpotId) -> SpotId | None:
        near, far = self.ends
        if here == near:
            return far
        if here == far and self.two_way:
            return near
        return None

    def allows(self, state: PassageStateName) -> bool:
        return self.state(state).traversable

    def state(self, name: PassageStateName) -> PassageStateDeclaration:
        for declared in self.states:
            if declared.name == name:
                return declared
        raise UndeclaredPassageStateException(f"PassageDeclaration {self.passage_id.value} has no state {name.value!r}")
