from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.subject import Subject
from ai_rpg_world.game_world.domain.declaration.spot import NoAmbientSound, NoSmell, Temperature, Unchanged
from ai_rpg_world.game_world.domain.effect.body_effects import (
    DamageEffect,
    HealEffect,
    RestEffect,
    ReviveEffect,
    SatisfyHungerEffect,
)
from ai_rpg_world.game_world.domain.effect.combined_effects import (
    ConditionalEffect,
    ForEveryoneEffect,
    ForSomeoneEffect,
    NoEffect,
    RandomBranchEffect,
    SequenceEffect,
)
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.flag_effects import LowerFlagEffect, RaiseFlagEffect
from ai_rpg_world.game_world.domain.effect.item_effects import (
    Anywhere,
    GiveItemEffect,
    InHands,
    InPack,
    ItemByArgument,
    ItemPlace,
    MoveItemEffect,
    RandomItemOf,
    SetItemValueEffect,
    TakeItemEffect,
)
from ai_rpg_world.game_world.domain.effect.membership_and_outcome_effects import (
    JoinGroupEffect,
    LeaveGroupEffect,
    SetOutcomeEffect,
)
from ai_rpg_world.game_world.domain.effect.object_effects import (
    AddToObjectCountEffect,
    DepositGoldToObjectEffect,
    DepositItemToObjectEffect,
    RevealObjectEffect,
    SetObjectValueEffect,
    SubtractFromObjectCountEffect,
    TakeFromObjectStockEffect,
    WriteTextEffect,
)
from ai_rpg_world.game_world.domain.effect.spot_and_passage_effects import (
    ChangeAtmosphereEffect,
    ChangePassageStateEffect,
    RemovePassageEffect,
    RevealPassageEffect,
)
from ai_rpg_world.game_world.domain.effect.weight import Weight
from ai_rpg_world.game_world.domain.effect.whereabouts_effects import (
    PutIntoSectionEffect,
    RemoveBodyEffect,
    TakeOutOfSectionEffect,
    TeleportEffect,
)
from ai_rpg_world.game_world.domain.effect.world_progress_effects import (
    CloseGroupDecisionEffect,
    EnterWorldStageEffect,
    StartGroupDecisionEffect,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DescriptionText,
    FatigueAmount,
    Gold,
    HealAmount,
    HungerAmount,
    PassageStateName,
    Rate,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.infrastructure.scenario.condition_reader import ConditionReader
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.kinded_node import KindedNode, split_kind
from ai_rpg_world.game_world.infrastructure.scenario.value_readers import (
    count,
    description,
    state_value,
    subject,
    this_item,
    words,
)
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import YamlNode

_PLACES: dict[str, ItemPlace] = {"in_hands": InHands(), "in_pack": InPack(), "anywhere": Anywhere()}
_RANDOM_ITEM_OF = "random_item_of"


class EffectReader:
    def __init__(
        self,
        names: DeclaredNames,
        conditions: ConditionReader,
        voters_and_choices: Callable[[YamlNode], tuple[PeopleSelection, PeopleSelection]],
    ) -> None:
        self._names = names
        self._conditions = conditions
        self._voters_and_choices = voters_and_choices
        self._kinds: dict[str, Callable[[KindedNode], Effect]] = {
            "no_effect": self._no_effect,
            "sequence": self._sequence,
            "conditional": self._conditional,
            "random_branch": self._random_branch,
            "for_everyone": self._for_everyone,
            "for_someone": self._for_someone,
            "damage": self._damage,
            "heal": self._heal,
            "revive": self._revive,
            "satisfy_hunger": self._satisfy_hunger,
            "rest": self._rest,
            "give_item": self._give_item,
            "take_item": self._take_item,
            "move_item": self._move_item,
            "set_item_value": self._set_item_value,
            "raise_flag": self._raise_flag,
            "lower_flag": self._lower_flag,
            "join_group": self._join_group,
            "leave_group": self._leave_group,
            "set_outcome": self._set_outcome,
            "set_object_value": self._set_object_value,
            "add_to_object_count": self._add_to_object_count,
            "subtract_from_object_count": self._subtract_from_object_count,
            "take_from_object_stock": self._take_from_object_stock,
            "write_text": self._write_text,
            "reveal_object": self._reveal_object,
            "deposit_item_to_object": self._deposit_item_to_object,
            "deposit_gold_to_object": self._deposit_gold_to_object,
            "change_passage_state": self._change_passage_state,
            "reveal_passage": self._reveal_passage,
            "remove_passage": self._remove_passage,
            "change_atmosphere": self._change_atmosphere,
            "teleport": self._teleport,
            "put_into_section": self._put_into_section,
            "take_out_of_section": self._take_out_of_section,
            "remove_body": self._remove_body,
            "enter_world_stage": self._enter_world_stage,
            "start_group_decision": self._start_group_decision,
            "close_group_decision": self._close_group_decision,
        }

    def read(self, node: YamlNode) -> Effect:
        kinded = split_kind(node, self._kinds, explains_failure=False)
        return kinded.body.build(lambda: self._kinds[kinded.kind](kinded))

    def _no_effect(self, node: KindedNode) -> Effect:
        node.nothing()
        return NoEffect()

    def _sequence(self, node: KindedNode) -> Effect:
        return SequenceEffect(steps=tuple(self.read(step) for step in node.single("steps").items()))

    def _conditional(self, node: KindedNode) -> Effect:
        fields = node.fields("condition", "then", "otherwise")
        otherwise = fields.required("otherwise")
        return ConditionalEffect(
            condition=self._conditions.read(fields.required("condition")),
            then=self.read(fields.required("then")),
            otherwise=self.read(otherwise),
        )

    def _random_branch(self, node: KindedNode) -> Effect:
        branches = []
        for branch in node.single("branches").items():
            fields = branch.fields("weight", "effect")
            weight = fields.required("weight")
            branches.append((weight.build(lambda: Weight(weight.integer())), self.read(fields.required("effect"))))
        return RandomBranchEffect(branches=tuple(branches))

    def _for_everyone(self, node: KindedNode) -> Effect:
        fields = node.fields("people", "effect")
        return ForEveryoneEffect(
            people=self._conditions.people(fields.required("people")), effect=self.read(fields.required("effect"))
        )

    def _for_someone(self, node: KindedNode) -> Effect:
        fields = node.fields("people", "effect")
        return ForSomeoneEffect(
            people=self._conditions.people(fields.required("people")), effect=self.read(fields.required("effect"))
        )

    def _damage(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "amount")
        return DamageEffect(
            who=self._subject(fields.required("who")), amount=Damage(fields.required("amount").integer())
        )

    def _heal(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "amount")
        return HealEffect(
            who=self._subject(fields.required("who")), amount=HealAmount(fields.required("amount").integer())
        )

    def _revive(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "hp_rate")
        return ReviveEffect(
            who=self._subject(fields.required("who")), hp_rate=Rate(fields.required("hp_rate").number())
        )

    def _satisfy_hunger(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "amount")
        return SatisfyHungerEffect(
            who=self._subject(fields.required("who")), amount=HungerAmount(fields.required("amount").integer())
        )

    def _rest(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "amount")
        return RestEffect(
            who=self._subject(fields.required("who")), amount=FatigueAmount(fields.required("amount").integer())
        )

    def _give_item(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "item_spec", "count")
        return GiveItemEffect(
            who=self._subject(fields.required("who")),
            item_spec=self._names.item_spec(fields.required("item_spec")),
            count=count(fields.required("count")),
        )

    def _take_item(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "item_spec", "count")
        return TakeItemEffect(
            who=self._subject(fields.required("who")),
            item_spec=self._names.item_spec(fields.required("item_spec")),
            count=count(fields.required("count")),
        )

    def _move_item(self, node: KindedNode) -> Effect:
        fields = node.fields("from_who", "to_who", "item")
        return MoveItemEffect(
            from_who=self._subject(fields.required("from_who")),
            to_who=self._subject(fields.required("to_who")),
            item=self._moved_item(fields.required("item")),
        )

    def _moved_item(self, node: YamlNode) -> ItemByArgument | RandomItemOf:
        if node.value == _RANDOM_ITEM_OF:
            return RandomItemOf()
        fields = node.fields("argument", "place")
        return ItemByArgument(
            argument=ArgumentName(fields.required("argument").text()), place=words(fields.required("place"), _PLACES)
        )

    def _set_item_value(self, node: KindedNode) -> Effect:
        fields = node.fields("item", "key", "value")
        key = self._names.item_state_key(fields.required("key"))
        return SetItemValueEffect(
            item=this_item(fields.required("item")), key=key, value=state_value(key.kind, fields.required("value"))
        )

    def _raise_flag(self, node: KindedNode) -> Effect:
        return RaiseFlagEffect(flag=self._names.flag(node.single("flag")))

    def _lower_flag(self, node: KindedNode) -> Effect:
        return LowerFlagEffect(flag=self._names.flag(node.single("flag")))

    def _join_group(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "group")
        return JoinGroupEffect(
            who=self._subject(fields.required("who")), group=self._names.group(fields.required("group"))
        )

    def _leave_group(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "group")
        return LeaveGroupEffect(
            who=self._subject(fields.required("who")), group=self._names.group(fields.required("group"))
        )

    def _set_outcome(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "outcome")
        return SetOutcomeEffect(
            who=self._subject(fields.required("who")), outcome=self._names.outcome(fields.required("outcome"))
        )

    def _set_object_value(self, node: KindedNode) -> Effect:
        fields = node.fields("key", "value")
        key = self._names.object_state_key(fields.required("key"))
        return SetObjectValueEffect(key=key, value=state_value(key.kind, fields.required("value")))

    def _add_to_object_count(self, node: KindedNode) -> Effect:
        fields = node.fields("key", "amount")
        return AddToObjectCountEffect(
            key=self._names.object_state_key(fields.required("key")), amount=count(fields.required("amount"))
        )

    def _subtract_from_object_count(self, node: KindedNode) -> Effect:
        fields = node.fields("key", "amount")
        return SubtractFromObjectCountEffect(
            key=self._names.object_state_key(fields.required("key")), amount=count(fields.required("amount"))
        )

    def _take_from_object_stock(self, node: KindedNode) -> Effect:
        fields = node.fields("key", "amount")
        return TakeFromObjectStockEffect(
            key=self._names.object_state_key(fields.required("key")), amount=count(fields.required("amount"))
        )

    def _write_text(self, node: KindedNode) -> Effect:
        fields = node.fields("key", "body_argument")
        return WriteTextEffect(
            key=self._names.object_state_key(fields.required("key")),
            body_argument=ArgumentName(fields.required("body_argument").text()),
        )

    def _reveal_object(self, node: KindedNode) -> Effect:
        return RevealObjectEffect(obj=self._names.object(node.single("obj")))

    def _deposit_item_to_object(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "item_spec", "key")
        return DepositItemToObjectEffect(
            who=self._subject(fields.required("who")),
            item_spec=self._names.item_spec(fields.required("item_spec")),
            key=self._names.object_state_key(fields.required("key")),
        )

    def _deposit_gold_to_object(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "amount", "key")
        return DepositGoldToObjectEffect(
            who=self._subject(fields.required("who")),
            amount=Gold(fields.required("amount").integer()),
            key=self._names.object_state_key(fields.required("key")),
        )

    def _change_passage_state(self, node: KindedNode) -> Effect:
        fields = node.fields("passage", "state")
        return ChangePassageStateEffect(
            passage=self._names.passage(fields.required("passage")),
            state=PassageStateName(fields.required("state").text()),
        )

    def _reveal_passage(self, node: KindedNode) -> Effect:
        return RevealPassageEffect(passage=self._names.passage(node.single("passage")))

    def _remove_passage(self, node: KindedNode) -> Effect:
        return RemovePassageEffect(passage=self._names.passage(node.single("passage")))

    def _change_atmosphere(self, node: KindedNode) -> Effect:
        fields = node.fields("spot", "lighting", "temperature", "ambient_sound", "smell")
        lighting = fields.optional("lighting")
        temperature = fields.optional("temperature")
        return ChangeAtmosphereEffect(
            spot=self._names.spot(fields.required("spot")),
            lighting=Unchanged() if lighting is None else lighting.enum(Lighting),
            temperature=Unchanged() if temperature is None else temperature.enum(Temperature),
            ambient_sound=_changed_text(fields.optional("ambient_sound"), NoAmbientSound()),
            smell=_changed_text(fields.optional("smell"), NoSmell()),
        )

    def _teleport(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "to")
        return TeleportEffect(who=self._subject(fields.required("who")), to=self._names.spot(fields.required("to")))

    def _put_into_section(self, node: KindedNode) -> Effect:
        fields = node.fields("who", "section")
        return PutIntoSectionEffect(
            who=self._subject(fields.required("who")), section=self._names.section(fields.required("section"))
        )

    def _take_out_of_section(self, node: KindedNode) -> Effect:
        return TakeOutOfSectionEffect(who=self._subject(node.single("who")))

    def _remove_body(self, node: KindedNode) -> Effect:
        return RemoveBodyEffect(who=self._subject(node.single("who")))

    def _enter_world_stage(self, node: KindedNode) -> Effect:
        return EnterWorldStageEffect(stage=self._names.world_stage(node.single("stage")))

    def _start_group_decision(self, node: KindedNode) -> Effect:
        decision = node.single("decision")
        voters, choices = self._voters_and_choices(decision)
        return StartGroupDecisionEffect(decision=self._names.group_decision(decision), voters=voters, choices=choices)

    def _close_group_decision(self, node: KindedNode) -> Effect:
        return CloseGroupDecisionEffect(decision=self._names.group_decision(node.single("decision")))

    def _subject(self, node: YamlNode) -> Subject:
        return subject(node, self._names)


_Absent = TypeVar("_Absent", NoAmbientSound, NoSmell)


def _changed_text(node: YamlNode | None, absent: _Absent) -> DescriptionText | _Absent | Unchanged:
    if node is None:
        return Unchanged()
    if node.is_null():
        return absent
    return description(node)
