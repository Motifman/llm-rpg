from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition import AwaitsArguments, Condition, FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.exception.action_argument_exception import BlankTextArgumentException
from ai_rpg_world.game_world.domain.exception.action_exception import (
    ArgumentsDoNotMatchDeclarationException,
    ArgumentsNotChosenException,
)
from ai_rpg_world.game_world.domain.exception.trigger_exception import ArgumentNotInTriggerException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.declared_interaction import DeclaredInteraction
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class TextArgumentValue:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankTextArgumentException(f"TextArgumentValue must be non-blank, got {self.text!r}")


ActionArguments = Mapping[ArgumentName, TextArgumentValue | ItemInstanceId]


@final
@dataclass(frozen=True)
class ChosenArguments:
    values: ActionArguments = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def require_declared_by(self, interaction: DeclaredInteraction) -> None:
        declared = {declaration.name: declaration for declaration in interaction.arguments}
        if declared.keys() != self.values.keys() or not all(
            declared[name].accepts(value) for name, value in self.values.items()
        ):
            raise ArgumentsDoNotMatchDeclarationException(
                f"{interaction.interaction_id.value} declares"
                f" {sorted(name.value for name in declared)} but got {sorted(name.value for name in self.values)}"
            )

    def items(self) -> tuple[ItemInstanceId, ...]:
        return tuple(value for value in self.values.values() if isinstance(value, ItemInstanceId))

    def value_of(self, name: ArgumentName, asked_by: Trigger) -> TextArgumentValue | ItemInstanceId:
        if name not in self.values:
            raise ArgumentNotInTriggerException(f"{asked_by!r} does not answer the argument {name.value!r}")
        return self.values[name]

    def unmet(
        self, precondition: Condition, facts: WorldFacts, trigger: Trigger
    ) -> FailureReason | HiddenFailure | None:
        return precondition.failure_reason(facts, trigger)

    def require_chosen(self, interaction: DeclaredInteraction) -> None:
        pass

    def chosen_as(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> ChosenArguments:
        return self


@final
@dataclass(frozen=True)
class ArgumentsNotChosen:
    def require_declared_by(self, interaction: DeclaredInteraction) -> None:
        pass

    def items(self) -> tuple[ItemInstanceId, ...]:
        return ()

    def value_of(self, name: ArgumentName, asked_by: Trigger) -> TextArgumentValue | ItemInstanceId:
        raise ArgumentNotInTriggerException(f"{asked_by!r} does not answer the argument {name.value!r}")

    def unmet(
        self, precondition: Condition, facts: WorldFacts, trigger: Trigger
    ) -> FailureReason | HiddenFailure | None:
        # 値しだいで決まる前提は、値を選べば満たせる見込みがあるので、できる側に倒す。
        verdict = precondition.failure_reason_before_arguments(facts, trigger)
        return None if isinstance(verdict, AwaitsArguments) else verdict

    def chosen_as(self, values: Mapping[str, TextArgumentValue | ItemInstanceId]) -> ChosenArguments:
        return ChosenArguments({ArgumentName(name): value for name, value in values.items()})

    def require_chosen(self, interaction: DeclaredInteraction) -> None:
        raise ArgumentsNotChosenException(f"the arguments of {interaction.interaction_id.value} have not been chosen")
