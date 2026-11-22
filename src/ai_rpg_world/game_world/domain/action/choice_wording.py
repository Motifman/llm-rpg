from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration, TextArgument
from ai_rpg_world.game_world.domain.action.offered_action import (
    OfferedFreeText,
    OfferedInput,
    OfferedItemPick,
    OfferedStep,
    OfferedValue,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PeopleAsSeen, PersonRef
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign

_SOMEONE_IN_THE_DARK = DisplayName("暗がりの誰か")
_ABSTAIN = DisplayName("棄権する")


@final
class ChoiceWording:
    def __init__(
        self,
        actor: PersonId,
        design: WorldDesign,
        facts: WorldFacts,
        people: PeopleAsSeen,
        items_seen_on: Mapping[PersonId, tuple[ItemInstanceId, ...]],
    ) -> None:
        self._actor = actor
        self.design = design
        self.facts = facts
        self._people = people
        self._items_seen_on = items_seen_on

    def person(self, person: PersonId) -> PersonRef:
        return self._people.ref_of(person)

    def someone_in_the_dark(self) -> DisplayName:
        return _SOMEONE_IN_THE_DARK

    def abstain(self) -> DisplayName:
        return _ABSTAIN

    def item(self, value: OfferedValue, item: ItemInstanceId) -> OfferedStep:
        return OfferedStep(value, self.design.nouns.item_spec_of(self.facts.item(item).spec_id).name, item)

    def arguments(
        self, declared: tuple[ArgumentDeclaration, ...], toward: PersonId | None = None
    ) -> tuple[OfferedInput, ...]:
        return tuple(self._argument(argument, toward) for argument in declared)

    def _argument(self, argument: ArgumentDeclaration, toward: PersonId | None) -> OfferedInput:
        value = OfferedValue(argument.name.value, argument.name.value)
        if isinstance(argument.kind, TextArgument):
            return OfferedFreeText(value)
        # 品物の引数がどの品物を指すかは宣言に書かれていない。人への操作は相手の見えている持ち物、ほかは自分の持ち物から出す。
        owner_items = (
            self.facts.inventory(self._actor).items() if toward is None else self._items_seen_on.get(toward, ())
        )
        return OfferedItemPick(value, tuple(self.item(value, item) for item in owner_items))
