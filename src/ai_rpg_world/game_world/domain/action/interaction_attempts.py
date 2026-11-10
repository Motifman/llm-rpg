from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.action.action_arguments import ActionArguments, TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActorRequirement,
    CopresenceRequirement,
    Exertion,
    WithObject,
    WithPerson,
)
from ai_rpg_world.game_world.domain.action.declared_interaction import DeclaredInteraction
from ai_rpg_world.game_world.domain.action.manner import Manner
from ai_rpg_world.game_world.domain.action.trigger_answers_nothing_by_default import TriggerAnswersNothingByDefault
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.object_and_item import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.exception.action_exception import (
    ArgumentsDoNotMatchDeclarationException,
    UnseenTargetNotAllowedException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, PersonId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName


@final
@dataclass(frozen=True)
class SomeoneInTheDark:
    pass


class _InteractionAttempt(TriggerAnswersNothingByDefault, ABC):
    actor: PersonId
    interaction: DeclaredInteraction
    arguments: ActionArguments
    manner: Manner

    @abstractmethod
    def kind(self) -> ActionKind: ...

    def __post_init__(self) -> None:
        self.manner.require_allowed_by(self.interaction)
        self._require_declared_arguments()
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))

    def _require_declared_arguments(self) -> None:
        declared = {declaration.name: declaration for declaration in self.interaction.arguments}
        if declared.keys() != self.arguments.keys() or not all(
            declared[name].accepts(value) for name, value in self.arguments.items()
        ):
            raise ArgumentsDoNotMatchDeclarationException(
                f"{self.interaction.interaction_id.value} declares"
                f" {sorted(name.value for name in declared)} but got {sorted(name.value for name in self.arguments)}"
            )

    def exertion(self) -> Exertion:
        return self.interaction.exertion

    def actor_requirement(self) -> ActorRequirement:
        return self.interaction.actor_requirement

    def can_start_while_busy(self) -> bool:
        return False

    def is_allowed_in(self, stage: WorldStageDeclaration | NoWorldStages) -> bool:
        return stage.allows_interaction(self.interaction.interaction_id)

    def done_as(self) -> frozenset[ActionKind | InteractionId]:
        return frozenset({self.kind(), self.interaction.interaction_id})

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.ACTOR:
            return self.actor
        return super().person_as(kind)

    def acting_person(self) -> PersonId | NoActingPerson:
        return self.actor

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId:
        if name in self.arguments:
            return self.arguments[name]
        return super().argument(name)

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return fall_cause_from(self.acting_person(), victim)


@final
@dataclass(frozen=True)
class ObjectInteractionAttempt(_InteractionAttempt):
    actor: PersonId
    obj: ObjectDeclaration
    interaction: DeclaredInteraction
    arguments: ActionArguments
    manner: Manner

    def kind(self) -> ActionKind:
        return ActionKind.INTERACT_WITH_OBJECT

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return (WithObject(self.obj.object_id),)


@final
@dataclass(frozen=True)
class CarriedItemInteractionAttempt(_InteractionAttempt):
    actor: PersonId
    item: ItemInstanceId
    interaction: DeclaredInteraction
    arguments: ActionArguments
    manner: Manner

    def kind(self) -> ActionKind:
        return ActionKind.INTERACT_WITH_CARRIED_ITEM

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return ()

    def this_item(self) -> ItemInstanceId:
        return self.item


@final
@dataclass(frozen=True)
class PersonInteractionAttempt(_InteractionAttempt):
    actor: PersonId
    target: PersonId | SomeoneInTheDark
    interaction: DeclaredInteraction
    arguments: ActionArguments
    manner: Manner

    def __post_init__(self) -> None:
        if isinstance(self.target, SomeoneInTheDark) and not self.interaction.reaches_unseen:
            raise UnseenTargetNotAllowedException(
                f"{self.interaction.interaction_id.value} cannot be aimed at someone in the dark"
            )
        super().__post_init__()

    def kind(self) -> ActionKind:
        return ActionKind.INTERACT_WITH_PERSON

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        if isinstance(self.target, SomeoneInTheDark):
            return ()
        return (WithPerson(self.target),)

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.TARGET and isinstance(self.target, PersonId):
            return self.target
        return super().person_as(kind)
