from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, TypeVar, final

from typing_extensions import Self, assert_never

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.action.action_arguments import (
    ArgumentsNotChosen,
    ChosenArguments,
    TextArgumentValue,
)
from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActorRequirement,
    CopresenceRequirement,
    Exertion,
    WithCarriedItem,
    WithObject,
    WithPerson,
)
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NoOneFoundInTheDark
from ai_rpg_world.game_world.domain.action.declared_interaction import DeclaredInteraction
from ai_rpg_world.game_world.domain.action.manner import Manner
from ai_rpg_world.game_world.domain.action.offered_action import (
    HOW,
    TARGET,
    ActionChoiceKind,
    OfferedAction,
    OfferedStep,
)
from ai_rpg_world.game_world.domain.action.trigger_answers_nothing_by_default import TriggerAnswersNothingByDefault
from ai_rpg_world.game_world.domain.action.witnessed_act import WitnessedAct, item_names
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.failure_texts import people_in_text
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.object_and_item import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.verb.action_texts import ActionTextKey
from ai_rpg_world.game_world.domain.exception.action_exception import (
    UnseenTargetNotAllowedException,
)
from ai_rpg_world.game_world.domain.exception.perception_exception import PerceivedItemSpecNotGivenException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.perception import Noise, NoTarget
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, ItemSpecId, ObjectId, PersonId, Ticks
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.whereabouts import PersonBody

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_entrances import ActionEntrances
    from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.verb.interaction_declaration import InteractionDeclaration
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
    from ai_rpg_world.game_world.domain.people import NameInText, TextAboutPeople

_Reply = TypeVar("_Reply")


@final
@dataclass(frozen=True)
class SomeoneInTheDark:
    def chosen_near(self, actor: PersonId, facts: WorldFacts) -> PersonId | NoOneFoundInTheDark:
        whereabouts = facts.whereabouts()
        here = facts.vitals(actor).occupant_in_world(facts.rules().departed_persons_act)
        candidates = [
            person
            for person in facts.people()
            if person != actor
            and not facts.vitals(person).is_dead()
            and whereabouts.are_together(here, PersonBody(person))
        ]
        if not candidates:
            return NoOneFoundInTheDark()
        return candidates[int(facts.random().next_fraction() * len(candidates))]


class _InteractionAttempt(TriggerAnswersNothingByDefault, ABC):
    actor: PersonId
    interaction: DeclaredInteraction
    arguments: ChosenArguments | ArgumentsNotChosen
    manner: Manner

    @abstractmethod
    def kind(self) -> ActionKind: ...

    @abstractmethod
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]: ...

    @abstractmethod
    def offered_as(self, wording: ChoiceWording) -> OfferedAction: ...

    @abstractmethod
    def chosen_with(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> Self: ...

    @abstractmethod
    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply: ...

    def __post_init__(self) -> None:
        self.manner.require_allowed_by(self.interaction)
        self.arguments.require_declared_by(self.interaction)

    def exertion(self) -> Exertion:
        return self.interaction.exertion

    def actor_requirement(self) -> ActorRequirement:
        return self.interaction.actor_requirement

    def can_start_while_busy(self) -> bool:
        return False

    def is_allowed_in(self, stage: WorldStageDeclaration | NoWorldStages) -> bool:
        return stage.allows_interaction(self.interaction.interaction_id)

    def items_handled(self) -> tuple[ItemInstanceId, ...]:
        return self.arguments.items()

    def done_as(self) -> frozenset[ActionKind | InteractionId]:
        return frozenset({self.kind(), self.interaction.interaction_id})

    def operates(self, obj: ObjectId, interaction: InteractionId) -> bool:
        return False

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.ACTOR:
            return self.actor
        return super().person_as(kind)

    def acting_person(self) -> PersonId | NoActingPerson:
        return self.actor

    def done_text_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> TextAboutPeople:
        return people_in_text(self._declared(design, item_specs).success_text, self)

    def summary_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> TextAboutPeople:
        how = {"how": self._declared(design, item_specs).display_label}
        target = self._witnessed_target()
        people = {"actor": self.actor} | ({"target": target} if isinstance(target, PersonId) else {})
        summary = design.action_texts.summary_of(self._summary_key())
        return summary.about_named(people, {**self._things_named(design, item_specs), **how})

    @abstractmethod
    def _summary_key(self) -> ActionTextKey: ...

    def _things_named(
        self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]
    ) -> Mapping[str, NameInText]:
        return {}

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId:
        return self.arguments.value_of(name, self)

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return fall_cause_from(self.acting_person(), victim)

    def witnessed_in(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> WitnessedAct:
        return WitnessedAct(
            perception=self._declared(design, item_specs).perceived_as,
            names={},
            target=self._witnessed_target(),
            manner=self.manner,
            source=Noise(),
        )

    @abstractmethod
    def _declared(
        self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]
    ) -> InteractionDeclaration: ...

    def _witnessed_target(self) -> PersonId | NoTarget:
        return NoTarget()

    def aimed_in(self, facts: WorldFacts) -> Self | NoOneFoundInTheDark:
        return self

    def unmet_precondition(self, design: WorldDesign, facts: WorldFacts) -> FailureReason | HiddenFailure | None:
        return self.arguments.unmet(self._declared_now(design, facts).precondition, facts, self)

    def take_effect(self, design: WorldDesign, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        self.arguments.require_chosen(self.interaction)
        declared = self._declared_now(design, facts)
        declared.effect.apply(facts, world, self)
        return facts.rules().duration_of(self.kind(), declared.duration)

    def _declared_now(self, design: WorldDesign, facts: WorldFacts) -> InteractionDeclaration:
        return self._declared(design, {})


@final
@dataclass(frozen=True)
class ObjectInteractionAttempt(_InteractionAttempt):
    actor: PersonId
    obj: ObjectDeclaration
    interaction: DeclaredInteraction
    arguments: ChosenArguments | ArgumentsNotChosen
    manner: Manner

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.interact_with_object(self)

    def chosen_with(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> Self:
        return replace(self, arguments=self.arguments.chosen_as(values))

    def kind(self) -> ActionKind:
        return ActionKind.INTERACT_WITH_OBJECT

    def _summary_key(self) -> ActionTextKey:
        return ActionTextKey.INTERACT_WITH_OBJECT

    def _things_named(
        self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]
    ) -> Mapping[str, NameInText]:
        return {"object": self.obj.name}

    def _declared(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> InteractionDeclaration:
        return design.interaction_on_object(self.obj.object_id, self.interaction.interaction_id)

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithObject(self.obj.object_id),)

    def operates(self, obj: ObjectId, interaction: InteractionId) -> bool:
        return (self.obj.object_id, self.interaction.interaction_id) == (obj, interaction)

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        declared = wording.design.interaction_on_object(self.obj.object_id, self.interaction.interaction_id)
        return OfferedAction(
            ActionChoiceKind.INTERACT,
            (OfferedStep(TARGET, self.obj.name), OfferedStep(HOW, declared.display_label)),
            wording.arguments_on_things(declared.arguments),
        )


@final
@dataclass(frozen=True)
class CarriedItemInteractionAttempt(_InteractionAttempt):
    actor: PersonId
    item: ItemInstanceId
    interaction: DeclaredInteraction
    arguments: ChosenArguments | ArgumentsNotChosen
    manner: Manner

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.interact_with_carried_item(self)

    def chosen_with(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> Self:
        return replace(self, arguments=self.arguments.chosen_as(values))

    def kind(self) -> ActionKind:
        return ActionKind.INTERACT_WITH_CARRIED_ITEM

    def _summary_key(self) -> ActionTextKey:
        return ActionTextKey.INTERACT_WITH_CARRIED_ITEM

    def _things_named(
        self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]
    ) -> Mapping[str, NameInText]:
        return {"item": item_names((self.item,), item_specs, design)}

    def _declared(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> InteractionDeclaration:
        if self.item not in item_specs:
            raise PerceivedItemSpecNotGivenException(f"the kind of {self.item.value} was not read when it was handled")
        return design.interaction_on_item(item_specs[self.item], self.interaction.interaction_id)

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithCarriedItem(self.item),)

    def _declared_now(self, design: WorldDesign, facts: WorldFacts) -> InteractionDeclaration:
        return self._declared(design, {self.item: facts.item(self.item).spec_id})

    def this_item(self) -> ItemInstanceId:
        return self.item

    def items_handled(self) -> tuple[ItemInstanceId, ...]:
        return (self.item, *super().items_handled())

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        target = wording.item(TARGET, self.item)
        declared = self._declared_now(wording.design, wording.facts)
        return OfferedAction(
            ActionChoiceKind.INTERACT,
            (target, OfferedStep(HOW, declared.display_label)),
            wording.arguments_on_things(declared.arguments),
        )


@final
@dataclass(frozen=True)
class PersonInteractionAttempt(_InteractionAttempt):
    actor: PersonId
    target: PersonId | SomeoneInTheDark
    interaction: DeclaredInteraction
    arguments: ChosenArguments | ArgumentsNotChosen
    manner: Manner

    def __post_init__(self) -> None:
        if isinstance(self.target, SomeoneInTheDark) and not self.interaction.reaches_unseen:
            raise UnseenTargetNotAllowedException(
                f"{self.interaction.interaction_id.value} cannot be aimed at someone in the dark"
            )
        super().__post_init__()

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.interact_with_person(self)

    def chosen_with(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> Self:
        return replace(self, arguments=self.arguments.chosen_as(values))

    def kind(self) -> ActionKind:
        return ActionKind.INTERACT_WITH_PERSON

    def _summary_key(self) -> ActionTextKey:
        # 暗がりで相手を選ぶ前に断られると、相手の名前が無い
        if isinstance(self.target, SomeoneInTheDark):
            return ActionTextKey.INTERACT_WITH_SOMEONE_IN_THE_DARK
        return ActionTextKey.INTERACT_WITH_PERSON

    def aimed_in(self, facts: WorldFacts) -> Self | NoOneFoundInTheDark:
        if isinstance(self.target, PersonId):
            return self
        chosen = self.target.chosen_near(self.actor, facts)
        if isinstance(chosen, NoOneFoundInTheDark):
            return chosen
        return replace(self, target=chosen)

    def _declared(self, design: WorldDesign, item_specs: Mapping[ItemInstanceId, ItemSpecId]) -> InteractionDeclaration:
        return design.person_interaction(self.interaction.interaction_id)

    def _witnessed_target(self) -> PersonId | NoTarget:
        if isinstance(self.target, SomeoneInTheDark):
            return NoTarget()
        if isinstance(self.target, PersonId):
            return self.target
        assert_never(self.target)

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        if isinstance(self.target, SomeoneInTheDark):
            return ()
        return (WithPerson(self.target),)

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.TARGET and isinstance(self.target, PersonId):
            return self.target
        return super().person_as(kind)

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        declared = wording.design.person_interaction(self.interaction.interaction_id)
        how = OfferedStep(HOW, declared.display_label)
        if isinstance(self.target, SomeoneInTheDark):
            target = OfferedStep(TARGET, wording.someone_in_the_dark())
            return OfferedAction(
                ActionChoiceKind.INTERACT, (target, how), wording.arguments_toward_unseen(declared.arguments)
            )
        target = OfferedStep(TARGET, wording.person(self.target))
        return OfferedAction(
            ActionChoiceKind.INTERACT, (target, how), wording.arguments_toward(declared.arguments, self.target)
        )
