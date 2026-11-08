from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar, final

from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration, ItemArgument, TextArgument
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.verb import (
    DiscoverableDeclaration,
    Finding,
    GroupDecisionRulesDeclaration,
    HappeningDeclaration,
    InteractionDeclaration,
    ItemInteractionDeclaration,
    ItemUseDeclaration,
    JointActionDeclaration,
    ObjectInteractionDeclaration,
    PassageTraversalDeclaration,
    PeopleCountAt,
    ReactionDeclaration,
    SectionAccessDeclaration,
    ShownToActor,
    WorldStageEffectsDeclaration,
    WrittenTextOf,
)
from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId, SpotId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.infrastructure.scenario.condition_reader import ConditionReader
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.effect_reader import EffectReader
from ai_rpg_world.game_world.infrastructure.scenario.kinded_node import split_kind
from ai_rpg_world.game_world.infrastructure.scenario.noun_reader import (
    GROUP_DECISION_FIELDS,
    ITEM_SPEC_FIELDS,
    OBJECT_FIELDS,
    PASSAGE_FIELDS,
    SECTION_FIELDS,
    SPOT_FIELDS,
    WORLD_STAGE_FIELDS,
)
from ai_rpg_world.game_world.infrastructure.scenario.perception_reader import PerceptionReader
from ai_rpg_world.game_world.infrastructure.scenario.scenario_defaults import ScenarioDefaults
from ai_rpg_world.game_world.infrastructure.scenario.value_readers import (
    actor_requirement,
    display_name,
    duration,
    exertion,
    people_text,
    ticks,
    words,
)
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import FlawCollector, YamlFields, YamlNode

_INTERACTION_FIELDS = (
    "display_label",
    "precondition",
    "effect",
    "success_text",
    "shows_on_success",
    "exertion",
    "actor_requirement",
    "perceived_as",
    "reaches_unseen",
    "duration",
    "allows_stealth",
    "arguments",
)
_ACCESS_FIELDS = (
    "enter_label",
    "leave_label",
    "enter_text",
    "leave_text",
    "exertion",
    "duration",
    "entry_condition",
    "perceived_as",
)
_ARGUMENT_KINDS: dict[str, TextArgument | ItemArgument] = {"text": TextArgument(), "item": ItemArgument()}
_FINDINGS: dict[str, Finding] = {"once_in_world": Finding.ONCE_IN_WORLD, "once_per_person": Finding.ONCE_PER_PERSON}
_SHOWN_KINDS = ("people_count_at", "written_text_of")

_Declaration = TypeVar("_Declaration")


@final
@dataclass
class ReadVerbs:
    object_interactions: list[ObjectInteractionDeclaration] = field(default_factory=list)
    item_interactions: list[ItemInteractionDeclaration] = field(default_factory=list)
    item_uses: list[ItemUseDeclaration] = field(default_factory=list)
    section_accesses: list[SectionAccessDeclaration] = field(default_factory=list)
    passage_traversals: list[PassageTraversalDeclaration] = field(default_factory=list)
    world_stage_effects: list[WorldStageEffectsDeclaration] = field(default_factory=list)
    group_decision_rules: list[GroupDecisionRulesDeclaration] = field(default_factory=list)
    happenings: list[HappeningDeclaration] = field(default_factory=list)
    reactions: list[ReactionDeclaration] = field(default_factory=list)
    discoverables: list[DiscoverableDeclaration] = field(default_factory=list)
    joint_actions: list[JointActionDeclaration] = field(default_factory=list)
    person_interactions: list[InteractionDeclaration] = field(default_factory=list)


class VerbReader:
    def __init__(
        self,
        defaults: ScenarioDefaults,
        names: DeclaredNames,
        conditions: ConditionReader,
        effects: EffectReader,
        perceptions: PerceptionReader,
        collector: FlawCollector,
    ) -> None:
        self._defaults = defaults
        self._names = names
        self._conditions = conditions
        self._effects = effects
        self._perceptions = perceptions
        self._collector = collector
        self._read = ReadVerbs()

    def read(self, scenario: YamlFields) -> ReadVerbs:
        for spot_name, spot in self._entries(scenario.nested("spots")):
            spot_fields = self._collector.attempt(lambda: self._defaults.fill("spot", spot).fields(*SPOT_FIELDS))
            if spot_fields is None:
                continue
            for name, obj in self._entries(spot_fields.nested("objects")):
                self._object_interactions(name, obj)
            for name, section in self._entries(spot_fields.nested("sections")):
                self._add(self._read.section_accesses, lambda: self._section_access(name, section))
            for name, discoverable in self._entries(spot_fields.nested("discoverables")):
                self._add(self._read.discoverables, lambda: self._discoverable(name, spot_name, discoverable))
        for name, passage in self._entries(scenario.nested("passages")):
            self._add_traversal(name, passage)
        for name, item_spec in self._entries(scenario.nested("item_specs")):
            self._item_verbs(name, item_spec)
        for name, stage in self._entries(scenario.nested("world_stages")):
            self._add(self._read.world_stage_effects, lambda: self._world_stage_effects(name, stage))
        for name, decision in self._entries(scenario.nested("group_decisions")):
            self._add(self._read.group_decision_rules, lambda: self._group_decision_rules(name, decision))
        for name, happening in self._entries(scenario.nested("happenings")):
            self._add(self._read.happenings, lambda: self._happening(name, happening))
        for name, reaction in self._entries(scenario.nested("reactions")):
            self._add(self._read.reactions, lambda: self._reaction(name, reaction))
        for name, joint in self._entries(scenario.nested("joint_actions")):
            self._add(self._read.joint_actions, lambda: self._joint_action(name, joint))
        for name, interaction in self._entries(scenario.nested("person_interactions")):
            self._add(self._read.person_interactions, lambda: self.interaction(name, interaction, has_target=True))
        return self._read

    def voters_and_choices(
        self, decision: YamlNode, group_decisions: YamlNode
    ) -> tuple[PeopleSelection, PeopleSelection]:
        name = decision.text()
        declared = dict(group_decisions.entries()).get(name)
        if declared is None:
            raise decision.unreadable(f"group_decision {name!r} is not declared")
        fields = self._defaults.fill("group_decision", declared).fields(*GROUP_DECISION_FIELDS)
        return self._conditions.people(fields.required("voters")), self._conditions.people(fields.required("choices"))

    def interaction(self, name: str, node: YamlNode, has_target: bool) -> InteractionDeclaration:
        fields = self._defaults.fill("interaction", node).fields(*_INTERACTION_FIELDS)
        return node.build(
            lambda: InteractionDeclaration(
                interaction_id=InteractionId(name),
                display_label=display_name(fields.required("display_label")),
                precondition=self._conditions.read(fields.required("precondition")),
                effect=self._effects.read(fields.required("effect")),
                success_text=people_text(fields.required("success_text")),
                shows_on_success=tuple(self._shown(shown) for shown in fields.required("shows_on_success").items()),
                exertion=exertion(fields.required("exertion")),
                actor_requirement=actor_requirement(fields.required("actor_requirement")),
                perceived_as=self._perceptions.perception(fields.nested("perceived_as"), has_target),
                reaches_unseen=fields.required("reaches_unseen").boolean(),
                duration=duration(fields.required("duration")),
                allows_stealth=fields.required("allows_stealth").boolean(),
                arguments=tuple(
                    ArgumentDeclaration(name=ArgumentName(argument_name), kind=words(kind, _ARGUMENT_KINDS))
                    for argument_name, kind in fields.required("arguments").entries()
                ),
            )
        )

    def _entries(self, node: YamlNode) -> list[tuple[str, YamlNode]]:
        return self._collector.attempt(node.entries) or []

    def _add(self, into: list[_Declaration], read: Callable[[], _Declaration]) -> None:
        declaration = self._collector.attempt(read)
        if declaration is not None:
            into.append(declaration)

    def _object_interactions(self, name: str, node: YamlNode) -> None:
        fields = self._collector.attempt(lambda: self._defaults.fill("object", node).fields(*OBJECT_FIELDS))
        if fields is None:
            return
        for interaction_name, interaction in self._entries(fields.nested("interactions")):
            self._add(
                self._read.object_interactions,
                lambda: ObjectInteractionDeclaration(
                    obj=self._names.object(YamlNode(name, node.path)),
                    interaction=self.interaction(interaction_name, interaction, has_target=False),
                ),
            )

    def _item_verbs(self, name: str, node: YamlNode) -> None:
        fields = self._collector.attempt(lambda: self._defaults.fill("item_spec", node).fields(*ITEM_SPEC_FIELDS))
        if fields is None:
            return
        for interaction_name, interaction in self._entries(fields.nested("interactions")):
            self._add(
                self._read.item_interactions,
                lambda: ItemInteractionDeclaration(
                    item_spec=self._names.item_spec(YamlNode(name, node.path)),
                    interaction=self.interaction(interaction_name, interaction, has_target=False),
                ),
            )
        use = fields.optional("use")
        if use is not None:
            self._add(
                self._read.item_uses,
                lambda: ItemUseDeclaration(
                    item_spec=self._names.item_spec(YamlNode(name, node.path)), effect=self._effects.read(use)
                ),
            )

    def _section_access(self, name: str, node: YamlNode) -> SectionAccessDeclaration:
        section = self._names.section(YamlNode(name, node.path))
        fields = self._defaults.fill("section", node).fields(*SECTION_FIELDS)
        access_node = fields.required("access")
        access = self._defaults.fill("section_access", access_node).fields(*_ACCESS_FIELDS)
        return access_node.build(
            lambda: SectionAccessDeclaration(
                section=section,
                enter_label=display_name(access.required("enter_label")),
                leave_label=display_name(access.required("leave_label")),
                enter_text=people_text(access.required("enter_text")),
                leave_text=people_text(access.required("leave_text")),
                exertion=exertion(access.required("exertion")),
                duration=duration(access.required("duration")),
                entry_condition=self._conditions.read(access.required("entry_condition")),
                perceived_as=self._perceptions.perception(access.nested("perceived_as"), has_target=False),
            )
        )

    def _discoverable(self, name: str, spot: str, node: YamlNode) -> DiscoverableDeclaration:
        fields = self._defaults.fill("discoverable", node).fields("found_text", "condition", "when_found", "finding")
        return node.build(
            lambda: DiscoverableDeclaration(
                discoverable_id=DiscoverableId(name),
                spot_id=SpotId(spot),
                found_text=people_text(fields.required("found_text")),
                condition=self._conditions.read(fields.required("condition")),
                when_found=self._effects.read(fields.required("when_found")),
                finding=words(fields.required("finding"), _FINDINGS),
            )
        )

    def _add_traversal(self, name: str, node: YamlNode) -> None:
        fields = self._collector.attempt(lambda: self._defaults.fill("passage", node).fields(*PASSAGE_FIELDS))
        if fields is None:
            return
        condition = fields.optional("condition")
        if condition is None or condition.is_null():
            return
        self._add(
            self._read.passage_traversals,
            lambda: PassageTraversalDeclaration(
                passage=self._names.passage(YamlNode(name, node.path)), condition=self._conditions.read(condition)
            ),
        )

    def _world_stage_effects(self, name: str, node: YamlNode) -> WorldStageEffectsDeclaration:
        fields = self._defaults.fill("world_stage", node).fields(*WORLD_STAGE_FIELDS)
        return WorldStageEffectsDeclaration(
            stage=self._names.world_stage(YamlNode(name, node.path)),
            when_entered=self._effects.read(fields.required("when_entered")),
            when_left=self._effects.read(fields.required("when_left")),
        )

    def _group_decision_rules(self, name: str, node: YamlNode) -> GroupDecisionRulesDeclaration:
        fields = self._defaults.fill("group_decision", node).fields(*GROUP_DECISION_FIELDS)
        return GroupDecisionRulesDeclaration(
            decision=self._names.group_decision(YamlNode(name, node.path)),
            voters=self._conditions.people(fields.required("voters")),
            choices=self._conditions.people(fields.required("choices")),
            when_decided=self._effects.read(fields.required("when_decided")),
            when_undecided=self._effects.read(fields.required("when_undecided")),
        )

    def _happening(self, name: str, node: YamlNode) -> HappeningDeclaration:
        fields = self._defaults.fill("happening", node).fields("condition", "effect", "once", "notice")
        return node.build(
            lambda: HappeningDeclaration(
                happening_id=HappeningId(name),
                condition=self._conditions.read(fields.required("condition")),
                effect=self._effects.read(fields.required("effect")),
                once=fields.required("once").boolean(),
                notice=self._perceptions.notice(fields.required("notice")),
            )
        )

    def _reaction(self, name: str, node: YamlNode) -> ReactionDeclaration:
        fields = self._defaults.fill("reaction", node).fields("condition", "when_becomes_true", "when_becomes_false")
        return node.build(
            lambda: ReactionDeclaration(
                reaction_id=ReactionId(name),
                condition=self._conditions.read(fields.required("condition")),
                when_becomes_true=self._effects.read(fields.required("when_becomes_true")),
                when_becomes_false=self._effects.read(fields.required("when_becomes_false")),
            )
        )

    def _joint_action(self, name: str, node: YamlNode) -> JointActionDeclaration:
        fields = self._defaults.fill("joint_action", node).fields(
            "required", "window", "distinct_people", "on_complete", "on_timeout", "complete_notice", "timeout_notice"
        )
        required = []
        for part in fields.required("required").items():
            part_fields = part.fields("object", "interaction")
            obj = self._names.object(part_fields.required("object"))
            interaction = part_fields.required("interaction")
            required.append((obj.object_id, interaction.build(lambda: InteractionId(interaction.text()))))
        return node.build(
            lambda: JointActionDeclaration(
                joint_id=JointActionId(name),
                required=tuple[tuple[ObjectId, InteractionId], ...](required),
                window=ticks(fields.required("window")),
                distinct_people=fields.required("distinct_people").boolean(),
                on_complete=self._effects.read(fields.required("on_complete")),
                on_timeout=self._effects.read(fields.required("on_timeout")),
                complete_notice=self._perceptions.notice(fields.required("complete_notice")),
                timeout_notice=self._perceptions.notice(fields.required("timeout_notice")),
            )
        )

    def _shown(self, node: YamlNode) -> ShownToActor:
        kinded = split_kind(node, _SHOWN_KINDS, explains_failure=False)
        if kinded.kind == "people_count_at":
            return PeopleCountAt(spot=self._names.spot(kinded.single("spot")))
        return kinded.body.build(lambda: WrittenTextOf(key=self._names.object_state_key(kinded.single("key"))))
