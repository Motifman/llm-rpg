from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.being.contract import (
    ActionChoice,
    ActionChoices,
    ArgumentOutline,
    Candidate,
    ChoiceValue,
    FreeText,
    PersonInText,
    PickOne,
    UnavailableAction,
)
from ai_rpg_world.game_world.domain.action.available_actions import AvailableActions, Doable, NotNow
from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
from ai_rpg_world.game_world.domain.action.offered_action import (
    ActionChoiceKind,
    OfferedAction,
    OfferedFreeText,
    OfferedInput,
    OfferedItemPick,
    OfferedStep,
    OfferedValue,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PeopleAsSeen, PersonRef
from ai_rpg_world.game_world.domain.value_object import DisplayName

_Label = DisplayName | PersonRef


@final
class OffersOfOneTurn:
    def __init__(
        self,
        offers: tuple[tuple[OfferedAction, Doable | NotNow], ...],
        people: PeopleAsSeen,
        descriptions: Mapping[ActionChoiceKind, str],
    ) -> None:
        self._offers = offers
        self._people = people
        self._descriptions = descriptions

    @classmethod
    def of(cls, available: AvailableActions, wording: ChoiceWording) -> OffersOfOneTurn:
        return cls(
            tuple((action.attempt.offered_as(wording), action.standing) for action in available.actions),
            wording.people,
            {
                kind: wording.design.choice_descriptions.description_of(
                    kind, wording.facts.rules(), wording.facts.day_night()
                )
                for kind in ActionChoiceKind
            },
        )

    def as_action_choices(self) -> ActionChoices:
        return ActionChoices(tuple(self._choice(kind) for kind in ActionChoiceKind))

    def _choice(self, kind: ActionChoiceKind) -> ActionChoice:
        root = _Node()
        not_now: list[tuple[OfferedAction, NotNow]] = []
        for offered, standing in self._offers:
            if offered.kind is not kind:
                continue
            if isinstance(standing, NotNow):
                not_now.append((offered, standing))
            else:
                root.add(offered.steps, offered.inputs)
        unavailable = dict.fromkeys(
            UnavailableAction(
                picked=tuple(_label(step.candidate) for step in offered.steps),
                reason=standing.reason.seen_by(self._people).for_being(),
                argument=offered.steps[-1].value.name if offered.steps else None,
            )
            for offered, standing in not_now
            if not root.reaches(tuple(_key(step.candidate) for step in offered.steps))
        )
        if kind.first_value is None and root.is_reached:
            unavailable = {}
        values: tuple[ChoiceValue, ...] = () if kind.first_value is None else (root.pick(kind.first_value),)
        return ActionChoice(
            name=kind.choice_name,
            label=kind.label,
            description=self._descriptions[kind],
            outline=tuple(
                ArgumentOutline(
                    name=value.name,
                    label=value.label,
                    required=value is kind.first_value,
                    hidden_as=value.hidden_as,
                    max_length=value.max_length,
                )
                for value in kind.outline
            ),
            takes_details=kind.takes_details,
            values=values,
            unavailable=tuple(unavailable),
        )


@dataclass
class _Child:
    label: _Label
    items: set[ItemInstanceId] = field(default_factory=set)
    node: _Node = field(default_factory=lambda: _Node())


@dataclass
class _Node:
    values: dict[str, OfferedValue] = field(default_factory=dict)
    children: dict[str, dict[object, _Child]] = field(default_factory=dict)
    inputs: dict[str, ChoiceValue] = field(default_factory=dict)
    is_reached: bool = False

    def add(self, steps: tuple[OfferedStep, ...], inputs: tuple[OfferedInput, ...]) -> None:
        leaf_values = tuple(_input(offered) for offered in inputs)
        # 暗がりの相手のように品物の候補が出せない道筋を残すと、契約が行き止まりとして拒む。
        if any(isinstance(value, PickOne) and not value.candidates for value in leaf_values):
            return
        node = self
        for step in steps:
            node.values[step.value.name] = step.value
            child = node.children.setdefault(step.value.name, {}).setdefault(
                _key(step.candidate), _Child(step.candidate)
            )
            child.items.update(() if not isinstance(step.item, ItemInstanceId) else (step.item,))
            node.is_reached = True
            node = child.node
        node.is_reached = True
        node.inputs.update((value.name, value) for value in leaf_values)

    def reaches(self, keys: tuple[object, ...]) -> bool:
        node = self
        for key in keys:
            found = [children[key] for children in node.children.values() if key in children]
            if not found:
                return False
            node = found[0].node
        return node.is_reached

    def pick(self, value: OfferedValue) -> PickOne:
        children = self.children.get(value.name, {})
        return PickOne(
            name=value.name,
            label=value.label,
            candidates=tuple(
                Candidate(label=_label(child.label), values=child.node.choice_values(), count=max(len(child.items), 1))
                for child in children.values()
            ),
        )

    def choice_values(self) -> tuple[ChoiceValue, ...]:
        return (*(self.pick(value) for value in self.values.values()), *self.inputs.values())


def _input(offered: OfferedInput) -> ChoiceValue:
    if isinstance(offered, OfferedFreeText):
        return FreeText(
            name=offered.value.name,
            label=offered.value.label,
            writes=None if offered.writes is None else offered.writes.text,
        )
    pick = _Node()
    for step in offered.items:
        pick.add((step,), ())
    return pick.pick(offered.value)


def _key(label: _Label) -> object:
    return label.handle if isinstance(label, PersonRef) else label.text


def _label(label: _Label) -> str | PersonInText:
    return label.for_being() if isinstance(label, PersonRef) else label.text
