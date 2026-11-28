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
from ai_rpg_world.game_world.domain.people import PeopleAsSeen, PeopleSeenBy, PersonRef
from ai_rpg_world.game_world.domain.perception.names_in_world import NamesInWorld
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
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
        self.people = people
        self._items_seen_on = items_seen_on

    @classmethod
    def for_person(cls, actor: PersonId, facts: WorldFacts, design: WorldDesign) -> ChoiceWording:
        seen = VisibleSurroundings.seen_by_person(actor, facts, design)
        return cls.seeing(actor, design, facts, PeopleSeenBy.in_world(actor, facts), seen)

    @classmethod
    def seeing(
        cls,
        actor: PersonId,
        design: WorldDesign,
        facts: WorldFacts,
        people: PeopleAsSeen,
        seen: VisibleSurroundings | NothingInView,
    ) -> ChoiceWording:
        if isinstance(seen, NothingInView):
            return cls(actor, design, facts, people, {})
        register = facts.people_register()
        by_handle = {register.handle_of(person): person for person in facts.people()}
        items_seen_on = {
            by_handle[shown.person.handle]: shown.visible_items
            for shown in (*seen.people, *seen.bodies)
            if isinstance(shown.person, PersonRef)
        }
        return cls(actor, design, facts, people, items_seen_on)

    def person(self, person: PersonId) -> PersonRef:
        return self.people.ref_of(person)

    def someone_in_the_dark(self) -> DisplayName:
        return _SOMEONE_IN_THE_DARK

    def abstain(self) -> DisplayName:
        return _ABSTAIN

    def item(self, value: OfferedValue, item: ItemInstanceId) -> OfferedStep:
        return OfferedStep(value, NamesInWorld(self.facts).item_name(item), item)

    # 品物の引数がどの品物を指すかは、まだ宣言に書かれていない (#2247)。人への操作は相手の見えている持ち物、
    # 暗がりの相手は持ち物が見えないので無し、ほかは自分の持ち物から出す。決め方を変えるときはこの 3 つだけを直す。
    def arguments_on_things(self, declared: tuple[ArgumentDeclaration, ...]) -> tuple[OfferedInput, ...]:
        return self._arguments(declared, self.facts.inventory(self._actor).items())

    def arguments_toward(self, declared: tuple[ArgumentDeclaration, ...], person: PersonId) -> tuple[OfferedInput, ...]:
        return self._arguments(declared, self._items_seen_on.get(person, ()))

    def arguments_toward_unseen(self, declared: tuple[ArgumentDeclaration, ...]) -> tuple[OfferedInput, ...]:
        return self._arguments(declared, ())

    def _arguments(
        self, declared: tuple[ArgumentDeclaration, ...], items: tuple[ItemInstanceId, ...]
    ) -> tuple[OfferedInput, ...]:
        return tuple(self._argument(argument, items) for argument in declared)

    def _argument(self, argument: ArgumentDeclaration, items: tuple[ItemInstanceId, ...]) -> OfferedInput:
        value = OfferedValue(argument.name.value, argument.name.value)
        if isinstance(argument.kind, TextArgument):
            return OfferedFreeText(value, writes=argument.kind.writes)
        return OfferedItemPick(value, tuple(self.item(value, item) for item in items), argument.kind.writes)
