from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeVar, final

from typing_extensions import Self

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.action.action_arguments import ActionArguments, TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActionAttempt,
    ActorRequirement,
    CopresenceRequirement,
    Exertion,
    LivingOnly,
    UsesBody,
)
from ai_rpg_world.game_world.domain.action.action_entrances import ActionEntrances
from ai_rpg_world.game_world.domain.action.action_fixed_before_effect import ActionFixedBeforeEffect
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NoOneFoundInTheDark
from ai_rpg_world.game_world.domain.action.offered_action import OfferedAction
from ai_rpg_world.game_world.domain.action.witnessed_act import WitnessedAct
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ArgumentNotInTriggerException,
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import TextAboutPeople
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, ItemSpecId, ObjectId, PersonId, SpotId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.whereabouts import PersonBody

_Reply = TypeVar("_Reply")


@final
@dataclass(frozen=True)
class ActionAttemptForTests(ActionAttempt):
    actor_id: PersonId
    target: PersonId | None = None
    item: ItemInstanceId | None = None
    arguments: ActionArguments = field(default_factory=lambda: MappingProxyType({}))
    action_kind: ActionKind = ActionKind.INTERACT_WITH_PERSON
    requirement: ActorRequirement = field(default_factory=LivingOnly)
    copresence: tuple[CopresenceRequirement, ...] = ()
    body_use: Exertion = field(default_factory=UsesBody)
    startable_while_busy: bool = False

    def __post_init__(self) -> None:
        arguments: Mapping[ArgumentName, TextArgumentValue | ItemInstanceId] = MappingProxyType(dict(self.arguments))
        object.__setattr__(self, "arguments", arguments)

    @property
    def actor(self) -> PersonId:
        return self.actor_id

    def kind(self) -> ActionKind:
        return self.action_kind

    def actor_requirement(self) -> ActorRequirement:
        return self.requirement

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return self.copresence

    def exertion(self) -> Exertion:
        return self.body_use

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.ACTOR:
            return self.actor_id
        if kind is SubjectKind.TARGET and self.target is not None:
            return self.target
        raise SubjectNotInTriggerException(f"{self!r} does not answer {kind.name}")

    def items_handled(self) -> tuple[ItemInstanceId, ...]:
        return () if self.item is None else (self.item,)

    def this_item(self) -> ItemInstanceId:
        if self.item is None:
            raise ItemNotInTriggerException(f"{self!r} does not answer the item")
        return self.item

    def acting_person(self) -> PersonId | NoActingPerson:
        return self.actor_id

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId:
        if name not in self.arguments:
            raise ArgumentNotInTriggerException(f"{self!r} does not answer the argument {name.value!r}")
        return self.arguments[name]

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return fall_cause_from(self.acting_person(), victim)

    def can_start_while_busy(self) -> bool:
        return self.startable_while_busy

    def is_waiting(self) -> bool:
        return self.action_kind is ActionKind.WAIT

    def is_allowed_in(self, stage: WorldStageDeclaration | NoWorldStages) -> bool:
        return stage.allows(self.action_kind)

    def done_as(self) -> frozenset[ActionKind | InteractionId]:
        return frozenset({self.action_kind})

    def operates(self, obj: ObjectId, interaction: InteractionId) -> bool:
        return False

    def hidden_while_unmet(self) -> bool:
        return False

    def aimed_in(self, facts: WorldFacts) -> Self | NoOneFoundInTheDark:
        return self

    def witnessed_in(self, design: WorldDesign, situation: ActorSituation) -> WitnessedAct:
        raise NotImplementedError(f"{self!r} is not witnessed in tests that use it")

    def done_text_in(self, design: WorldDesign, situation: ActorSituation) -> TextAboutPeople:
        raise NotImplementedError(f"{self!r} is not carried out in tests that use it")

    def summary_in(self, design: WorldDesign, situation: ActorSituation) -> TextAboutPeople:
        raise NotImplementedError(f"{self!r} is not summarized in tests that use it")

    def ongoing_in(self, design: WorldDesign, situation: ActorSituation) -> TextAboutPeople:
        raise NotImplementedError(f"{self!r} is not carried out in tests that use it")

    def fixed_before_effect(self, design: WorldDesign, facts: WorldFacts) -> ActionFixedBeforeEffect:
        raise NotImplementedError(f"{self!r} is not carried out in tests that use it")

    def offered_as(self, wording: ChoiceWording) -> OfferedAction:
        raise NotImplementedError(f"{self!r} is not offered in tests that use it")

    def chosen_with(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> Self:
        raise NotImplementedError(f"{self!r} is not chosen in tests that use it")

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        raise NotImplementedError(f"{self!r} is not entered in tests that use it")


def situation_for_tests() -> ActorSituation:
    return ActorSituation(at_spot=SpotId("somewhere"), actor_as=PersonBody(PersonId("alice")), item_specs={})
