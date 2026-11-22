from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.lighting import Lighting

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
    from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
    from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration, NoDayNight
    from ai_rpg_world.game_world.domain.value_object import SpotId


@final
@dataclass(frozen=True)
class WorldMapWording:
    place: str
    place_without_exits: str
    exit: str
    joiner: str
    minutes: str
    turns: str
    lighting: Mapping[Lighting, str]

    def __post_init__(self) -> None:
        missing = sorted(lighting.name for lighting in Lighting if lighting not in self.lighting)
        if missing:
            raise ValueOutOfRangeException(f"WorldMapWording.lighting lacks {missing}")
        object.__setattr__(self, "lighting", MappingProxyType(dict(self.lighting)))
        # 書けない書き方を、地図を描くときではなく、読み込みのときに断る
        try:
            self.place.format(spot="", lighting="", exits="")
            self.place_without_exits.format(spot="", lighting="")
            self.exit.format(spot="", time="")
            self.minutes.format(minutes=0)
            self.turns.format(turns=0)
        except (KeyError, IndexError, ValueError, AttributeError, TypeError) as error:
            raise ValueOutOfRangeException(f"WorldMapWording names something it cannot fill: {error}") from error


@final
@dataclass(frozen=True)
class _Exit:
    to: SpotDeclaration
    ticks: int


@final
@dataclass(frozen=True)
class WorldMap:
    places: tuple[tuple[SpotDeclaration, tuple[_Exit, ...]], ...]

    @classmethod
    def drawn_from(cls, nouns: DeclaredNouns) -> WorldMap:
        spots = nouns.all_spots()
        shortest: dict[SpotId, dict[SpotId, int]] = {spot.spot_id: {} for spot in spots}

        def note(start: SpotId, end: SpotId, ticks: int) -> None:
            # 同じ相手へ道が何本もあるなら、短いほうを載せる。行き来にどれだけかかるかを推し量る材料なので
            if start in shortest and (end not in shortest[start] or ticks < shortest[start][end]):
                shortest[start][end] = ticks

        # 始まった時点で隠れている通路は載せない。地図は run のあいだ変わらず、見つける前から分かってしまうため
        for passage in nouns.all_passages():
            if passage.hidden_until_revealed:
                continue
            start, end = passage.ends
            note(start, end, passage.travel_ticks.value)
            if passage.two_way:
                note(end, start, passage.travel_ticks.value)
        by_id = {spot.spot_id: spot for spot in spots}
        return cls(
            tuple(
                (
                    spot,
                    tuple(
                        _Exit(by_id[to], ticks)
                        for to, ticks in sorted(
                            shortest[spot.spot_id].items(), key=lambda entry: (entry[1], by_id[entry[0]].name.text)
                        )
                    ),
                )
                for spot in spots
            )
        )

    def written_with(self, wording: WorldMapWording, day_night: DayNightDeclaration | NoDayNight) -> str:
        lines = []
        for spot, exits in self.places:
            lighting = wording.lighting[spot.atmosphere.lighting]
            if not exits:
                lines.append(wording.place_without_exits.format(spot=spot.name.text, lighting=lighting))
                continue
            written_exits = wording.joiner.join(
                wording.exit.format(spot=way.to.name.text, time=day_night.travel_time_text(way.ticks, wording))
                for way in exits
            )
            lines.append(wording.place.format(spot=spot.name.text, lighting=lighting, exits=written_exits))
        return "\n".join(lines)
