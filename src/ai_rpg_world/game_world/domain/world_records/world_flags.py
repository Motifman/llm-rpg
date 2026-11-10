from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
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
class FlagPosition:
    flag: FlagId
    raised: bool


@final
@dataclass(frozen=True)
class WorldFlagsMemento:
    world_id: WorldId
    positions: frozenset[FlagPosition]

    def __post_init__(self) -> None:
        flags = [position.flag for position in self.positions]
        if len(set(flags)) != len(flags):
            raise RepeatedMementoKeyException(f"world {self.world_id} has a flag both raised and lowered")


class WorldFlags(AggregateRoot[WorldFlagsEvent]):
    def __init__(self, world_id: WorldId, changed: Mapping[FlagId, bool]) -> None:
        super().__init__()
        self._world_id = world_id
        self._changed = dict(changed)

    @classmethod
    def start(cls, world_id: WorldId) -> WorldFlags:
        return cls(world_id, {})

    @classmethod
    def from_memento(cls, memento: WorldFlagsMemento, design: WorldDesign) -> WorldFlags:
        return cls(memento.world_id, {position.flag: position.raised for position in memento.positions})

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> WorldFlagsMemento:
        return WorldFlagsMemento(
            world_id=self._world_id,
            positions=frozenset(FlagPosition(flag, raised) for flag, raised in self._changed.items()),
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
