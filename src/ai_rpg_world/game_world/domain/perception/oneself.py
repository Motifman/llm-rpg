from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

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
class Oneself:
    belongings: tuple[CarriedKind, ...]
    hp: HitPoints
    hunger: HungerAmount
    hunger_limit: HungerAmount
    fatigue: FatigueAmount
    fatigue_limit: FatigueAmount
    fatigue_felt: DisplayName | None

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
                tier=wording.hit_points_tiers.name_of(self.hp).text, current=self.hp.current, maximum=self.hp.maximum
            ),
            wording.hunger.format(
                tier=needs.name_of(self.hunger.value, self.hunger_limit.value).text,
                amount=self.hunger.value,
                limit=self.hunger_limit.value,
            ),
            wording.fatigue.format(
                tier=needs.name_of(self.fatigue.value, self.fatigue_limit.value).text,
                amount=self.fatigue.value,
                limit=self.fatigue_limit.value,
            ),
            *([] if self.fatigue_felt is None else [wording.fatigue_felt.format(feel=self.fatigue_felt.text)]),
        ]
