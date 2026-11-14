from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from typing import TypeVar, final

from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.world_store import WorldSession, WorldStore
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException

_Result = TypeVar("_Result")


@final
class CommandScope:
    def __init__(self, store: WorldStore, distributor: CommittedEventsDistributor) -> None:
        self._store = store
        self._distributor = distributor
        self._refusals: Counter[str] = Counter()

    @property
    def refusals(self) -> Mapping[str, int]:
        return dict(self._refusals)

    def run(self, work: Callable[[WorldSession], _Result]) -> _Result:
        session = self._store.session()
        try:
            result = work(session)
        except GameWorldDomainException as refusal:
            session.roll_back()
            self._refusals[refusal.error_code] += 1
            raise
        except BaseException:
            session.roll_back()
            raise
        self._distributor.distribute(session.commit())
        return result
