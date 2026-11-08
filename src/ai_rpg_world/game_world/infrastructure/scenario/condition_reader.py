from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.condition.argument_condition import ArgumentEqualsCondition
from ai_rpg_world.game_world.domain.condition.chance_condition import ChanceCondition
from ai_rpg_world.game_world.domain.condition.condition import Condition, NoText
from ai_rpg_world.game_world.domain.condition.connectives import (
    AllOfCondition,
    AnyOfCondition,
    ForEveryoneCondition,
    ForSomeoneCondition,
    NotCondition,
)
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition, FlagsRaisedAtLeastCondition
from ai_rpg_world.game_world.domain.condition.happening_conditions import (
    HappeningHasFiredCondition,
    TicksSinceHappeningAtLeastCondition,
)
from ai_rpg_world.game_world.domain.condition.item_conditions import ItemAgeAtLeastCondition, ItemValueIsCondition
from ai_rpg_world.game_world.domain.condition.latest_action_conditions import (
    SinceStart,
    SinceWorldStageEntered,
    TicksSinceLastActionAtLeastCondition,
)
from ai_rpg_world.game_world.domain.condition.membership_condition import IsMemberCondition
from ai_rpg_world.game_world.domain.condition.object_state_conditions import (
    ObjectCountAtLeastCondition,
    ObjectCountGreaterThanCondition,
    ObjectStockAtLeastCondition,
    ObjectValueIsCondition,
)
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.person_conditions import (
    AllOutcomesDecidedCondition,
    FatigueAtLeastCondition,
    GoldAtLeastCondition,
    HasItemCondition,
    HungerAtLeastCondition,
    IsAliveCondition,
    IsAtSpotCondition,
    IsDownCondition,
    IsHoldingCondition,
    IsInSectionCondition,
    OutcomeIsCondition,
    PeopleCountAtLeastCondition,
    SearchCountAtLeastCondition,
)
from ai_rpg_world.game_world.domain.condition.subject import Anyone, Subject
from ai_rpg_world.game_world.domain.condition.world_time_conditions import (
    TickAtLeastCondition,
    TickModuloCondition,
    TicksInWorldStageAtLeastCondition,
    TimeOfDayIsCondition,
    WeatherIsCondition,
    WorldStageIsCondition,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayPhaseName, WeatherType
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import Died, Outcome
from ai_rpg_world.game_world.domain.person.person_outcomes import DeclaredOutcome
from ai_rpg_world.game_world.domain.value_object import (
    FatigueAmount,
    Gold,
    HungerAmount,
    Probability,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.kinded_node import KindedNode, split_kind
from ai_rpg_world.game_world.infrastructure.scenario.value_readers import (
    action,
    count,
    people_text,
    state_value,
    subject,
    this_item,
    ticks,
    words,
)
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import YamlNode

_Text = TextWithUnassignedPeople | NoText
_DIED = "died"
_SINCE: dict[str, SinceStart | SinceWorldStageEntered] = {
    "start": SinceStart(),
    "world_stage_entered": SinceWorldStageEntered(),
}


class ConditionReader:
    def __init__(self, names: DeclaredNames) -> None:
        self._names = names
        self._kinds: dict[str, Callable[[KindedNode, _Text], Condition]] = {
            "all_of": self._all_of,
            "any_of": self._any_of,
            "not": self._not,
            "for_someone": self._for_someone,
            "for_everyone": self._for_everyone,
            "argument_equals": self._argument_equals,
            "chance": self._chance,
            "item_age_at_least": self._item_age_at_least,
            "item_value_is": self._item_value_is,
            "flag_is_raised": self._flag_is_raised,
            "flags_raised_at_least": self._flags_raised_at_least,
            "ticks_since_last_action_at_least": self._ticks_since_last_action_at_least,
            "happening_has_fired": self._happening_has_fired,
            "ticks_since_happening_at_least": self._ticks_since_happening_at_least,
            "object_value_is": self._object_value_is,
            "object_count_at_least": self._object_count_at_least,
            "object_count_greater_than": self._object_count_greater_than,
            "object_stock_at_least": self._object_stock_at_least,
            "is_member": self._is_member,
            "has_item": self._has_item,
            "is_holding": self._is_holding,
            "gold_at_least": self._gold_at_least,
            "is_at_spot": self._is_at_spot,
            "is_in_section": self._is_in_section,
            "search_count_at_least": self._search_count_at_least,
            "is_down": self._is_down,
            "is_alive": self._is_alive,
            "hunger_at_least": self._hunger_at_least,
            "fatigue_at_least": self._fatigue_at_least,
            "outcome_is": self._outcome_is,
            "all_outcomes_decided": self._all_outcomes_decided,
            "people_count_at_least": self._people_count_at_least,
            "tick_at_least": self._tick_at_least,
            "tick_modulo": self._tick_modulo,
            "world_stage_is": self._world_stage_is,
            "ticks_in_world_stage_at_least": self._ticks_in_world_stage_at_least,
            "time_of_day_is": self._time_of_day_is,
            "weather_is": self._weather_is,
        }

    def read(self, node: YamlNode) -> Condition:
        kinded = split_kind(node, self._kinds, explains_failure=True)
        failure_text: _Text = NoText() if kinded.failure_text is None else people_text(kinded.failure_text)
        return kinded.body.build(lambda: self._kinds[kinded.kind](kinded, failure_text))

    def people(self, node: YamlNode) -> PeopleSelection:
        where = node.fields("where").required("where")
        return PeopleSelection(where=self.read(where))

    def _all_of(self, node: KindedNode, text: _Text) -> Condition:
        return AllOfCondition(children=self._children(node.single("children")), failure_text=text)

    def _any_of(self, node: KindedNode, text: _Text) -> Condition:
        return AnyOfCondition(children=self._children(node.single("children")), failure_text=text)

    def _children(self, node: YamlNode) -> tuple[Condition, ...]:
        return tuple(self.read(child) for child in node.items())

    def _not(self, node: KindedNode, text: _Text) -> Condition:
        return NotCondition(child=self.read(node.single("child")), failure_text=text)

    def _for_someone(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("people", "condition")
        return ForSomeoneCondition(
            people=self.people(fields.required("people")),
            condition=self.read(fields.required("condition")),
            failure_text=text,
        )

    def _for_everyone(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("people", "condition")
        return ForEveryoneCondition(
            people=self.people(fields.required("people")),
            condition=self.read(fields.required("condition")),
            failure_text=text,
        )

    def _argument_equals(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("argument", "expected")
        return ArgumentEqualsCondition(
            argument=ArgumentName(fields.required("argument").text()),
            expected=TextArgumentValue(fields.required("expected").text()),
            failure_text=text,
        )

    def _chance(self, node: KindedNode, text: _Text) -> Condition:
        return ChanceCondition(probability=Probability(node.single("probability").number()), failure_text=text)

    def _item_age_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("item", "ticks")
        return ItemAgeAtLeastCondition(
            item=this_item(fields.required("item")), ticks=ticks(fields.required("ticks")), failure_text=text
        )

    def _item_value_is(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("item", "key", "value")
        key = self._names.item_state_key(fields.required("key"))
        return ItemValueIsCondition(
            item=this_item(fields.required("item")),
            key=key,
            value=state_value(key.kind, fields.required("value")),
            failure_text=text,
        )

    def _flag_is_raised(self, node: KindedNode, text: _Text) -> Condition:
        return FlagIsRaisedCondition(flag=self._names.flag(node.single("flag")), failure_text=text)

    def _flags_raised_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("flags", "count")
        return FlagsRaisedAtLeastCondition(
            flags=tuple(self._names.flag(flag) for flag in fields.required("flags").items()),
            count=count(fields.required("count")),
            failure_text=text,
        )

    def _ticks_since_last_action_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "action", "ticks", "since")
        who = fields.required("who")
        return TicksSinceLastActionAtLeastCondition(
            who=Anyone() if who.value == "anyone" else self._subject(who),
            action=action(fields.required("action")),
            ticks=ticks(fields.required("ticks")),
            since=words(fields.required("since"), _SINCE),
            failure_text=text,
        )

    def _happening_has_fired(self, node: KindedNode, text: _Text) -> Condition:
        return HappeningHasFiredCondition(happening=self._happening(node.single("happening")), failure_text=text)

    def _ticks_since_happening_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("happening", "ticks")
        return TicksSinceHappeningAtLeastCondition(
            happening=self._happening(fields.required("happening")),
            ticks=ticks(fields.required("ticks")),
            failure_text=text,
        )

    def _object_value_is(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("key", "value")
        key = self._names.object_state_key(fields.required("key"))
        return ObjectValueIsCondition(key=key, value=state_value(key.kind, fields.required("value")), failure_text=text)

    def _object_count_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("key", "count")
        return ObjectCountAtLeastCondition(
            key=self._names.object_state_key(fields.required("key")),
            count=count(fields.required("count")),
            failure_text=text,
        )

    def _object_count_greater_than(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("key", "other")
        return ObjectCountGreaterThanCondition(
            key=self._names.object_state_key(fields.required("key")),
            other=self._names.object_state_key(fields.required("other")),
            failure_text=text,
        )

    def _object_stock_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("key", "amount")
        return ObjectStockAtLeastCondition(
            key=self._names.object_state_key(fields.required("key")),
            amount=count(fields.required("amount")),
            failure_text=text,
        )

    def _is_member(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "group")
        return IsMemberCondition(
            who=self._subject(fields.required("who")),
            group=self._names.group(fields.required("group")),
            failure_text=text,
        )

    def _has_item(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "item_spec", "count")
        return HasItemCondition(
            who=self._subject(fields.required("who")),
            item_spec=self._names.item_spec(fields.required("item_spec")),
            count=count(fields.required("count")),
            failure_text=text,
        )

    def _is_holding(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "item_spec")
        return IsHoldingCondition(
            who=self._subject(fields.required("who")),
            item_spec=self._names.item_spec(fields.required("item_spec")),
            failure_text=text,
        )

    def _gold_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "amount")
        amount = fields.required("amount")
        return GoldAtLeastCondition(
            who=self._subject(fields.required("who")), amount=Gold(amount.integer()), failure_text=text
        )

    def _is_at_spot(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "spot")
        return IsAtSpotCondition(
            who=self._subject(fields.required("who")),
            spot=self._names.spot(fields.required("spot")),
            failure_text=text,
        )

    def _is_in_section(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "section")
        return IsInSectionCondition(
            who=self._subject(fields.required("who")),
            section=self._names.section(fields.required("section")),
            failure_text=text,
        )

    def _search_count_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "count")
        return SearchCountAtLeastCondition(
            who=self._subject(fields.required("who")), count=count(fields.required("count")), failure_text=text
        )

    def _is_down(self, node: KindedNode, text: _Text) -> Condition:
        return IsDownCondition(who=self._subject(node.single("who")), failure_text=text)

    def _is_alive(self, node: KindedNode, text: _Text) -> Condition:
        return IsAliveCondition(who=self._subject(node.single("who")), failure_text=text)

    def _hunger_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "value")
        return HungerAtLeastCondition(
            who=self._subject(fields.required("who")),
            value=HungerAmount(fields.required("value").integer()),
            failure_text=text,
        )

    def _fatigue_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "value")
        return FatigueAtLeastCondition(
            who=self._subject(fields.required("who")),
            value=FatigueAmount(fields.required("value").integer()),
            failure_text=text,
        )

    def _outcome_is(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("who", "outcome")
        return OutcomeIsCondition(
            who=self._subject(fields.required("who")),
            outcome=self._outcome(fields.required("outcome")),
            failure_text=text,
        )

    def _outcome(self, node: YamlNode) -> Outcome:
        if node.value == _DIED:
            return Died()
        return DeclaredOutcome(self._names.outcome(node))

    def _all_outcomes_decided(self, node: KindedNode, text: _Text) -> Condition:
        node.nothing()
        return AllOutcomesDecidedCondition(failure_text=text)

    def _people_count_at_least(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("people", "count")
        return PeopleCountAtLeastCondition(
            people=self.people(fields.required("people")), count=count(fields.required("count")), failure_text=text
        )

    def _tick_at_least(self, node: KindedNode, text: _Text) -> Condition:
        return TickAtLeastCondition(tick=WorldTick(node.single("tick").integer()), failure_text=text)

    def _tick_modulo(self, node: KindedNode, text: _Text) -> Condition:
        fields = node.fields("divisor", "remainder")
        return TickModuloCondition(
            divisor=ticks(fields.required("divisor")), remainder=ticks(fields.required("remainder")), failure_text=text
        )

    def _world_stage_is(self, node: KindedNode, text: _Text) -> Condition:
        return WorldStageIsCondition(stage=self._names.world_stage(node.single("stage")), failure_text=text)

    def _ticks_in_world_stage_at_least(self, node: KindedNode, text: _Text) -> Condition:
        return TicksInWorldStageAtLeastCondition(ticks=ticks(node.single("ticks")), failure_text=text)

    def _time_of_day_is(self, node: KindedNode, text: _Text) -> Condition:
        return TimeOfDayIsCondition(phase=DayPhaseName(node.single("phase").text()), failure_text=text)

    def _weather_is(self, node: KindedNode, text: _Text) -> Condition:
        return WeatherIsCondition(weather=node.single("weather").enum(WeatherType), failure_text=text)

    def _happening(self, node: YamlNode) -> HappeningId:
        return node.build(lambda: HappeningId(node.text()))

    def _subject(self, node: YamlNode) -> Subject:
        return subject(node, self._names)
