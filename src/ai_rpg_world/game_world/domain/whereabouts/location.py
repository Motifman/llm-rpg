from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration
from ai_rpg_world.game_world.domain.sound.hearing_values import HearingValues
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.sound.sound_level import SoundLevel
from ai_rpg_world.game_world.domain.sound.sound_network import NotReached, SoundReach
from ai_rpg_world.game_world.domain.value_object import PassageId, SpotId, SpotSectionId, Ticks
from ai_rpg_world.game_world.domain.whereabouts.route import Route


@final
@dataclass(frozen=True)
class OpenArea:
    pass


@final
@dataclass(frozen=True)
class AtSpot:
    spot: SpotId
    section: SpotSectionId | OpenArea

    def is_at(self, spot: SpotId) -> bool:
        return self.spot == spot

    def sound_level_from(
        self, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues
    ) -> SoundLevel | NotReached:
        return reach.level_at(self.spot)


@final
@dataclass(frozen=True)
class TravelInProgress:
    route: Route
    passage_index: int
    ticks_left_on_passage: Ticks
    departed_from: SpotId

    def is_at(self, spot: SpotId) -> bool:
        return False

    def position(self) -> TravelPosition:
        return TravelPosition(
            route_start=self.route.start,
            route_passages=tuple(passage.passage_id for passage in self.route.passages),
            passage_index=self.passage_index,
            ticks_left_on_passage=self.ticks_left_on_passage,
            departed_from=self.departed_from,
        )

    def sound_level_from(
        self, origin: SpotId, loudness: Loudness, reach: SoundReach, values: HearingValues
    ) -> SoundLevel | NotReached:
        if loudness not in _HEARD_WHILE_TRAVELLING or origin not in self._ends_of_current_passage():
            return NotReached()
        # 通路の上はどの場所でもないので、端の場所から 1 つ隣にいるものとして聞く。
        return values.level_of(loudness).weakened_by(values.loss_per_passage)

    def _ends_of_current_passage(self) -> tuple[SpotId, SpotId]:
        index = self.passage_index
        start = self.route.start if index == 0 else self.route.end_of_passage(index - 1)
        return (start, self.route.end_of_passage(index))


@final
@dataclass(frozen=True)
class TravelPosition:
    route_start: SpotId
    route_passages: tuple[PassageId, ...]
    passage_index: int
    ticks_left_on_passage: Ticks
    departed_from: SpotId

    def resumed_on(self, passages: tuple[PassageDeclaration, ...]) -> TravelInProgress:
        return TravelInProgress(
            route=Route(start=self.route_start, passages=passages),
            passage_index=self.passage_index,
            ticks_left_on_passage=self.ticks_left_on_passage,
            departed_from=self.departed_from,
        )


_HEARD_WHILE_TRAVELLING = frozenset({Loudness.LOUD, Loudness.VERY_LOUD})


Location = AtSpot | TravelInProgress
