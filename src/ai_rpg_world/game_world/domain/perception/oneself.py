from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_and_clock_time import DayAndClockTime
from ai_rpg_world.game_world.domain.people import PeopleSeenBy, PersonRef, TextWithAssignedPeople, Unidentified
from ai_rpg_world.game_world.domain.person import Busy
from ai_rpg_world.game_world.domain.person.shown_body import BodyChange
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    FatigueAmount,
    HitPoints,
    HungerAmount,
    ItemSpecId,
    PersonId,
)

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SceneTexts
    from ai_rpg_world.game_world.domain.declaration.time_and_weather.clock_wording import ClockWording


@final
@dataclass(frozen=True)
class CarriedKind:
    spec: ItemSpecId
    name: DisplayName
    description: DescriptionText
    count: int
    held: bool


@final
@dataclass(frozen=True)
class DoingNow:
    """``until`` が None なのは、昼夜の無い世界で時刻を書けないとき。"""

    text: TextWithAssignedPeople
    until: DayAndClockTime | None


@final
@dataclass(frozen=True)
class NotDoingAnything:
    pass


@final
@dataclass(frozen=True)
class Oneself:
    belongings: tuple[CarriedKind, ...]
    hp: HitPoints
    hunger: HungerAmount
    hunger_limit: HungerAmount
    fatigue: FatigueAmount
    fatigue_limit: FatigueAmount
    fatigue_felt: DisplayName | None
    change: BodyChange
    doing: DoingNow | NotDoingAnything

    @classmethod
    def of(cls, person: PersonId, facts: WorldFacts) -> Oneself:
        inventory = facts.inventory(person)
        vitals = facts.vitals(person)
        rules = facts.rules()
        held = set(inventory.held_items())
        # 同じ種類でも手に持っている物と荷の中の物は別の行にする。手に持っているかで、そのまま使えるかが変わるため
        counts: dict[tuple[ItemSpecId, bool], int] = {}
        for item in inventory.items():
            key = (facts.item(item).spec_id, item in held)
            counts[key] = counts.get(key, 0) + 1
        specs = {spec: facts.nouns().item_spec_of(spec) for spec, _ in counts}
        return cls(
            belongings=tuple(
                CarriedKind(
                    spec=spec,
                    name=specs[spec].name,
                    description=specs[spec].description,
                    count=count,
                    held=is_held,
                )
                for (spec, is_held), count in counts.items()
            ),
            hp=vitals.hp(),
            hunger=vitals.hunger(),
            hunger_limit=rules.hunger.limit,
            fatigue=vitals.fatigue(),
            fatigue_limit=rules.fatigue.limit,
            fatigue_felt=rules.fatigue.level_of(vitals.fatigue()).felt_as,
            change=vitals.change_since_shown(),
            doing=_doing_now(person, facts),
        )

    def lines(self, wording: SceneTexts) -> list[str]:
        return [*self._belonging_lines(wording), *self._body_lines(wording)]

    def _belonging_lines(self, wording: SceneTexts) -> list[str]:
        if not self.belongings:
            return []
        return [
            wording.belongings,
            *(
                wording.belonging.format(
                    item=kind.name.text,
                    count=wording.belonging_count.format(count=kind.count) if kind.count > 1 else "",
                    description=wording.belonging_description.format(description=kind.description.text),
                    held=wording.belonging_held if kind.held else "",
                )
                for kind in self.belongings
            ),
        ]

    def _body_lines(self, wording: SceneTexts) -> list[str]:
        needs = wording.need_tiers
        return [
            wording.body,
            wording.hit_points.format(
                tier=wording.hit_points_tiers.name_of(self.hp).text,
                current=self.hp.current,
                maximum=self.hp.maximum,
                change=_change(self.change.hp, wording),
            ),
            wording.hunger.format(
                tier=needs.name_of(self.hunger.value, self.hunger_limit.value).text,
                amount=self.hunger.value,
                limit=self.hunger_limit.value,
                change=_change(self.change.hunger, wording),
            ),
            wording.fatigue.format(
                tier=needs.name_of(self.fatigue.value, self.fatigue_limit.value).text,
                amount=self.fatigue.value,
                limit=self.fatigue_limit.value,
                change=_change(self.change.fatigue, wording),
            ),
            *([] if self.fatigue_felt is None else [wording.fatigue_felt.format(feel=self.fatigue_felt.text)]),
        ]

    def doing_lines(
        self, wording: SceneTexts, clock: ClockWording, holes: dict[str, PersonRef | Unidentified]
    ) -> list[str]:
        """人の穴の名前を場面のほかの人と重ならないものに変え、``holes`` に足した行を、format の書き方で返す。"""
        if isinstance(self.doing, NotDoingAnything):
            return []
        doing = _rekeyed(self.doing.text, "doing_", holes)
        until = "" if self.doing.until is None else wording.doing_until.format(time=clock.display(self.doing.until))
        return [_escaped(wording.doing).replace("{{doing}}", doing).replace("{{until}}", _escaped(until))]


def _doing_now(person: PersonId, facts: WorldFacts) -> DoingNow | NotDoingAnything:
    busy = facts.vitals(person).doing_at(facts.now())
    if not isinstance(busy, Busy):
        return NotDoingAnything()
    day_night = facts.day_night()
    until = None if isinstance(day_night, NoDayNight) else day_night.day_and_clock_time_at(busy.until)
    return DoingNow(text=busy.doing.seen_by(PeopleSeenBy.in_world(person, facts)), until=until)


def _rekeyed(text: TextWithAssignedPeople, prefix: str, holes: dict[str, PersonRef | Unidentified]) -> str:
    rebuilt: list[str] = []
    for literal, name, _, _ in Formatter().parse(text.template):
        rebuilt.append(_escaped(literal))
        if name is not None:
            holes[f"{prefix}{name}"] = text.people[name]
            rebuilt.append(f"{{{prefix}{name}}}")
    return "".join(rebuilt)


def _escaped(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def _change(amount: int, wording: SceneTexts) -> str:
    if amount == 0:
        return ""
    return wording.body_change.format(change=f"{amount:+d}")
