from __future__ import annotations

import heapq
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.being.contract import Description, Orientation
from ai_rpg_world.game_world.domain.action.offered_action import ActionChoiceKind
from ai_rpg_world.game_world.domain.condition.condition import Condition, NoText
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition
from ai_rpg_world.game_world.domain.declaration.belongings_texts import BelongingsTexts
from ai_rpg_world.game_world.domain.declaration.briefing_headings import BriefingHeadings
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.initial_world import InitialWorld
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.declaration.rule_placement import RulePlacement
from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SurroundingsTexts
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    ClockWording,
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
from ai_rpg_world.game_world.domain.declaration.verb.action_texts import ActionTextKey, ActionTexts
from ai_rpg_world.game_world.domain.declaration.world_design_review import (
    DeclaredWorldTime,
    WorldDesignReview,
    design_location,
    duplicate_flaws,
    labels_alike_flaws,
    one_per_noun_flaws,
)
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.declaration.world_map import WorldMap, WorldMapWording
from ai_rpg_world.game_world.domain.declaration.world_words import WorldWords
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation, DesignWarning
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import ItemNotUsableException
from ai_rpg_world.game_world.domain.exception.world_design_exception import (
    UndeclaredVerbException,
    WorldDesignFlawsException,
)
from ai_rpg_world.game_world.domain.perception.own_action_completion import OwnActionCompletion
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
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.whereabouts.route import NoRoute, Route
from ai_rpg_world.game_world.domain.whereabouts.whereabouts_events import Teleported

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
    from ai_rpg_world.game_world.domain.perception.stimulus import Stimulus
    from ai_rpg_world.game_world.domain.whereabouts import Occupant

_WORLD_LOCATION = DesignLocation("world", "world", "")
_ALWAYS = AllOfCondition(children=(), failure_text=NoText())


@final
@dataclass(frozen=True)
class NotUsable:
    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        raise ItemNotUsableException("the item has no declared use")


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
        action_texts: ActionTexts,
        surroundings_texts: SurroundingsTexts,
        clock_wording: ClockWording,
        belongings_texts: BelongingsTexts,
        world_map_wording: WorldMapWording,
        world_words: WorldWords,
        weather: WeatherDeclaration | NoWeather,
        day_night: DayNightDeclaration | NoDayNight,
        initial_stage: WorldStageDeclaration | NoWorldStages,
        introduction: WorldIntroduction,
        briefing_headings: BriefingHeadings,
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
        self._action_texts = action_texts
        self._surroundings_texts = surroundings_texts
        self._clock_wording = clock_wording
        self._belongings_texts = belongings_texts
        self._world_map_wording = world_map_wording
        self._world_words = world_words
        self._weather = weather
        self._day_night = day_night
        self._initial_stage = initial_stage
        self._introduction = introduction
        self._briefing_headings = briefing_headings
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
        action_texts: ActionTexts,
        surroundings_texts: SurroundingsTexts,
        clock_wording: ClockWording,
        belongings_texts: BelongingsTexts,
        world_map_wording: WorldMapWording,
        world_words: WorldWords,
        weather: WeatherDeclaration | NoWeather,
        day_night: DayNightDeclaration | NoDayNight,
        initial_stage: WorldStageDeclaration | NoWorldStages,
        introduction: WorldIntroduction,
        briefing_headings: BriefingHeadings,
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
            review.author_text(placement.at_field("enter_text"), access.enter_text, ActionTextKey.ENTER_SECTION)
            review.author_text(placement.at_field("leave_text"), access.leave_text, ActionTextKey.LEAVE_SECTION)
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
        for phase in day_night.declared_phases():
            location = replace(_WORLD_LOCATION, field=f"time.day_night.phases.{phase.name.value}.audience")
            placement = RulePlacement.in_world(location)
            review.requirements(placement, phase.audience.requirements())
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
        review.flaws += labels_alike_flaws(
            (
                design_location(
                    "object_interaction", d.obj.object_id, d.interaction.interaction_id, field="display_label"
                ),
                d.obj.object_id,
                d.interaction.display_label.text,
            )
            for d in object_interactions
        )
        review.flaws += labels_alike_flaws(
            (
                design_location(
                    "item_interaction", d.item_spec.item_spec_id, d.interaction.interaction_id, field="display_label"
                ),
                d.item_spec.item_spec_id,
                d.interaction.display_label.text,
            )
            for d in item_interactions
        )
        review.flaws += labels_alike_flaws(
            (
                design_location("person_interaction", i.interaction_id, field="display_label"),
                "person",
                i.display_label.text,
            )
            for i in person_interactions
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
            action_texts=action_texts,
            surroundings_texts=surroundings_texts,
            clock_wording=clock_wording,
            belongings_texts=belongings_texts,
            world_map_wording=world_map_wording,
            world_words=world_words,
            weather=weather,
            day_night=day_night,
            initial_stage=initial_stage,
            introduction=introduction,
            briefing_headings=briefing_headings,
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
    def briefing_headings(self) -> BriefingHeadings:
        return self._briefing_headings

    @property
    def refusal_texts(self) -> RefusalTexts:
        return self._refusal_texts

    @property
    def built_in_action_perceptions(self) -> BuiltInActionPerceptions:
        return self._built_in_action_perceptions

    @property
    def action_texts(self) -> ActionTexts:
        return self._action_texts

    @property
    def surroundings_texts(self) -> SurroundingsTexts:
        return self._surroundings_texts

    def orientation(self) -> Orientation:
        return self._briefing_headings.orientation(
            self._introduction, self.world_map_text(), self._ending.has_deadline()
        )

    def arrival_stimuli(
        self, where: SpotId, arriving: Occupant, origin: SpotId | Teleported, at: WorldTick
    ) -> tuple[Stimulus, ...]:
        seen = self._built_in_action_perceptions.arrival_seen_at(where, arriving, origin, self._nouns, at)
        if isinstance(origin, Teleported):
            return seen
        names = {"destination": self._nouns.spot_of(where).name}
        people = {"actor": arriving.person}
        completion = OwnActionCompletion(
            person=arriving.person,
            summary=self._action_texts.summary_of(ActionTextKey.ARRIVAL).about_named(people, names),
            text=self._action_texts.done_of(ActionTextKey.ARRIVAL).about_named(people, names),
            tool=ActionChoiceKind.TRAVEL_TO.choice_name,
            at=at,
        )
        return (completion, *seen)

    def world_map_text(self) -> str | None:
        if not self._introduction.shows_world_map:
            return None
        return WorldMap.drawn_from(self._nouns).written_with(self._world_map_wording, self._day_night)

    @property
    def clock_wording(self) -> ClockWording:
        return self._clock_wording

    @property
    def belongings_texts(self) -> BelongingsTexts:
        return self._belongings_texts

    @property
    def world_words(self) -> WorldWords:
        return self._world_words

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

    def is_usable(self, item_spec: ItemSpecId) -> bool:
        return item_spec in self._item_uses

    def section_access(self, section: SpotSectionId) -> SectionAccessDeclaration:
        if section not in self._section_accesses:
            raise UndeclaredVerbException(f"section {section.value!r} has no access declared")
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
        if decision not in self._group_decision_rules:
            raise UndeclaredVerbException(f"group decision {decision.value!r} has no rules declared")
        return self._group_decision_rules[decision]

    def person_interaction(self, interaction: InteractionId) -> InteractionDeclaration:
        if interaction not in self._person_interactions:
            raise UndeclaredVerbException(f"no interaction {interaction.value!r} is declared on people")
        return self._person_interactions[interaction]

    def person_interactions(self) -> tuple[InteractionDeclaration, ...]:
        return tuple(self._person_interactions.values())

    def happenings(self) -> tuple[HappeningDeclaration, ...]:
        return self._happenings

    def happening(self, happening: HappeningId) -> HappeningDeclaration:
        for declared in self._happenings:
            if declared.happening_id == happening:
                return declared
        raise UndeclaredVerbException(f"no happening {happening.value!r} is declared")

    def joint_actions(self) -> tuple[JointActionDeclaration, ...]:
        return self._joint_actions

    def joint_action(self, joint: JointActionId) -> JointActionDeclaration:
        for declared in self._joint_actions:
            if declared.joint_id == joint:
                return declared
        raise UndeclaredVerbException(f"no joint action {joint.value!r} is declared")

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
