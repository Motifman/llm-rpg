from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast, final

from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException
from ai_rpg_world.game_world.infrastructure.persistence.ground_items_codec import GroundItemsCodec
from ai_rpg_world.game_world.infrastructure.persistence.group_decision_codec import GroupDecisionCodec
from ai_rpg_world.game_world.infrastructure.persistence.group_membership_codec import GroupMembershipCodec
from ai_rpg_world.game_world.infrastructure.persistence.item_codec import ItemCodec
from ai_rpg_world.game_world.infrastructure.persistence.item_serial_counter_codec import ItemSerialCounterCodec
from ai_rpg_world.game_world.infrastructure.persistence.latest_actions_codec import LatestActionsCodec
from ai_rpg_world.game_world.infrastructure.persistence.missed_notices_codec import MissedNoticesCodec
from ai_rpg_world.game_world.infrastructure.persistence.object_state_codec import ObjectStateCodec
from ai_rpg_world.game_world.infrastructure.persistence.passage_states_codec import PassageStatesCodec
from ai_rpg_world.game_world.infrastructure.persistence.people_register_codec import PeopleRegisterCodec
from ai_rpg_world.game_world.infrastructure.persistence.person_inventory_codec import PersonInventoryCodec
from ai_rpg_world.game_world.infrastructure.persistence.person_outcomes_codec import PersonOutcomesCodec
from ai_rpg_world.game_world.infrastructure.persistence.person_vitals_codec import PersonVitalsCodec
from ai_rpg_world.game_world.infrastructure.persistence.scenario_progress_codec import ScenarioProgressCodec
from ai_rpg_world.game_world.infrastructure.persistence.spot_atmospheres_codec import SpotAtmospheresCodec
from ai_rpg_world.game_world.infrastructure.persistence.spot_search_progress_codec import SpotSearchProgressCodec
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    MementoNotStorableException,
    StoredMementoUnreadableException,
)
from ai_rpg_world.game_world.infrastructure.persistence.weather_codec import WeatherCodec
from ai_rpg_world.game_world.infrastructure.persistence.whereabouts_codec import WhereaboutsCodec
from ai_rpg_world.game_world.infrastructure.persistence.world_clock_codec import WorldClockCodec
from ai_rpg_world.game_world.infrastructure.persistence.world_ending_codec import WorldEndingCodec
from ai_rpg_world.game_world.infrastructure.persistence.world_flags_codec import WorldFlagsCodec
from ai_rpg_world.game_world.infrastructure.persistence.world_stage_codec import WorldStageCodec

_Memento = TypeVar("_Memento")


class AggregateCodec(Protocol[_Memento]):
    kind: str
    version: int
    memento_type: type[_Memento]

    def to_json(self, memento: _Memento) -> object: ...

    def from_json(self, raw: object) -> _Memento: ...


@final
@dataclass(frozen=True)
class StoredMemento:
    kind: str
    version: int
    state: str


@final
class AggregateCodecs:
    def __init__(self, codecs: Iterable[AggregateCodec[Any]]) -> None:
        self._by_kind: dict[str, AggregateCodec[Any]] = {}
        self._by_type: dict[type, AggregateCodec[Any]] = {}
        for codec in codecs:
            if codec.kind in self._by_kind or codec.memento_type in self._by_type:
                raise ValueError(f"{codec.kind} ({codec.memento_type.__name__}) is registered twice")
            self._by_kind[codec.kind] = codec
            self._by_type[codec.memento_type] = codec

    def memento_types(self) -> frozenset[type]:
        return frozenset(self._by_type)

    def kind_of(self, memento_type: type) -> str:
        codec = self._by_type.get(memento_type)
        if codec is None:
            raise MementoNotStorableException(f"no codec is registered for {memento_type.__name__}")
        return codec.kind

    def stored(self, memento: object) -> StoredMemento:
        codec = self._by_type.get(type(memento))
        if codec is None:
            raise MementoNotStorableException(f"no codec is registered for {type(memento).__name__}")
        written = codec.to_json(memento)
        try:
            state = json.dumps(written, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise MementoNotStorableException(f"{codec.kind} cannot be written as JSON: {error}") from error
        return StoredMemento(kind=codec.kind, version=codec.version, state=state)

    def memento(self, stored: StoredMemento, memento_type: type[_Memento]) -> _Memento:
        codec = self._by_kind.get(stored.kind)
        if codec is None:
            raise StoredMementoUnreadableException(f"no codec is registered for kind {stored.kind!r}")
        if codec.memento_type is not memento_type:
            raise StoredMementoUnreadableException(f"a {stored.kind} row is not a {memento_type.__name__}")
        if stored.version != codec.version:
            raise StoredMementoUnreadableException(
                f"a {stored.kind} row has version {stored.version}, but this code reads version {codec.version}"
            )
        try:
            return cast(
                _Memento, codec.from_json(json.loads(stored.state, object_pairs_hook=_object_without_repeated_keys))
            )
        except (json.JSONDecodeError, StoredMementoUnreadableException, GameWorldDomainException) as error:
            raise StoredMementoUnreadableException(
                f"a {stored.kind} row cannot be read: {type(error).__name__}: {error}"
            ) from error


def _object_without_repeated_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise StoredMementoUnreadableException(f"a key is written more than once in {sorted(key for key, _ in pairs)}")
    return fields


GAME_WORLD_CODECS = AggregateCodecs(
    [
        WorldClockCodec(),
        WorldFlagsCodec(),
        PersonVitalsCodec(),
        PersonOutcomesCodec(),
        GroupMembershipCodec(),
        PeopleRegisterCodec(),
        ItemCodec(),
        ItemSerialCounterCodec(),
        ObjectStateCodec(),
        PersonInventoryCodec(),
        GroundItemsCodec(),
        SpotSearchProgressCodec(),
        WhereaboutsCodec(),
        PassageStatesCodec(),
        SpotAtmospheresCodec(),
        GroupDecisionCodec(),
        WeatherCodec(),
        WorldEndingCodec(),
        WorldStageCodec(),
        LatestActionsCodec(),
        MissedNoticesCodec(),
        ScenarioProgressCodec(),
    ]
)
