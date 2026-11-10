from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.value_object import FlagId, WorldId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True, kw_only=True)
class WorldFlagRaisedEvent(DomainEvent):
    world_id: WorldId
    flag_id: FlagId
    trigger: Trigger


@final
@dataclass(frozen=True, kw_only=True)
class WorldFlagLoweredEvent(DomainEvent):
    world_id: WorldId
    flag_id: FlagId
    trigger: Trigger


WorldFlagsEvent = WorldFlagRaisedEvent | WorldFlagLoweredEvent


@final
@dataclass(frozen=True)
class WorldFlagsMemento:
    world_id: WorldId
    raised: tuple[FlagId, ...]
    lowered: tuple[FlagId, ...]


class WorldFlags(AggregateRoot[WorldFlagsEvent]):
    def __init__(self, world_id: WorldId) -> None:
        super().__init__()
        self._world_id = world_id
        self._changed: dict[FlagId, bool] = {}

    @classmethod
    def from_memento(cls, memento: WorldFlagsMemento, design: WorldDesign) -> WorldFlags:
        flags = cls(memento.world_id)
        flags._changed = {flag_id: True for flag_id in memento.raised} | {flag_id: False for flag_id in memento.lowered}
        return flags

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> WorldFlagsMemento:
        return WorldFlagsMemento(
            world_id=self._world_id,
            raised=tuple(flag_id for flag_id, raised in self._changed.items() if raised),
            lowered=tuple(flag_id for flag_id, raised in self._changed.items() if not raised),
        )

    def raise_flag(self, flag: FlagDeclaration, trigger: Trigger) -> None:
        if self.is_raised(flag):
            return
        self._changed[flag.flag_id] = True
        self.add_event(
            WorldFlagRaisedEvent(**new_event_stamp(), world_id=self._world_id, flag_id=flag.flag_id, trigger=trigger)
        )

    def lower_flag(self, flag: FlagDeclaration, trigger: Trigger) -> None:
        if not self.is_raised(flag):
            return
        self._changed[flag.flag_id] = False
        self.add_event(
            WorldFlagLoweredEvent(**new_event_stamp(), world_id=self._world_id, flag_id=flag.flag_id, trigger=trigger)
        )

    def is_raised(self, flag: FlagDeclaration) -> bool:
        return self._changed.get(flag.flag_id, flag.initially_raised)
