from __future__ import annotations

from collections.abc import Iterable

import pytest

from ai_rpg_world.game_world.domain.action.action_attempt import DoesNotUseBody
from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusalKind
from ai_rpg_world.game_world.domain.declaration.character import (
    CharacterDeclaration,
    GroupDeclaration,
    GroupingDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import UsesWorldDefault
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    LastsIndefinitely,
    NotALightSource,
    ObjectAppearance,
    ObjectDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress import (
    AllActionsAllowed,
    FlagDeclaration,
    GroupDecisionDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.declaration.spot import (
    NoAmbientSound,
    NoCapacity,
    NoSmell,
    PassageDeclaration,
    SpotAtmosphere,
    SpotDeclaration,
    SpotSectionDeclaration,
    Temperature,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    NoDayNight,
    NoWeather,
    WeatherDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.verb import (
    BuiltInActionPerceptions,
    DefaultDuration,
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
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw
from ai_rpg_world.game_world.domain.exception.world_design_exception import WorldDesignFlawsException
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    GroupDecisionId,
    ItemSpecId,
    ObjectId,
    PassageId,
    PersonId,
    SpotId,
    SpotSectionId,
    Ticks,
    WorldStageId,
)
from ai_rpg_world.game_world.domain.value_object.hands_needed import HandsNeeded
from tests.game_world.support.declarations_for_tests import OPEN as OPEN_STATE
from tests.game_world.support.declarations_for_tests import open_passage_states
from tests.game_world.support.verb_declarations_for_tests import lever_pulled_quietly
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_KINDS_PERCEIVED_THROUGH_DECLARATIONS = frozenset(
    {
        ActionKind.INTERACT_WITH_OBJECT,
        ActionKind.INTERACT_WITH_CARRIED_ITEM,
        ActionKind.INTERACT_WITH_PERSON,
        ActionKind.ENTER_SECTION,
        ActionKind.LEAVE_SECTION,
        ActionKind.ATTACK_MONSTER,
    }
)


def spot(name: str) -> SpotDeclaration:
    return SpotDeclaration(
        spot_id=SpotId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の様子"),
        atmosphere=SpotAtmosphere(
            lighting=Lighting.BRIGHT,
            outdoor=False,
            temperature=Temperature.NORMAL,
            ambient_sound=NoAmbientSound(),
            smell=NoSmell(),
        ),
    )


def passage(name: str, ends: tuple[str, str], travel_ticks: int = 1, two_way: bool = True) -> PassageDeclaration:
    return PassageDeclaration(
        passage_id=PassageId(name),
        name=DisplayName(f"{name} の通路"),
        description=DescriptionText(f"{name} の様子"),
        ends=(SpotId(ends[0]), SpotId(ends[1])),
        two_way=two_way,
        travel_ticks=Ticks(travel_ticks),
        states=open_passage_states(),
        initial_state=OPEN_STATE,
        hidden_until_revealed=False,
    )


def section(name: str, at_spot: str) -> SpotSectionDeclaration:
    return SpotSectionDeclaration(
        section_id=SpotSectionId(name),
        spot_id=SpotId(at_spot),
        name=DisplayName(name),
        capacity=NoCapacity(),
        reachable_objects=(),
    )


def obj(name: str, at_spot: str) -> ObjectDeclaration:
    return ObjectDeclaration(
        object_id=ObjectId(name),
        spot_id=SpotId(at_spot),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の見た目"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=False),
        state_keys=(),
    )


def item_spec(name: str) -> ItemSpecDeclaration:
    return ItemSpecDeclaration(
        item_spec_id=ItemSpecId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の見た目"),
        state_keys=(),
        lights_up=NotALightSource(),
        hands_needed=HandsNeeded(1),
        lasts=LastsIndefinitely(),
    )


def group_decision(name: str) -> GroupDecisionDeclaration:
    return GroupDecisionDeclaration(
        decision_id=GroupDecisionId(name), name=DisplayName(name), abstain_allowed=True, reveals_ballots=False
    )


def world_stage(name: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        allowed_actions=AllActionsAllowed(),
    )


def access_to(declared_section: SpotSectionDeclaration) -> SectionAccessDeclaration:
    return SectionAccessDeclaration(
        section=declared_section,
        enter_label=DisplayName("乗り込む"),
        leave_label=DisplayName("降りる"),
        enter_text=TextWithUnassignedPeople("乗り込んだ。"),
        leave_text=TextWithUnassignedPeople("降りた。"),
        exertion=DoesNotUseBody(),
        duration=DefaultDuration(),
        entry_condition=AlwaysHolds(),
        perceived_as=lever_pulled_quietly(),
    )


def character(name: str, spawn_spot: str) -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=PersonId(name),
        appearance=DescriptionText(f"{name} の見た目"),
        spawn_spot=SpotId(spawn_spot),
        initial_items=(),
        initial_held=(),
        initial_groups=(),
        knows_at_start=(),
        max_hp=UsesWorldDefault(),
        pack_capacity=UsesWorldDefault(),
    )


def nouns(
    flags: Iterable[FlagDeclaration] = (),
    spots: Iterable[SpotDeclaration] = (),
    passages: Iterable[PassageDeclaration] = (),
    objects: Iterable[ObjectDeclaration] = (),
    item_specs: Iterable[ItemSpecDeclaration] = (),
    groupings: Iterable[GroupingDeclaration] = (),
    groups: Iterable[GroupDeclaration] = (),
    characters: Iterable[CharacterDeclaration] = (),
    world_stages: Iterable[WorldStageDeclaration] = (),
    group_decisions: Iterable[GroupDecisionDeclaration] = (),
    sections: Iterable[SpotSectionDeclaration] = (),
) -> DeclaredNouns:
    return DeclaredNouns(
        flags=flags,
        spots=spots,
        passages=passages,
        objects=objects,
        item_specs=item_specs,
        groupings=groupings,
        groups=groups,
        characters=characters,
        world_stages=world_stages,
        group_decisions=group_decisions,
        sections=sections,
        outcomes=(),
    )


def refusal_texts() -> RefusalTexts:
    return RefusalTexts(
        common_rules={
            kind: TextWithUnassignedPeople(f"{kind.name} のためできない。") for kind in CommonRuleRefusalKind
        },
        world_state={},
        hidden=TextWithUnassignedPeople("今はできない。"),
    )


def built_in_action_perceptions(without: Iterable[ActionKind] = ()) -> BuiltInActionPerceptions:
    kinds = frozenset(ActionKind) - _KINDS_PERCEIVED_THROUGH_DECLARATIONS - frozenset(without)
    return BuiltInActionPerceptions(by_kind={kind: lever_pulled_quietly() for kind in kinds})


def introduction() -> WorldIntroduction:
    return WorldIntroduction(
        text=DescriptionText("山あいの廃坑の村で目を覚ました。"),
        objective=DescriptionText("坑道から外へ出る。"),
    )


def compose_world(
    nouns_: DeclaredNouns | None = None,
    object_interactions: Iterable[ObjectInteractionDeclaration] = (),
    item_interactions: Iterable[ItemInteractionDeclaration] = (),
    item_uses: Iterable[ItemUseDeclaration] = (),
    section_accesses: Iterable[SectionAccessDeclaration] = (),
    passage_traversals: Iterable[PassageTraversalDeclaration] = (),
    world_stage_effects: Iterable[WorldStageEffectsDeclaration] = (),
    object_looks: Iterable[ObjectLooksDeclaration] = (),
    group_decision_rules: Iterable[GroupDecisionRulesDeclaration] = (),
    happenings: Iterable[HappeningDeclaration] = (),
    reactions: Iterable[ReactionDeclaration] = (),
    discoverables: Iterable[DiscoverableDeclaration] = (),
    joint_actions: Iterable[JointActionDeclaration] = (),
    person_interactions: Iterable[InteractionDeclaration] = (),
    ending: EndingDeclaration | None = None,
    world_rules: WorldRules | None = None,
    refusal_texts_: RefusalTexts | None = None,
    built_in_action_perceptions_: BuiltInActionPerceptions | None = None,
    weather: WeatherDeclaration | NoWeather = NoWeather(),
    day_night: DayNightDeclaration | NoDayNight = NoDayNight(),
    initial_stage: WorldStageDeclaration | NoWorldStages = NoWorldStages(),
) -> WorldDesign:
    return WorldDesign.compose(
        nouns=nouns_ if nouns_ is not None else nouns(),
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
        ending=ending if ending is not None else EndingDeclaration(ends_when=AlwaysHolds()),
        world_rules=world_rules if world_rules is not None else world_rules_for_tests(),
        refusal_texts=refusal_texts_ if refusal_texts_ is not None else refusal_texts(),
        built_in_action_perceptions=(
            built_in_action_perceptions_
            if built_in_action_perceptions_ is not None
            else built_in_action_perceptions(without=(ActionKind.TEND,))
        ),
        weather=weather,
        day_night=day_night,
        initial_stage=initial_stage,
        introduction=introduction(),
    )


def flaws_of_composing(**declarations: object) -> tuple[DesignFlaw, ...]:
    with pytest.raises(WorldDesignFlawsException) as raised:
        compose_world(**declarations)  # type: ignore[arg-type]
    return raised.value.flaws
