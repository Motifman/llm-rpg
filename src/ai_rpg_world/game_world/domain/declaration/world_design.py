from __future__ import annotations

import heapq
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import final

from ai_rpg_world.game_world.domain.condition.condition import Condition, NoText
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.initial_world import InitialWorld
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.declaration.rule_placement import RulePlacement
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    NoDayNight,
    NoWeather,
    WeatherDeclaration,
    WeatherState,
)
from ai_rpg_world.game_world.domain.declaration.verb import (
    BuiltInActionPerceptions,
    DiscoverableDeclaration,
    EndingDeclaration,
    GroupDecisionRulesDeclaration,
    HappeningDeclaration,
    InteractionDeclaration,
    ItemInteractionDeclaration,
    ItemUseDeclaration,
    JointActionDeclaration,
    ObjectInteractionDeclaration,
    ObjectLooksDeclaration,
    PassageTraversalDeclaration,
    ReactionDeclaration,
    SectionAccessDeclaration,
    WorldStageEffectsDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.world_design_review import (
    DeclaredWorldTime,
    WorldDesignReview,
    design_location,
    duplicate_flaws,
    one_per_noun_flaws,
)
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation, DesignWarning
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.exception.world_design_exception import (
    UndeclaredVerbException,
    WorldDesignFlawsException,
)
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import (
    GroupDecisionId,
    InteractionId,
    ItemSpecId,
    ObjectId,
    PassageId,
    SpotId,
    SpotSectionId,
    WorldStageId,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.whereabouts.route import NoRoute, Route

_WORLD_LOCATION = DesignLocation("world", "world", "")
_ALWAYS = AllOfCondition(children=(), failure_text=NoText())


@final
@dataclass(frozen=True)
class NotUsable:
    pass


def _declared_arguments(interaction: InteractionDeclaration) -> frozenset[ArgumentName]:
    return frozenset(argument.name for argument in interaction.arguments)


class WorldDesign:
    def __init__(
        self,
        nouns: DeclaredNouns,
        object_interactions: tuple[ObjectInteractionDeclaration, ...],
        item_interactions: tuple[ItemInteractionDeclaration, ...],
        item_uses: tuple[ItemUseDeclaration, ...],
        section_accesses: tuple[SectionAccessDeclaration, ...],
        passage_traversals: tuple[PassageTraversalDeclaration, ...],
        world_stage_effects: tuple[WorldStageEffectsDeclaration, ...],
        object_looks: tuple[ObjectLooksDeclaration, ...],
        group_decision_rules: tuple[GroupDecisionRulesDeclaration, ...],
        happenings: tuple[HappeningDeclaration, ...],
        reactions: tuple[ReactionDeclaration, ...],
        discoverables: tuple[DiscoverableDeclaration, ...],
        joint_actions: tuple[JointActionDeclaration, ...],
        person_interactions: tuple[InteractionDeclaration, ...],
        ending: EndingDeclaration,
        world_rules: WorldRules,
        refusal_texts: RefusalTexts,
        built_in_action_perceptions: BuiltInActionPerceptions,
        weather: WeatherDeclaration | NoWeather,
        day_night: DayNightDeclaration | NoDayNight,
        initial_stage: WorldStageDeclaration | NoWorldStages,
        introduction: WorldIntroduction,
        warnings: tuple[DesignWarning, ...],
    ) -> None:
        self._nouns = nouns
        self._object_interactions = {
            (declared.obj.object_id, declared.interaction.interaction_id): declared.interaction
            for declared in object_interactions
        }
        self._item_interactions = {
            (declared.item_spec.item_spec_id, declared.interaction.interaction_id): declared.interaction
            for declared in item_interactions
        }
        self._item_uses = {declared.item_spec.item_spec_id: declared for declared in item_uses}
        self._section_accesses = {declared.section.section_id: declared for declared in section_accesses}
        self._passage_traversals = {declared.passage.passage_id: declared.condition for declared in passage_traversals}
        self._world_stage_effects = {declared.stage.stage_id: declared for declared in world_stage_effects}
        self._object_looks = {declared.object_id: declared for declared in object_looks}
        self._group_decision_rules = {declared.decision.decision_id: declared for declared in group_decision_rules}
        self._happenings = happenings
        self._reactions = reactions
        self._discoverables = discoverables
        self._joint_actions = joint_actions
        self._person_interactions = {declared.interaction_id: declared for declared in person_interactions}
        self._ending = ending
        self._world_rules = world_rules
        self._refusal_texts = refusal_texts
        self._built_in_action_perceptions = built_in_action_perceptions
        self._weather = weather
        self._day_night = day_night
        self._initial_stage = initial_stage
        self._introduction = introduction
        self._warnings = warnings

    @classmethod
    def compose(
        cls,
        nouns: DeclaredNouns,
        object_interactions: Iterable[ObjectInteractionDeclaration],
        item_interactions: Iterable[ItemInteractionDeclaration],
        item_uses: Iterable[ItemUseDeclaration],
        section_accesses: Iterable[SectionAccessDeclaration],
        passage_traversals: Iterable[PassageTraversalDeclaration],
        world_stage_effects: Iterable[WorldStageEffectsDeclaration],
        object_looks: Iterable[ObjectLooksDeclaration],
        group_decision_rules: Iterable[GroupDecisionRulesDeclaration],
        happenings: Iterable[HappeningDeclaration],
        reactions: Iterable[ReactionDeclaration],
        discoverables: Iterable[DiscoverableDeclaration],
        joint_actions: Iterable[JointActionDeclaration],
        person_interactions: Iterable[InteractionDeclaration],
        ending: EndingDeclaration,
        world_rules: WorldRules,
        refusal_texts: RefusalTexts,
        built_in_action_perceptions: BuiltInActionPerceptions,
        weather: WeatherDeclaration | NoWeather,
        day_night: DayNightDeclaration | NoDayNight,
        initial_stage: WorldStageDeclaration | NoWorldStages,
        introduction: WorldIntroduction,
    ) -> WorldDesign:
        object_interactions = tuple(object_interactions)
        item_interactions = tuple(item_interactions)
        item_uses = tuple(item_uses)
        section_accesses = tuple(section_accesses)
        passage_traversals = tuple(passage_traversals)
        world_stage_effects = tuple(world_stage_effects)
        object_looks = tuple(object_looks)
        group_decision_rules = tuple(group_decision_rules)
        happenings = tuple(happenings)
        reactions = tuple(reactions)
        discoverables = tuple(discoverables)
        joint_actions = tuple(joint_actions)
        person_interactions = tuple(person_interactions)

        review = WorldDesignReview(DeclaredWorldTime.of(initial_stage, day_night, weather))
        for declared in object_interactions:
            review.interaction(
                RulePlacement.in_action(
                    design_location(
                        "object_interaction", declared.obj.object_id, declared.interaction.interaction_id, field=""
                    ),
                    _declared_arguments(declared.interaction),
                ),
                declared.interaction,
            )
        for on_item in item_interactions:
            review.interaction(
                RulePlacement.in_action(
                    design_location(
                        "item_interaction",
                        on_item.item_spec.item_spec_id,
                        on_item.interaction.interaction_id,
                        field="",
                    ),
                    _declared_arguments(on_item.interaction),
                ),
                on_item.interaction,
            )
        for interaction in person_interactions:
            review.interaction(
                RulePlacement.in_person_interaction(
                    design_location("person_interaction", interaction.interaction_id, field=""),
                    _declared_arguments(interaction),
                ),
                interaction,
            )
        for use in item_uses:
            review.effect(
                RulePlacement.in_action(
                    design_location("item_use", use.item_spec.item_spec_id, field="effect"), frozenset()
                ),
                use.effect,
            )
        for access in section_accesses:
            placement = RulePlacement.in_action(
                design_location("section_access", access.section.section_id, field=""), frozenset()
            )
            review.precondition(placement.at_field("entry_condition"), access.entry_condition)
            review.perception(placement, access.perceived_as)
        for traversal in passage_traversals:
            review.precondition(
                RulePlacement.in_action(
                    design_location("passage_traversal", traversal.passage.passage_id, field="condition"), frozenset()
                ),
                traversal.condition,
            )
        for discoverable in discoverables:
            placement = RulePlacement.in_action(
                design_location("discoverable", discoverable.discoverable_id, field=""), frozenset()
            )
            review.condition(placement.at_field("condition"), discoverable.condition)
            review.effect(placement.at_field("when_found"), discoverable.when_found)
        for stage_effects in world_stage_effects:
            placement = RulePlacement.in_world(
                design_location("world_stage_effects", stage_effects.stage.stage_id, field="")
            )
            review.effect(placement.at_field("when_entered"), stage_effects.when_entered)
            review.effect(placement.at_field("when_left"), stage_effects.when_left)
        for rules in group_decision_rules:
            location = design_location("group_decision_rules", rules.decision.decision_id, field="")
            placement = RulePlacement.in_world(location)
            review.requirements(placement.at_field("voters"), rules.voters.requirements())
            review.requirements(placement.at_field("choices"), rules.choices.requirements())
            review.effect(RulePlacement.in_group_decision_result(location).at_field("when_decided"), rules.when_decided)
            review.effect(placement.at_field("when_undecided"), rules.when_undecided)
        for happening in happenings:
            placement = RulePlacement.in_world(design_location("happening", happening.happening_id, field=""))
            review.condition(placement.at_field("condition"), happening.condition)
            review.effect(placement.at_field("effect"), happening.effect)
            review.notice(placement.at_field("notice"), happening.notice)
        for reaction in reactions:
            placement = RulePlacement.in_world(design_location("reaction", reaction.reaction_id, field=""))
            review.condition(placement.at_field("condition"), reaction.condition)
            review.effect(placement.at_field("when_becomes_true"), reaction.when_becomes_true)
            review.effect(placement.at_field("when_becomes_false"), reaction.when_becomes_false)
        for joint in joint_actions:
            placement = RulePlacement.in_world(design_location("joint_action", joint.joint_id, field=""))
            review.effect(placement.at_field("on_complete"), joint.on_complete)
            review.effect(placement.at_field("on_timeout"), joint.on_timeout)
            review.notice(placement.at_field("complete_notice"), joint.complete_notice)
            review.notice(placement.at_field("timeout_notice"), joint.timeout_notice)
        review.condition(RulePlacement.in_world(DesignLocation("ending", "ending", "ends_when")), ending.ends_when)
        for declared_looks in object_looks:
            for index, look in enumerate(declared_looks.looks):
                review.condition(
                    RulePlacement.in_object_look(
                        design_location("object_looks", declared_looks.object_id, field=f"looks[{index}]")
                    ),
                    look.when,
                )

        for kind, perception in built_in_action_perceptions.by_kind.items():
            review.requirements(
                RulePlacement.in_person_interaction(
                    DesignLocation("built_in_action_perceptions", kind.name, "announcement"), frozenset()
                ),
                perception.requirements(),
            )
        review.flaws += world_rules.design_flaws(replace(_WORLD_LOCATION, field="world_rules"))
        review.flaws += built_in_action_perceptions.flaws_for(
            world_rules, replace(_WORLD_LOCATION, field="built_in_action_perceptions")
        )
        review.flaws += one_per_noun_flaws(
            "section",
            "section_access",
            "section",
            [section.section_id for section in nouns.all_sections()],
            [access.section.section_id for access in section_accesses],
        )
        review.flaws += one_per_noun_flaws(
            "group_decision",
            "group_decision_rules",
            "decision",
            [decision.decision_id for decision in nouns.all_group_decisions()],
            [rules.decision.decision_id for rules in group_decision_rules],
        )
        review.flaws += duplicate_flaws(
            "object_interaction",
            [(declared.obj.object_id, declared.interaction.interaction_id) for declared in object_interactions],
            "interaction",
        )
        review.flaws += duplicate_flaws(
            "item_interaction",
            [(on_item.item_spec.item_spec_id, on_item.interaction.interaction_id) for on_item in item_interactions],
            "interaction",
        )
        review.flaws += duplicate_flaws("item_use", [(use.item_spec.item_spec_id,) for use in item_uses], "item_spec")
        review.flaws += duplicate_flaws(
            "person_interaction",
            [(interaction.interaction_id,) for interaction in person_interactions],
            "interaction_id",
        )
        review.flaws += duplicate_flaws(
            "passage_traversal", [(traversal.passage.passage_id,) for traversal in passage_traversals], "passage"
        )
        review.flaws += duplicate_flaws(
            "world_stage_effects", [(stage_effects.stage.stage_id,) for stage_effects in world_stage_effects], "stage"
        )
        review.flaws += duplicate_flaws(
            "object_looks", [(declared_looks.object_id,) for declared_looks in object_looks], "object_id"
        )
        review.flaws += [
            flaw
            for declared_looks in object_looks
            for flaw in nouns.object_flaws_if_unknown(
                declared_looks.object_id, design_location("object_looks", declared_looks.object_id, field="object_id")
            )
        ]
        review.flaws += duplicate_flaws(
            "happening", [(happening.happening_id,) for happening in happenings], "happening_id"
        )
        review.flaws += duplicate_flaws("reaction", [(reaction.reaction_id,) for reaction in reactions], "reaction_id")
        review.flaws += duplicate_flaws(
            "discoverable", [(discoverable.discoverable_id,) for discoverable in discoverables], "discoverable_id"
        )
        review.flaws += duplicate_flaws("joint_action", [(joint.joint_id,) for joint in joint_actions], "joint_id")
        declared_on_objects = {
            (declared.obj.object_id, declared.interaction.interaction_id) for declared in object_interactions
        }
        for joint in joint_actions:
            for index, (object_id, interaction_id) in enumerate(joint.required):
                if (object_id, interaction_id) not in declared_on_objects:
                    review.flaws.append(
                        DesignFlaw(
                            design_location("joint_action", joint.joint_id, field=f"required[{index}]"),
                            f"object {object_id.value!r} has no interaction {interaction_id.value!r}",
                        )
                    )

        review.flags(nouns.all_flags())
        review.group_decisions(nouns.all_group_decisions())
        review.happenings(happening.happening_id for happening in happenings)

        if review.flaws:
            raise WorldDesignFlawsException(review.flaws)
        return cls(
            nouns=nouns,
            object_interactions=object_interactions,
            item_interactions=item_interactions,
            item_uses=item_uses,
            section_accesses=section_accesses,
            passage_traversals=passage_traversals,
            world_stage_effects=world_stage_effects,
            object_looks=object_looks,
            group_decision_rules=group_decision_rules,
            happenings=happenings,
            reactions=reactions,
            discoverables=discoverables,
            joint_actions=joint_actions,
            person_interactions=person_interactions,
            ending=ending,
            world_rules=world_rules,
            refusal_texts=refusal_texts,
            built_in_action_perceptions=built_in_action_perceptions,
            weather=weather,
            day_night=day_night,
            initial_stage=initial_stage,
            introduction=introduction,
            warnings=tuple(review.warnings),
        )

    @property
    def nouns(self) -> DeclaredNouns:
        return self._nouns

    @property
    def world_rules(self) -> WorldRules:
        return self._world_rules

    @property
    def ending(self) -> EndingDeclaration:
        return self._ending

    @property
    def introduction(self) -> WorldIntroduction:
        return self._introduction

    @property
    def refusal_texts(self) -> RefusalTexts:
        return self._refusal_texts

    @property
    def built_in_action_perceptions(self) -> BuiltInActionPerceptions:
        return self._built_in_action_perceptions

    @property
    def weather(self) -> WeatherDeclaration | NoWeather:
        return self._weather

    @property
    def day_night(self) -> DayNightDeclaration | NoDayNight:
        return self._day_night

    def interaction_on_object(self, obj: ObjectId, interaction: InteractionId) -> InteractionDeclaration:
        if (obj, interaction) not in self._object_interactions:
            raise UndeclaredVerbException(f"object {obj.value!r} has no interaction {interaction.value!r}")
        return self._object_interactions[(obj, interaction)]

    def interaction_on_item(self, item_spec: ItemSpecId, interaction: InteractionId) -> InteractionDeclaration:
        if (item_spec, interaction) not in self._item_interactions:
            raise UndeclaredVerbException(f"item {item_spec.value!r} has no interaction {interaction.value!r}")
        return self._item_interactions[(item_spec, interaction)]

    def interactions_on_object(self, obj: ObjectId) -> tuple[InteractionDeclaration, ...]:
        return tuple(declared for (on, _), declared in self._object_interactions.items() if on == obj)

    def interactions_on_item(self, item_spec: ItemSpecId) -> tuple[InteractionDeclaration, ...]:
        return tuple(declared for (on, _), declared in self._item_interactions.items() if on == item_spec)

    def use_of_item(self, item_spec: ItemSpecId) -> ItemUseDeclaration | NotUsable:
        return self._item_uses.get(item_spec, NotUsable())

    def section_access(self, section: SpotSectionId) -> SectionAccessDeclaration:
        return self._section_accesses[section]

    def passage_traversal(self, passage: PassageId) -> Condition:
        return self._passage_traversals.get(passage, _ALWAYS)

    def world_stage_effects(self, stage: WorldStageId) -> WorldStageEffectsDeclaration:
        if stage in self._world_stage_effects:
            return self._world_stage_effects[stage]
        return WorldStageEffectsDeclaration(
            stage=self._nouns.world_stage_of(stage), when_entered=NoEffect(), when_left=NoEffect()
        )

    def looks_of(self, obj: ObjectId) -> ObjectLooksDeclaration:
        return self._object_looks.get(obj, ObjectLooksDeclaration(object_id=obj, looks=()))

    def group_decision_rules(self, decision: GroupDecisionId) -> GroupDecisionRulesDeclaration:
        return self._group_decision_rules[decision]

    def person_interaction(self, interaction: InteractionId) -> InteractionDeclaration:
        if interaction not in self._person_interactions:
            raise UndeclaredVerbException(f"no interaction {interaction.value!r} is declared on people")
        return self._person_interactions[interaction]

    def happenings(self) -> tuple[HappeningDeclaration, ...]:
        return self._happenings

    def joint_actions(self) -> tuple[JointActionDeclaration, ...]:
        return self._joint_actions

    def reactions(self) -> tuple[ReactionDeclaration, ...]:
        return self._reactions

    def discoverables_at(self, spot: SpotId) -> tuple[DiscoverableDeclaration, ...]:
        return tuple(discoverable for discoverable in self._discoverables if discoverable.spot_id == spot)

    def route(self, start: SpotId, destination: SpotId, passable: frozenset[PassageId]) -> Route | NoRoute:
        passages = tuple(passage for passage in self._nouns.all_passages() if passage.passage_id in passable)
        order = {passage.passage_id: index for index, passage in enumerate(passages)}
        frontier: list[tuple[int, int, tuple[int, ...], str]] = [(0, 0, (), start.value)]
        settled: set[str] = set()
        while frontier:
            ticks, count, path, here = heapq.heappop(frontier)
            if here in settled:
                continue
            settled.add(here)
            if here == destination.value and path:
                return Route(start=start, passages=tuple(passages[index] for index in path))
            for passage in passages:
                there = passage.far_end_from(SpotId(here))
                if there is not None:
                    heapq.heappush(
                        frontier,
                        (
                            ticks + passage.travel_ticks.value,
                            count + 1,
                            (*path, order[passage.passage_id]),
                            there.value,
                        ),
                    )
        return NoRoute()

    def initial_world(self) -> InitialWorld:
        return InitialWorld(
            people=self._nouns.starting_people(self._world_rules.person_max_hp, self._world_rules.pack_capacity),
            raised_flags=self._nouns.initially_raised_flags(),
            stage=self._initial_stage,
            weather=self._weather.initial_state(),
        )

    def warnings(self) -> tuple[DesignWarning, ...]:
        return self._warnings
