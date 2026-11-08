from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActorRequirement,
    DoesNotUseBody,
    Exertion,
    LivingOnly,
    LivingOrDeparted,
    UsesBody,
)
from ai_rpg_world.game_world.domain.condition.subject import (
    Actor,
    ChosenByGroup,
    EachPerson,
    NamedPerson,
    Subject,
    Target,
    ThisItem,
)
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    CountStateKind,
    CountValue,
    FlagStateKind,
    FlagValue,
    NothingWritten,
    StateKind,
    StateValue,
    StockStateKind,
    StockValue,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.declaration.verb import DefaultDuration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception.salience import Background, Notable, Salience
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import Count, DescriptionText, DisplayName, InteractionId, Ticks
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import YamlNode

_Value = TypeVar("_Value")

_SUBJECTS: dict[str, Subject] = {
    "actor": Actor(),
    "target": Target(),
    "chosen_by_group": ChosenByGroup(),
    "each_person": EachPerson(),
}
_EXERTIONS: dict[str, Exertion] = {"uses_body": UsesBody(), "does_not_use_body": DoesNotUseBody()}
_ACTOR_REQUIREMENTS: dict[str, ActorRequirement] = {
    "living_only": LivingOnly(),
    "living_or_departed": LivingOrDeparted(),
}
_SALIENCES: dict[str, Salience] = {"notable": Notable(), "background": Background()}
_NAMED = "named"
_INTERACTION = "interaction"


def words(node: YamlNode, choices: dict[str, _Value]) -> _Value:
    if not isinstance(node.value, str) or node.value not in choices:
        raise node.unreadable(f"expected one of {sorted(choices)}, got {node.value!r}")
    return choices[node.value]


def nullable(node: YamlNode, absent: _Value, read: Callable[[YamlNode], object]) -> object:
    if node.is_null():
        return absent
    return read(node)


def subject(node: YamlNode, names: DeclaredNames) -> Subject:
    if node.is_mapping():
        return NamedPerson(names.character(node.fields(_NAMED).required(_NAMED)))
    return words(node, _SUBJECTS)


def this_item(node: YamlNode) -> ThisItem:
    return words(node, {"this_item": ThisItem()})


def people_text(node: YamlNode) -> TextWithUnassignedPeople:
    return node.build(lambda: TextWithUnassignedPeople(node.text()))


def display_name(node: YamlNode) -> DisplayName:
    return node.build(lambda: DisplayName(node.text()))


def description(node: YamlNode) -> DescriptionText:
    return node.build(lambda: DescriptionText(node.text()))


def ticks(node: YamlNode) -> Ticks:
    return node.build(lambda: Ticks(node.integer()))


def count(node: YamlNode) -> Count:
    return node.build(lambda: Count(node.integer()))


def duration(node: YamlNode) -> Ticks | DefaultDuration:
    if node.value == "default":
        return DefaultDuration()
    return ticks(node)


def exertion(node: YamlNode) -> Exertion:
    return words(node, _EXERTIONS)


def actor_requirement(node: YamlNode) -> ActorRequirement:
    return words(node, _ACTOR_REQUIREMENTS)


def salience(node: YamlNode) -> Salience:
    return words(node, _SALIENCES)


def action(node: YamlNode) -> ActionKind | InteractionId:
    if node.is_mapping():
        interaction = node.fields(_INTERACTION).required(_INTERACTION)
        return interaction.build(lambda: InteractionId(interaction.text()))
    return node.enum(ActionKind)


def state_value(kind: StateKind, node: YamlNode) -> StateValue:
    value: StateValue
    if isinstance(kind, FlagStateKind):
        value = FlagValue(node.boolean())
    elif isinstance(kind, CountStateKind):
        value = node.build(lambda: CountValue(Count(node.integer())))
    elif isinstance(kind, ChoiceStateKind):
        value = node.build(lambda: ChoiceValue(ChoiceName(node.text())))
    elif isinstance(kind, StockStateKind):
        value = node.build(lambda: StockValue(Count(node.integer())))
    elif isinstance(kind, WrittenTextStateKind):
        if not node.is_null():
            raise node.unreadable("a written text key starts with nothing written; write null")
        value = NothingWritten()
    if not kind.accepts(value):
        raise node.unreadable(f"{node.value!r} does not fit the state key")
    return value
