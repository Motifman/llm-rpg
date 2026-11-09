from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration, TextArgument
from ai_rpg_world.game_world.domain.action.trigger import Trigger
from ai_rpg_world.game_world.domain.condition.argument_condition import ArgumentEqualsCondition
from ai_rpg_world.game_world.domain.condition.chance_condition import ChanceCondition
from ai_rpg_world.game_world.domain.condition.condition import Condition, NoText
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.happening_conditions import (
    HappeningHasFiredCondition,
    TicksSinceHappeningAtLeastCondition,
)
from ai_rpg_world.game_world.domain.condition.membership_condition import IsMemberCondition
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.person_conditions import IsDownCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Actor, ChosenByGroup, NamedPerson, Target
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.condition.world_time_conditions import (
    TickAtLeastCondition,
    TimeOfDayIsCondition,
    WeatherIsCondition,
    WorldStageIsCondition,
)
from ai_rpg_world.game_world.domain.declaration.character import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.declaration.initial_world import StartingPerson
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseDeclaration,
    DayPhaseName,
    NoChange,
    NoWeather,
    WeatherDeclaration,
    WeatherState,
    WeatherType,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather.time_of_day import TimeOfDay
from ai_rpg_world.game_world.domain.declaration.verb import (
    AnnouncementTo,
    BuiltInActionPerceptions,
    DiscoverableDeclaration,
    EndingDeclaration,
    Finding,
    HappeningDeclaration,
    InteractionDeclaration,
    ItemInteractionDeclaration,
    ItemUseDeclaration,
    JointActionDeclaration,
    NoNotice,
    ObjectInteractionDeclaration,
    ObjectLook,
    ObjectLooksDeclaration,
    PassageTraversalDeclaration,
    ReactionDeclaration,
    WorldStageEffectsDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.world_design import NotUsable, WorldDesign
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.effect.body_effects import DamageEffect
from ai_rpg_world.game_world.domain.effect.combined_effects import ConditionalEffect, NoEffect
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from ai_rpg_world.game_world.domain.effect.world_progress_effects import CloseGroupDecisionEffect
from ai_rpg_world.game_world.domain.exception.world_design_exception import UndeclaredVerbException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Notable
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.tend_rule import TendRule
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Damage,
    DescriptionText,
    DisplayName,
    FlagId,
    GroupDecisionId,
    GroupId,
    GroupingId,
    HitPoints,
    InteractionId,
    ItemSpecId,
    ObjectId,
    PassageId,
    PersonId,
    Probability,
    Rate,
    SpotId,
    SpotSectionId,
    Ticks,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.whereabouts.route import NoRoute, Route
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on, pull_lever
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds, ChangesNothing
from tests.game_world.support.world_design_for_tests import (
    access_to,
    built_in_action_perceptions,
    character,
    compose_world,
    flaws_of_composing,
    group_decision,
    introduction,
    item_spec,
    nouns,
    obj,
    passage,
    refusal_texts,
    section,
    spot,
    world_stage,
)
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_REFUSED = TextWithUnassignedPeople("今はできない。")
_DAY_NIGHT = DayNightDeclaration(
    ticks_per_day=Ticks(4),
    starts_at=TimeOfDay(0),
    phases=(
        DayPhaseDeclaration(
            name=DayPhaseName("morning"), begins_at=TimeOfDay(0), dark=False, announcement=NoAnnouncement()
        ),
        DayPhaseDeclaration(
            name=DayPhaseName("night"), begins_at=TimeOfDay(2), dark=True, announcement=NoAnnouncement()
        ),
    ),
)
_WEATHER = WeatherDeclaration(
    initial=WeatherType.CLEAR, changes=NoChange(), announce_changes=False, obscuring=frozenset({WeatherType.FOG})
)
_ROLE = GroupingDeclaration(
    grouping_id=GroupingId("role"), name=DisplayName("役"), visibility=MembershipVisibility.SELF_ONLY, changes=False
)
_WOLVES = GroupDeclaration(
    group_id=GroupId("wolves"),
    grouping=_ROLE,
    name=DisplayName("狼"),
    members_know_each_other=False,
    shared_description=NoSharedDescription(),
)
_NO_FACTS = cast(WorldFacts, None)
_NO_TRIGGER = cast(Trigger, None)


def _strike(precondition: Condition) -> InteractionDeclaration:
    return replace(pull_lever(arguments=()), interaction_id=InteractionId("strike"), precondition=precondition)


class TestSubjectsByPlacement:
    """compose が、条件と効果を置いた場所ごとに使える主語を requirements() と照らし合わせることを保証する。"""

    def test_chosen_by_group_in_person_interaction_precondition_is_a_flaw(self) -> None:
        """人への操作 strike の前提で ChosenByGroup を見ると、strike の precondition を場所とする DesignFlaw になる。"""
        flaws = flaws_of_composing(
            person_interactions=(_strike(IsDownCondition(who=ChosenByGroup(), failure_text=_REFUSED)),)
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("person_interaction", "strike", "precondition")]

    def test_actor_and_target_in_person_interaction_precondition_are_allowed(self) -> None:
        """人への操作 strike の前提で Actor と Target を見ても、compose は断らない。"""
        compose_world(
            person_interactions=(
                _strike(IsDownCondition(who=Target(), failure_text=_REFUSED)),
                replace(
                    _strike(IsDownCondition(who=Actor(), failure_text=_REFUSED)),
                    interaction_id=InteractionId("kick"),
                ),
            )
        )


def _open_door(
    precondition: Condition | None = None, arguments: tuple[ArgumentDeclaration, ...] = ()
) -> ObjectInteractionDeclaration:
    interaction = replace(
        pull_lever(arguments=arguments),
        interaction_id=InteractionId("open"),
        precondition=precondition if precondition is not None else AlwaysHolds(),
    )
    return ObjectInteractionDeclaration(obj=obj("door", "hall"), interaction=interaction)


def _password_is(expected: str) -> ArgumentEqualsCondition:
    return ArgumentEqualsCondition(
        argument=ArgumentName("password"), expected=TextArgumentValue(expected), failure_text=_REFUSED
    )


def _happening(name: str, condition: Condition | None = None, effect: Effect | None = None) -> HappeningDeclaration:
    return HappeningDeclaration(
        happening_id=HappeningId(name),
        condition=condition if condition is not None else AlwaysHolds(),
        effect=effect if effect is not None else ChangesNothing(),
        once=True,
        notice=NoNotice(),
    )


_PASSWORD = ArgumentDeclaration(name=ArgumentName("password"), kind=TextArgument())
_HURT_CHOSEN = DamageEffect(who=ChosenByGroup(), amount=Damage(1))


class TestSubjectsOutsideActions:
    """行う人のいない場所 (出来事、集団の決定の結果) で使える主語を compose が確かめることを保証する。"""

    def test_actor_in_happening_effect_is_a_flaw(self) -> None:
        """出来事 cave_in の効果が Actor を傷つけると、happening cave_in の effect を場所とする DesignFlaw になる。"""
        flaws = flaws_of_composing(
            happenings=(_happening("cave_in", effect=DamageEffect(who=Actor(), amount=Damage(1))),)
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("happening", "cave_in", "effect")]

    def test_chosen_by_group_is_allowed_only_when_decided(self) -> None:
        """集団の決定 exile の when_decided では ChosenByGroup を使えるが、when_undecided で使うとそこだけが DesignFlaw になる。"""
        exile = group_decision("exile")
        rules = replace(everyone_votes_on(exile), when_decided=_HURT_CHOSEN, when_undecided=_HURT_CHOSEN)

        flaws = flaws_of_composing(nouns_=nouns(group_decisions=(exile,)), group_decision_rules=(rules,))

        assert [flaw.location for flaw in flaws] == [DesignLocation("group_decision_rules", "exile", "when_undecided")]

    def test_announcement_audience_is_checked_where_it_is_placed(self) -> None:
        """操作の知覚の知らせの相手で Target を、出来事の知らせの相手で Actor を選ぶと、それぞれの欄が DesignFlaw になる。"""
        to_target = AnnouncementTo(
            audience=PeopleSelection(where=IsDownCondition(who=Target(), failure_text=NoText())),
            text=TextWithUnassignedPeople("鐘が鳴った。"),
            salience=Notable(),
        )
        to_actor = replace(
            to_target, audience=PeopleSelection(where=IsDownCondition(who=Actor(), failure_text=NoText()))
        )
        door = _open_door()
        ringing_door = replace(
            door,
            interaction=replace(
                door.interaction, perceived_as=replace(door.interaction.perceived_as, announcement=to_target)
            ),
        )

        flaws = flaws_of_composing(
            object_interactions=(ringing_door,), happenings=(replace(_happening("bell"), notice=to_actor),)
        )

        assert {flaw.location for flaw in flaws} == {
            DesignLocation("object_interaction", "door/open", "perceived_as"),
            DesignLocation("happening", "bell", "notice"),
        }


class TestArgumentsRead:
    """効果と条件が読む引数の名前が、操作の宣言の arguments にあるかを compose が確かめることを保証する。"""

    def test_reading_an_undeclared_argument_is_a_flaw(self) -> None:
        """扉 door の操作 open の前提が、arguments に無い password を ArgumentEqualsCondition で読むと DesignFlaw になる。"""
        flaws = flaws_of_composing(object_interactions=(_open_door(precondition=_password_is("ひらけ")),))

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_interaction", "door/open", "precondition")]

    def test_reading_a_declared_argument_is_allowed(self) -> None:
        """arguments に password を宣言した操作の前提が password を読んでも、compose は断らない。"""
        compose_world(object_interactions=(_open_door(precondition=_password_is("ひらけ"), arguments=(_PASSWORD,)),))

    def test_reading_an_argument_outside_an_action_is_a_flaw(self) -> None:
        """出来事 echo の条件が password を読むと、出来事には引数が無いので DesignFlaw になる。"""
        flaws = flaws_of_composing(happenings=(_happening("echo", condition=_password_is("ひらけ")),))

        assert [flaw.location for flaw in flaws] == [DesignLocation("happening", "echo", "condition")]


class TestFlawsAreCollected:
    """compose が誤りを最初の 1 つで止めず、すべて集めて 1 つの例外で投げることを保証する。"""

    def test_two_flaws_are_raised_together(self) -> None:
        """引数の誤りの操作と、主語の誤りの出来事があると、2 つとも持つ WorldDesignFlawsException を投げる。"""
        flaws = flaws_of_composing(
            object_interactions=(_open_door(precondition=_password_is("ひらけ")),),
            happenings=(_happening("cave_in", effect=DamageEffect(who=Actor(), amount=Damage(1))),),
        )

        assert {flaw.location for flaw in flaws} == {
            DesignLocation("object_interaction", "door/open", "precondition"),
            DesignLocation("happening", "cave_in", "effect"),
        }


class TestWorldRulesAgainstTending:
    """猶予と介抱の組み合わせを compose が確かめることを保証する。"""

    def test_zero_grace_with_tending_is_a_flaw(self) -> None:
        """介抱がある (TendRule) のに猶予 (DeathRule.grace) が 0 だと、world_rules を場所とする DesignFlaw になる。"""
        rules = replace(
            world_rules_for_tests(), tend=TendRule(revive_hp_rate=Rate(0.6)), death=DeathRule(grace=Ticks(0))
        )

        flaws = flaws_of_composing(world_rules=rules, built_in_action_perceptions_=built_in_action_perceptions())

        assert [flaw.location for flaw in flaws] == [DesignLocation("world", "world", "world_rules")]

    def test_zero_grace_without_tending_is_allowed(self) -> None:
        """介抱が無い (NoTending) 世界なら、猶予が 0 でも compose は断らない。"""
        compose_world(world_rules=replace(world_rules_for_tests(), death=DeathRule(grace=Ticks(0))))


class TestTablesCoverTheWorld:
    """組み込みの行為の知覚の文が、世界で行える組み込みの行為をすべて持つかを compose が確かめることを保証する。"""

    def test_missing_built_in_perception_is_a_flaw(self) -> None:
        """BuiltInActionPerceptions に拾う (PICK_UP) の文が無いと DesignFlaw になる。"""
        flaws = flaws_of_composing(
            built_in_action_perceptions_=built_in_action_perceptions(without=(ActionKind.TEND, ActionKind.PICK_UP))
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("world", "world", "built_in_action_perceptions")]
        assert "PICK_UP" in flaws[0].reason

    def test_tend_perception_is_needed_only_when_tending_exists(self) -> None:
        """介抱がある世界で介抱 (TEND) の文が無いと DesignFlaw になり、介抱が無い世界では要らない。"""
        tending = replace(world_rules_for_tests(), tend=TendRule(revive_hp_rate=Rate(0.6)))

        flaws = flaws_of_composing(world_rules=tending)
        compose_world(built_in_action_perceptions_=built_in_action_perceptions(without=(ActionKind.TEND,)))

        assert [flaw.location.field for flaw in flaws] == ["built_in_action_perceptions"]


class TestVerbsDeclaredOncePerNoun:
    """区画の出入りと集団の決定の宣言が 1 つずつあり、名詞に付く動詞が重ならないことを compose が確かめることを保証する。"""

    def test_section_without_access_is_a_flaw(self) -> None:
        """区画 cage に出入りの宣言が無いと、section cage を場所とする DesignFlaw になる。"""
        cage = section("cage", "shaft")

        flaws = flaws_of_composing(nouns_=nouns(spots=(spot("shaft"),), sections=(cage,)))

        assert [flaw.location for flaw in flaws] == [DesignLocation("section", "cage", "section_access")]

    def test_section_with_two_accesses_is_a_flaw(self) -> None:
        """区画 cage に出入りの宣言が 2 つあると DesignFlaw になる。"""
        cage = section("cage", "shaft")

        flaws = flaws_of_composing(
            nouns_=nouns(spots=(spot("shaft"),), sections=(cage,)), section_accesses=(access_to(cage), access_to(cage))
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("section_access", "cage", "section")]

    def test_group_decision_without_rules_is_a_flaw(self) -> None:
        """集団の決定 exile に決まりの宣言が無いと、group_decision exile を場所とする DesignFlaw になる。"""
        flaws = flaws_of_composing(nouns_=nouns(group_decisions=(group_decision("exile"),)))

        assert [flaw.location for flaw in flaws] == [DesignLocation("group_decision", "exile", "group_decision_rules")]

    def test_group_decision_with_two_rules_is_a_flaw(self) -> None:
        """集団の決定 exile に決まりの宣言が 2 つあると DesignFlaw になる。"""
        exile = group_decision("exile")

        flaws = flaws_of_composing(
            nouns_=nouns(group_decisions=(exile,)),
            group_decision_rules=(everyone_votes_on(exile), everyone_votes_on(exile)),
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("group_decision_rules", "exile", "decision")]

    def test_same_interaction_twice_on_one_object_is_a_flaw(self) -> None:
        """扉 door に同じ名前の操作 open が 2 つあると DesignFlaw になる。"""
        flaws = flaws_of_composing(object_interactions=(_open_door(), _open_door()))

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_interaction", "door/open", "interaction")]

    def test_same_interaction_name_on_two_objects_is_allowed(self) -> None:
        """同じ名前の操作 open を、扉 door と箱 chest に 1 つずつ付けても compose は断らない。"""
        on_chest = replace(_open_door(), obj=obj("chest", "hall"))

        compose_world(object_interactions=(_open_door(), on_chest))

    def test_other_verbs_declared_twice_are_flaws(self) -> None:
        """品物の使い方・人への操作・通路の通り方・段階の出入りが同じ名詞に 2 つずつあると、それぞれ DesignFlaw になる。"""
        rope = replace(_open_door(), obj=obj("rope", "hall"))
        use = ItemUseDeclaration(item_spec=item_spec("rope"), effect=ChangesNothing())
        strike = _strike(AlwaysHolds())
        tunnel = passage("tunnel", ("hall", "shaft"))
        traversal = PassageTraversalDeclaration(passage=tunnel, condition=AlwaysHolds())
        dawn = world_stage("dawn")
        stage_effects = WorldStageEffectsDeclaration(
            stage=dawn, when_entered=ChangesNothing(), when_left=ChangesNothing()
        )

        flaws = flaws_of_composing(
            nouns_=nouns(spots=(spot("hall"), spot("shaft")), passages=(tunnel,), world_stages=(dawn,)),
            object_interactions=(rope,),
            item_uses=(use, use),
            person_interactions=(strike, strike),
            passage_traversals=(traversal, traversal),
            world_stage_effects=(stage_effects, stage_effects),
            initial_stage=dawn,
        )

        assert {flaw.location for flaw in flaws} == {
            DesignLocation("item_use", "rope", "item_spec"),
            DesignLocation("person_interaction", "strike", "interaction_id"),
            DesignLocation("passage_traversal", "tunnel", "passage"),
            DesignLocation("world_stage_effects", "dawn", "stage"),
        }

    def test_joint_action_on_undeclared_interaction_is_a_flaw(self) -> None:
        """二人で合わせる操作 two_valves が、宣言の無い操作 (valve の turn) を求めると DesignFlaw になる。"""
        joint = JointActionDeclaration(
            joint_id=JointActionId("two_valves"),
            required=((ObjectId("door"), InteractionId("open")), (ObjectId("valve"), InteractionId("turn"))),
            window=Ticks(3),
            distinct_people=True,
            on_complete=ChangesNothing(),
            on_timeout=ChangesNothing(),
            complete_notice=NoNotice(),
            timeout_notice=NoNotice(),
        )

        flaws = flaws_of_composing(object_interactions=(_open_door(),), joint_actions=(joint,))

        assert [flaw.location for flaw in flaws] == [DesignLocation("joint_action", "two_valves", "required[1]")]


def _composed_village() -> tuple[WorldDesign, dict[str, object]]:
    hall, shaft = spot("hall"), spot("shaft")
    tunnel = passage("tunnel", ("hall", "shaft"))
    cage = section("cage", "shaft")
    dawn, dusk = world_stage("dawn"), world_stage("dusk")
    exile = group_decision("exile")
    lamp = item_spec("lamp")
    open_door = _open_door()
    close_door = replace(open_door, interaction=replace(open_door.interaction, interaction_id=InteractionId("close")))
    light_lamp = ItemInteractionDeclaration(item_spec=lamp, interaction=open_door.interaction)
    use_lamp = ItemUseDeclaration(item_spec=lamp, effect=ChangesNothing())
    cage_access = access_to(cage)
    traversal = PassageTraversalDeclaration(passage=tunnel, condition=_password_is("ひらけ"))
    dawn_effects = WorldStageEffectsDeclaration(stage=dawn, when_entered=ChangesNothing(), when_left=ChangesNothing())
    exile_rules = everyone_votes_on(exile)
    strike = _strike(AlwaysHolds())
    cave_in = _happening("cave_in")
    found = DiscoverableDeclaration(
        discoverable_id=DiscoverableId("old_map"),
        spot_id=SpotId("shaft"),
        found_text=TextWithUnassignedPeople("古い地図を見つけた。"),
        condition=AlwaysHolds(),
        when_found=ChangesNothing(),
        finding=Finding.ONCE_IN_WORLD,
    )
    design = compose_world(
        nouns_=nouns(
            spots=(hall, shaft),
            passages=(tunnel,),
            sections=(cage,),
            world_stages=(dawn, dusk),
            group_decisions=(exile,),
        ),
        object_interactions=(open_door, close_door),
        item_interactions=(light_lamp,),
        item_uses=(use_lamp,),
        section_accesses=(cage_access,),
        passage_traversals=(replace(traversal, condition=AlwaysHolds()),),
        world_stage_effects=(dawn_effects,),
        group_decision_rules=(exile_rules,),
        happenings=(cave_in,),
        discoverables=(found,),
        person_interactions=(strike,),
        initial_stage=dawn,
    )
    return design, {
        "open_door": open_door,
        "close_door": close_door,
        "light_lamp": light_lamp,
        "use_lamp": use_lamp,
        "cage_access": cage_access,
        "dawn_effects": dawn_effects,
        "exile_rules": exile_rules,
        "strike": strike,
        "cave_in": cave_in,
        "found": found,
    }


class TestLookingUpVerbs:
    """動いている世界が、compose した WorldDesign から名詞に付く動詞と世界の宣言を ID で引けることを保証する。"""

    def test_interactions_on_an_object_are_looked_up_by_ids(self) -> None:
        """扉 door の操作は ID の組で 1 つずつ引け、まとめて引くと宣言した順に並ぶ。"""
        design, declared = _composed_village()
        open_door, close_door = declared["open_door"], declared["close_door"]
        assert isinstance(open_door, ObjectInteractionDeclaration)
        assert isinstance(close_door, ObjectInteractionDeclaration)

        assert design.interaction_on_object(ObjectId("door"), InteractionId("close")) == close_door.interaction
        assert design.interactions_on_object(ObjectId("door")) == (open_door.interaction, close_door.interaction)
        assert design.interactions_on_object(ObjectId("chest")) == ()

    def test_undeclared_interaction_raises(self) -> None:
        """宣言の無い操作 (door の kick、人への操作 hug) を引くと UndeclaredVerbException を投げる。"""
        design, _ = _composed_village()

        with pytest.raises(UndeclaredVerbException):
            design.interaction_on_object(ObjectId("door"), InteractionId("kick"))
        with pytest.raises(UndeclaredVerbException):
            design.person_interaction(InteractionId("hug"))

    def test_item_verbs_are_looked_up_by_item_spec(self) -> None:
        """品物 lamp の操作と使い方は品物の種類で引け、使い方の宣言が無い品物は NotUsable になる。"""
        design, declared = _composed_village()
        light_lamp = declared["light_lamp"]
        assert isinstance(light_lamp, ItemInteractionDeclaration)

        assert design.interaction_on_item(ItemSpecId("lamp"), InteractionId("open")) == light_lamp.interaction
        assert design.interactions_on_item(ItemSpecId("lamp")) == (light_lamp.interaction,)
        assert design.use_of_item(ItemSpecId("lamp")) == declared["use_lamp"]
        assert design.use_of_item(ItemSpecId("rope")) == NotUsable()

    def test_section_access_and_group_decision_rules_are_looked_up(self) -> None:
        """区画 cage の出入りと集団の決定 exile の決まりは、それぞれの ID で引ける。"""
        design, declared = _composed_village()

        assert design.section_access(SpotSectionId("cage")) == declared["cage_access"]
        assert design.group_decision_rules(GroupDecisionId("exile")) == declared["exile_rules"]
        assert design.person_interaction(InteractionId("strike")) == declared["strike"]

    def test_passage_without_traversal_declaration_is_always_traversable(self) -> None:
        """通り方の宣言が無い通路の条件は、誰がいつ試しても真で、主語も引数も要らない。"""
        design = compose_world()

        condition = design.passage_traversal(PassageId("ladder"))

        assert condition.holds(_NO_FACTS, _NO_TRIGGER)
        assert condition.requirements() == Requirements.nothing()

    def test_world_stage_without_effects_declaration_changes_nothing(self) -> None:
        """出入りの効果の宣言が無い段階 dusk は、入っても出ても何も要らない効果を返し、宣言した dawn はその宣言を返す。"""
        design, declared = _composed_village()

        dusk = design.world_stage_effects(WorldStageId("dusk"))

        assert design.world_stage_effects(WorldStageId("dawn")) == declared["dawn_effects"]
        assert dusk.stage == world_stage("dusk")
        assert dusk.when_entered.requirements() == Requirements.nothing()
        assert dusk.when_left.requirements() == Requirements.nothing()

    def test_world_wide_declarations_are_listed(self) -> None:
        """出来事は並びで、見つかる物は場所ごとに引け、見つかる物の無い場所は空になる。"""
        design, declared = _composed_village()

        assert design.happenings() == (declared["cave_in"],)
        assert design.reactions() == ()
        assert design.joint_actions() == ()
        assert design.discoverables_at(SpotId("shaft")) == (declared["found"],)
        assert design.discoverables_at(SpotId("hall")) == ()

    def test_introduction_is_kept(self) -> None:
        """compose に渡した導入と目的を introduction で引ける。"""
        assert compose_world().introduction == introduction()


def _flag(name: str, initially_raised: bool = False) -> FlagDeclaration:
    return FlagDeclaration(
        flag_id=FlagId(name), meaning=DescriptionText(f"{name} の意味"), initially_raised=initially_raised
    )


def _flag_is_raised(flag: FlagDeclaration) -> FlagIsRaisedCondition:
    return FlagIsRaisedCondition(flag=flag, failure_text=_REFUSED)


class TestRootFailureText:
    """理由が誰かに届く条件 (操作の前提、区画に入る条件、通路を通る条件) の根にだけ、compose が failure_text を求めることを保証する。"""

    def test_precondition_root_without_text_is_a_flaw(self) -> None:
        """扉 door の操作 open の前提の根が NoText だと、子に文があっても precondition を場所とする DesignFlaw になる。"""
        root = AllOfCondition(children=(_password_is("ひらけ"),), failure_text=NoText())

        flaws = flaws_of_composing(object_interactions=(_open_door(precondition=root, arguments=(_PASSWORD,)),))

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_interaction", "door/open", "precondition")]

    def test_section_entry_and_passage_traversal_roots_without_text_are_flaws(self) -> None:
        """区画 cage に入る条件と通路 tunnel を通る条件の根が NoText だと、それぞれの条件を場所とする DesignFlaw になる。"""
        silent = TickAtLeastCondition(tick=WorldTick(3), failure_text=NoText())
        cage = section("cage", "shaft")
        tunnel = passage("tunnel", ("hall", "shaft"))

        flaws = flaws_of_composing(
            nouns_=nouns(spots=(spot("hall"), spot("shaft")), passages=(tunnel,), sections=(cage,)),
            section_accesses=(replace(access_to(cage), entry_condition=silent),),
            passage_traversals=(PassageTraversalDeclaration(passage=tunnel, condition=silent),),
        )

        assert [flaw.location for flaw in flaws] == [
            DesignLocation("section_access", "cage", "entry_condition"),
            DesignLocation("passage_traversal", "tunnel", "condition"),
        ]

    def test_roots_whose_reason_reaches_no_one_need_no_text(self) -> None:
        """出来事・反応・見つかる物・終わりの条件は、偽になっても理由が誰にも届かないので、根が NoText でも compose は断らない。"""
        silent = TickAtLeastCondition(tick=WorldTick(3), failure_text=NoText())

        compose_world(
            happenings=(_happening("cave_in", condition=silent),),
            reactions=(
                ReactionDeclaration(
                    reaction_id=ReactionId("panic"),
                    condition=silent,
                    when_becomes_true=ChangesNothing(),
                    when_becomes_false=ChangesNothing(),
                ),
            ),
            discoverables=(
                DiscoverableDeclaration(
                    discoverable_id=DiscoverableId("old_map"),
                    spot_id=SpotId("shaft"),
                    found_text=TextWithUnassignedPeople("古い地図を見つけた。"),
                    condition=silent,
                    when_found=ChangesNothing(),
                    finding=Finding.ONCE_IN_WORLD,
                ),
            ),
            ending=EndingDeclaration(ends_when=silent),
        )


class TestUndeclaredWorldTime:
    """段階・昼夜・天候を宣言していない世界で、それを見る条件を compose が止めることを保証する。"""

    def test_time_of_day_without_day_night_is_a_flaw(self) -> None:
        """昼夜を宣言していない世界で、出来事 cave_in の条件が TimeOfDayIs(夜) を見ると、昼夜が無いことを理由とする DesignFlaw になる。"""
        night = TimeOfDayIsCondition(phase=DayPhaseName("night"), failure_text=_REFUSED)

        flaws = flaws_of_composing(happenings=(_happening("cave_in", condition=night),))

        assert [flaw.location for flaw in flaws] == [DesignLocation("happening", "cave_in", "condition")]
        assert "declares no day and night" in flaws[0].reason

    def test_undeclared_day_phase_is_a_flaw(self) -> None:
        """昼夜に 朝 と 夜 だけを宣言した世界で、夕方 を見る条件は DesignFlaw になり、夜 を見る条件は通る。"""
        dusk = TimeOfDayIsCondition(phase=DayPhaseName("dusk"), failure_text=_REFUSED)
        night = TimeOfDayIsCondition(phase=DayPhaseName("night"), failure_text=_REFUSED)

        flaws = flaws_of_composing(
            happenings=(_happening("dusk_bell", condition=dusk), _happening("night_bell", condition=night)),
            day_night=_DAY_NIGHT,
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("happening", "dusk_bell", "condition")]
        assert "dusk" in flaws[0].reason

    def test_world_stage_without_stages_is_a_flaw(self) -> None:
        """段階を宣言していない世界で、操作の前提が WorldStageIs を見ると DesignFlaw になる。"""
        dawn = world_stage("dawn")
        precondition = WorldStageIsCondition(stage=dawn, failure_text=_REFUSED)

        flaws = flaws_of_composing(object_interactions=(_open_door(precondition=precondition),))

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_interaction", "door/open", "precondition")]

    def test_world_stage_with_stages_is_allowed(self) -> None:
        """段階を宣言した世界なら、WorldStageIs を見る前提は通る。"""
        dawn = world_stage("dawn")

        compose_world(
            nouns_=nouns(world_stages=(dawn,)),
            object_interactions=(_open_door(precondition=WorldStageIsCondition(stage=dawn, failure_text=_REFUSED)),),
            initial_stage=dawn,
        )

    def test_weather_without_weather_is_a_flaw(self) -> None:
        """天候を宣言していない世界で WeatherIs を見ると DesignFlaw になり、宣言した世界では通る。"""
        fog = WeatherIsCondition(weather=WeatherType.FOG, failure_text=_REFUSED)

        flaws = flaws_of_composing(happenings=(_happening("mist", condition=fog),))
        compose_world(happenings=(_happening("mist", condition=fog),), weather=_WEATHER)

        assert [flaw.location for flaw in flaws] == [DesignLocation("happening", "mist", "condition")]


class TestFlagsRaisedAndRead:
    """旗を立てる効果と見る条件を compose が照らし合わせることを保証する。"""

    def test_flag_read_but_never_raised_is_a_flaw(self) -> None:
        """initially_raised でもなく、どの効果も立てない旗 beast_awake を出来事の条件が見ると DesignFlaw になる。"""
        beast_awake = _flag("beast_awake")

        flaws = flaws_of_composing(
            nouns_=nouns(flags=(beast_awake,)),
            happenings=(_happening("attack", condition=_flag_is_raised(beast_awake)),),
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("happening", "attack", "condition")]
        assert "beast_awake" in flaws[0].reason

    def test_flag_raised_by_some_effect_may_be_read(self) -> None:
        """出来事 rumble の効果が立てる旗を、別の出来事 attack の条件が見ても compose は断らず、警告も出さない。"""
        beast_awake = _flag("beast_awake")

        design = compose_world(
            nouns_=nouns(flags=(beast_awake,)),
            happenings=(
                _happening("rumble", effect=RaiseFlagEffect(flag=beast_awake)),
                _happening("attack", condition=_flag_is_raised(beast_awake)),
            ),
        )

        assert design.warnings() == ()

    def test_initially_raised_flag_may_be_read(self) -> None:
        """initially_raised の旗は、どの効果も立てなくても条件が見てよい。"""
        lamp_lit = _flag("lamp_lit", initially_raised=True)

        compose_world(
            nouns_=nouns(flags=(lamp_lit,)), happenings=(_happening("dark", condition=_flag_is_raised(lamp_lit)),)
        )

    def test_flag_raised_but_never_read_is_a_warning(self) -> None:
        """出来事が立てるだけで、どの条件も見ない旗 bell_rang は、flag bell_rang を場所とする DesignWarning になる。"""
        bell_rang = _flag("bell_rang")

        design = compose_world(
            nouns_=nouns(flags=(bell_rang,)), happenings=(_happening("bell", effect=RaiseFlagEffect(flag=bell_rang)),)
        )

        assert [warning.location for warning in design.warnings()] == [DesignLocation("flag", "bell_rang", "flag_id")]

    def test_flag_neither_raised_nor_read_is_not_warned(self) -> None:
        """どの効果も立てず、どの条件も見ない旗 unused は、立てるだけの旗ではないので警告しない。"""
        design = compose_world(nouns_=nouns(flags=(_flag("unused"),)))

        assert design.warnings() == ()


class TestHappeningsRead:
    """出来事を読む条件が、宣言された出来事の ID を指しているかを compose が照らし合わせることを保証する。"""

    def test_reading_undeclared_happening_is_a_flaw(self) -> None:
        """宣言の無い出来事 landslide が起きたかを見る出来事 rescue は、その条件の場所を付けた DesignFlaw になる。"""
        flaws = flaws_of_composing(
            happenings=(
                _happening(
                    "rescue",
                    condition=HappeningHasFiredCondition(happening=HappeningId("landslide"), failure_text=NoText()),
                ),
            ),
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("happening", "rescue", "condition")]
        assert "landslide" in flaws[0].reason

    def test_happening_may_read_itself(self) -> None:
        """最後に襲ってから 5 tick 経ったらまた襲う出来事 beast_attacks のように、自分を読む出来事も作れる。"""
        attacks = HappeningId("beast_attacks")

        design = compose_world(
            happenings=(
                _happening(
                    "beast_attacks",
                    condition=TicksSinceHappeningAtLeastCondition(
                        happening=attacks, ticks=Ticks(5), failure_text=NoText()
                    ),
                ),
            ),
        )

        assert design.happenings()[0].happening_id == attacks


class TestGroupDecisionsClosed:
    """締める出来事の無い集団の決定を compose が警告することを保証する。"""

    def test_decision_never_closed_is_a_warning(self) -> None:
        """集団の決定 exile を締める CloseGroupDecisionEffect がどこにも無いと、DesignWarning になる。"""
        exile = group_decision("exile")

        design = compose_world(nouns_=nouns(group_decisions=(exile,)), group_decision_rules=(everyone_votes_on(exile),))

        assert [warning.location for warning in design.warnings()] == [
            DesignLocation("group_decision", "exile", "decision_id")
        ]

    def test_decision_closed_by_a_happening_is_not_warned(self) -> None:
        """出来事 dusk が CloseGroupDecisionEffect(exile) を持てば、警告は出ない。"""
        exile = group_decision("exile")

        design = compose_world(
            nouns_=nouns(group_decisions=(exile,)),
            group_decision_rules=(everyone_votes_on(exile),),
            happenings=(_happening("dusk", effect=CloseGroupDecisionEffect(decision=exile)),),
        )

        assert design.warnings() == ()


class TestHiddenMembershipInPreconditions:
    """行う人に知りえない所属を見る前提を compose が警告することを保証する。"""

    def test_precondition_on_others_hidden_membership_is_a_warning(self) -> None:
        """人への操作 strike の前提が相手の SELF_ONLY の所属 (狼) を見ると precondition の DesignWarning になり、行う人のいない出来事 howl が同じ所属を見ても警告しない。"""
        is_wolf = IsMemberCondition(who=Target(), group=_WOLVES, failure_text=_REFUSED)

        design = compose_world(
            nouns_=nouns(groupings=(_ROLE,), groups=(_WOLVES,)),
            person_interactions=(_strike(is_wolf),),
            happenings=(
                _happening("howl", condition=replace(is_wolf, who=NamedPerson(character=character("bob", "hall")))),
            ),
        )

        assert [warning.location for warning in design.warnings()] == [
            DesignLocation("person_interaction", "strike", "precondition")
        ]

    def test_section_entry_and_passage_traversal_are_preconditions_too(self) -> None:
        """区画 cage に入る条件と通路 tunnel の通り方の条件が、名指しした bob の SELF_ONLY の所属を見ると、どちらも DesignWarning になる。"""
        bob_is_wolf = IsMemberCondition(
            who=NamedPerson(character=character("bob", "hall")), group=_WOLVES, failure_text=_REFUSED
        )
        cage = section("cage", "shaft")
        tunnel = passage("tunnel", ("hall", "shaft"))

        design = compose_world(
            nouns_=nouns(
                spots=(spot("hall"), spot("shaft")),
                passages=(tunnel,),
                sections=(cage,),
                groupings=(_ROLE,),
                groups=(_WOLVES,),
            ),
            section_accesses=(replace(access_to(cage), entry_condition=bob_is_wolf),),
            passage_traversals=(PassageTraversalDeclaration(passage=tunnel, condition=bob_is_wolf),),
        )

        assert [warning.location for warning in design.warnings()] == [
            DesignLocation("section_access", "cage", "entry_condition"),
            DesignLocation("passage_traversal", "tunnel", "condition"),
        ]


def _mine(*passages: PassageDeclaration) -> WorldDesign:
    names = sorted({end.value for declared in passages for end in declared.ends})
    return compose_world(nouns_=nouns(spots=tuple(spot(name) for name in names), passages=passages))


def _ids(*names: str) -> frozenset[PassageId]:
    return frozenset(PassageId(name) for name in names)


class TestRoute:
    """route が、通れる通路だけをたどり、かかる tick・通路の数・宣言の並びの順で道を 1 つに決めることを保証する。"""

    def test_route_follows_passable_passages_to_the_destination(self) -> None:
        """村 → 坑口 → 坑道 とつながる通路をたどって、村から坑道までの道を返す。"""
        path, shaft = passage("path", ("village", "mine_mouth")), passage("shaft", ("mine_mouth", "gallery"))
        design = _mine(path, shaft)

        route = design.route(SpotId("village"), SpotId("gallery"), passable=_ids("path", "shaft"))

        assert route == Route(start=SpotId("village"), passages=(path, shaft))

    def test_unreachable_destination_is_no_route(self) -> None:
        """坑道へ続く通路が通れない (passable に無い) と NoRoute を返す。"""
        design = _mine(passage("path", ("village", "mine_mouth")), passage("shaft", ("mine_mouth", "gallery")))

        assert design.route(SpotId("village"), SpotId("gallery"), passable=_ids("path")) == NoRoute()

    def test_one_way_passage_is_walked_only_forward(self) -> None:
        """片道の滑り台 (坑口 → 坑道) は前の端からしか通れず、坑道から坑口へは NoRoute になる。"""
        chute = passage("chute", ("mine_mouth", "gallery"), two_way=False)
        design = _mine(chute)

        assert design.route(SpotId("mine_mouth"), SpotId("gallery"), passable=_ids("chute")) == Route(
            start=SpotId("mine_mouth"), passages=(chute,)
        )
        assert design.route(SpotId("gallery"), SpotId("mine_mouth"), passable=_ids("chute")) == NoRoute()

    def test_two_way_passage_is_walked_backward(self) -> None:
        """両方向の通路は後ろの端からも通れる。"""
        path = passage("path", ("village", "mine_mouth"))

        assert _mine(path).route(SpotId("mine_mouth"), SpotId("village"), passable=_ids("path")) == Route(
            start=SpotId("mine_mouth"), passages=(path,)
        )

    def test_fewest_ticks_wins_over_fewest_passages(self) -> None:
        """近道 (5 tick の 1 本) より、回り道 (1 tick の 2 本で計 2 tick) を選ぶ。"""
        shortcut = passage("shortcut", ("village", "gallery"), travel_ticks=5)
        first, second = passage("first", ("village", "hut"), travel_ticks=1), passage("second", ("hut", "gallery"))
        design = _mine(shortcut, first, second)

        route = design.route(SpotId("village"), SpotId("gallery"), passable=_ids("shortcut", "first", "second"))

        assert route == Route(start=SpotId("village"), passages=(first, second))

    def test_closed_shortcut_falls_back_to_the_open_detour(self) -> None:
        """2 tick の近道が閉じていて passable に無ければ、5 tick の開いた回り道を選ぶ。"""
        shortcut = passage("shortcut", ("village", "gallery"), travel_ticks=2)
        detour = passage("detour", ("village", "gallery"), travel_ticks=5)
        design = _mine(shortcut, detour)

        assert design.route(SpotId("village"), SpotId("gallery"), passable=_ids("detour")) == Route(
            start=SpotId("village"), passages=(detour,)
        )

    def test_same_ticks_prefers_fewer_passages(self) -> None:
        """どちらも 2 tick なら、通路 1 本の道を 2 本の道より選ぶ。"""
        first, second = passage("first", ("village", "hut")), passage("second", ("hut", "gallery"))
        direct = passage("direct", ("village", "gallery"), travel_ticks=2)
        design = _mine(first, second, direct)

        route = design.route(SpotId("village"), SpotId("gallery"), passable=_ids("first", "second", "direct"))

        assert route == Route(start=SpotId("village"), passages=(direct,))

    def test_full_tie_prefers_the_passage_declared_first(self) -> None:
        """かかる tick も通路の数も同じ 2 本の道なら、宣言の並びが先の通路 (east) を通る道を選ぶ。"""
        east, west = passage("east", ("village", "gallery")), passage("west", ("village", "gallery"))
        design = _mine(east, west)

        assert design.route(SpotId("village"), SpotId("gallery"), passable=_ids("east", "west")) == Route(
            start=SpotId("village"), passages=(east,)
        )
        assert _mine(west, east).route(SpotId("village"), SpotId("gallery"), passable=_ids("east", "west")) == Route(
            start=SpotId("village"), passages=(west,)
        )

    def test_route_to_where_one_already_is_is_no_route(self) -> None:
        """出発地と目的地が同じなら、通路を 1 本も通らないので NoRoute を返す。"""
        design = _mine(passage("path", ("village", "mine_mouth")))

        assert design.route(SpotId("village"), SpotId("village"), passable=_ids("path")) == NoRoute()


class TestInitialWorld:
    """initial_world が、宣言どうしを組み合わせないと作れない始まりの世界を返すことを保証する。"""

    def test_starting_people_resolve_their_declarations(self) -> None:
        """登場人物 alice の居場所・持ち物・手に持つ物・所属・知り合いを、名前ではなく宣言で返す。"""
        hall = spot("hall")
        lamp = item_spec("lamp")
        role = GroupingDeclaration(
            grouping_id=GroupingId("role"),
            name=DisplayName("役"),
            visibility=MembershipVisibility.SELF_ONLY,
            changes=False,
        )
        miners = GroupDeclaration(
            group_id=GroupId("miners"),
            grouping=role,
            name=DisplayName("鉱夫"),
            members_know_each_other=True,
            shared_description=NoSharedDescription(),
        )
        alice = replace(
            character("alice", "hall"),
            initial_items=(ItemSpecId("lamp"), ItemSpecId("lamp")),
            initial_held=(ItemSpecId("lamp"),),
            initial_groups=(GroupId("miners"),),
            knows_at_start=(PersonId("bob"),),
        )
        bob = character("bob", "hall")

        initial = compose_world(
            nouns_=nouns(
                spots=(hall,), item_specs=(lamp,), groupings=(role,), groups=(miners,), characters=(alice, bob)
            )
        ).initial_world()

        assert initial.people == (
            StartingPerson(
                person=PersonId("alice"),
                spawn_spot=hall,
                items=(lamp, lamp),
                held=(lamp,),
                groups=(miners,),
                knows=(PersonId("bob"),),
                hp=HitPoints(100, 100),
                pack_capacity=Capacity(20),
            ),
            StartingPerson(
                person=PersonId("bob"),
                spawn_spot=hall,
                items=(),
                held=(),
                groups=(),
                knows=(),
                hp=HitPoints(100, 100),
                pack_capacity=Capacity(20),
            ),
        )

    def test_people_without_their_own_values_start_with_the_world_defaults(self) -> None:
        """体力と荷の上限を書かない登場人物は、WorldRules の既定 (体力 80、荷 12) で始まる。"""
        rules = replace(world_rules_for_tests(), person_max_hp=HitPoints(80, 80), pack_capacity=Capacity(12))

        (person,) = (
            compose_world(
                nouns_=nouns(spots=(spot("hall"),), characters=(character("alice", "hall"),)), world_rules=rules
            )
            .initial_world()
            .people
        )

        assert (person.hp, person.pack_capacity) == (HitPoints(80, 80), Capacity(12))

    def test_person_with_own_values_overrides_the_world_defaults(self) -> None:
        """屈強な鉱夫 goro が体力 150 と荷 30 を書けば、世界の既定ではなくその値で始まる。"""
        goro = replace(character("goro", "hall"), max_hp=HitPoints(150, 150), pack_capacity=Capacity(30))

        (person,) = compose_world(nouns_=nouns(spots=(spot("hall"),), characters=(goro,))).initial_world().people

        assert (person.hp, person.pack_capacity) == (HitPoints(150, 150), Capacity(30))

    def test_only_initially_raised_flags_start_raised(self) -> None:
        """initially_raised の旗 lamp_lit だけが最初に立ち、beast_awake は立っていない。"""
        lamp_lit, beast_awake = _flag("lamp_lit", initially_raised=True), _flag("beast_awake")

        initial = compose_world(nouns_=nouns(flags=(lamp_lit, beast_awake))).initial_world()

        assert initial.raised_flags == frozenset({lamp_lit})

    def test_stage_and_weather_start_as_declared(self) -> None:
        """最初の段階は compose に渡した段階、天候は宣言の initial になり、どちらも無い世界では NoWorldStages と NoWeather になる。"""
        dawn = world_stage("dawn")

        declared = compose_world(
            nouns_=nouns(world_stages=(dawn,)), initial_stage=dawn, weather=_WEATHER
        ).initial_world()
        undeclared = compose_world().initial_world()

        assert (declared.stage, declared.weather) == (dawn, WeatherState(WeatherType.CLEAR))
        assert (undeclared.stage, undeclared.weather) == (NoWorldStages(), NoWeather())


class TestDeclarationsKeptForTheRunningWorld:
    """compose に渡した世界全体の宣言を、動いている世界が引けることを保証する。"""

    def test_world_wide_declarations_are_returned_as_given(self) -> None:
        """断りの文の表・組み込みの行為の知覚の文・天候・昼夜は、compose に渡したものをそのまま返す。"""
        texts = refusal_texts()
        perceptions = built_in_action_perceptions(without=(ActionKind.TEND,))

        design = compose_world(
            refusal_texts_=texts, built_in_action_perceptions_=perceptions, weather=_WEATHER, day_night=_DAY_NIGHT
        )

        assert design.refusal_texts is texts
        assert design.built_in_action_perceptions is perceptions
        assert design.weather == _WEATHER
        assert design.day_night == _DAY_NIGHT


_READS_FOG = WeatherIsCondition(weather=WeatherType.FOG, failure_text=_REFUSED)
_EFFECT_READING_FOG = ConditionalEffect(condition=_READS_FOG, then=NoEffect(), otherwise=NoEffect())
_AUDIENCE_READING_FOG = AnnouncementTo(audience=PeopleSelection(where=_READS_FOG), text=_REFUSED, salience=Notable())


def _looking(name: str, *whens: Condition) -> ObjectLooksDeclaration:
    return ObjectLooksDeclaration(
        object_id=ObjectId(name),
        looks=tuple(ObjectLook(when=when, text=DescriptionText(f"見え方 {index}")) for index, when in enumerate(whens)),
    )


def _every_placement() -> list[tuple[str, dict[str, object], DesignLocation]]:
    exile = group_decision("exile")
    cage = section("cage", "shaft")
    tunnel = passage("tunnel", ("hall", "shaft"))
    dawn = world_stage("dawn")
    place_nouns = nouns(
        spots=(spot("hall"), spot("shaft")),
        passages=(tunnel,),
        sections=(cage,),
        world_stages=(dawn,),
        group_decisions=(exile,),
    )
    rope_use = ItemUseDeclaration(item_spec=item_spec("rope"), effect=_EFFECT_READING_FOG)
    on_rope = ItemInteractionDeclaration(item_spec=item_spec("rope"), interaction=_open_door().interaction)
    reaction = ReactionDeclaration(
        reaction_id=ReactionId("panic"),
        condition=AlwaysHolds(),
        when_becomes_true=ChangesNothing(),
        when_becomes_false=ChangesNothing(),
    )
    joint = JointActionDeclaration(
        joint_id=JointActionId("two_doors"),
        required=((ObjectId("door"), InteractionId("open")),),
        window=Ticks(3),
        distinct_people=True,
        on_complete=ChangesNothing(),
        on_timeout=ChangesNothing(),
        complete_notice=NoNotice(),
        timeout_notice=NoNotice(),
    )
    found = DiscoverableDeclaration(
        discoverable_id=DiscoverableId("old_map"),
        spot_id=SpotId("shaft"),
        found_text=TextWithUnassignedPeople("古い地図を見つけた。"),
        condition=AlwaysHolds(),
        when_found=ChangesNothing(),
        finding=Finding.ONCE_IN_WORLD,
    )
    rules = everyone_votes_on(exile)
    stage_effects = WorldStageEffectsDeclaration(stage=dawn, when_entered=ChangesNothing(), when_left=ChangesNothing())
    base: dict[str, object] = {
        "nouns_": place_nouns,
        "section_accesses": (access_to(cage),),
        "group_decision_rules": (rules,),
        "initial_stage": dawn,
    }
    door = _open_door()
    loud_perceptions = built_in_action_perceptions(without=(ActionKind.TEND,))
    loud_perceptions = BuiltInActionPerceptions(
        by_kind={
            **loud_perceptions.by_kind,
            ActionKind.PICK_UP: replace(
                loud_perceptions.by_kind[ActionKind.PICK_UP], announcement=_AUDIENCE_READING_FOG
            ),
        }
    )
    cases: list[tuple[str, dict[str, object], DesignLocation]] = [
        (
            "object_interaction",
            {
                "object_interactions": (
                    replace(door, interaction=replace(door.interaction, effect=_EFFECT_READING_FOG)),
                )
            },
            DesignLocation("object_interaction", "door/open", "effect"),
        ),
        (
            "item_interaction",
            {
                "item_interactions": (
                    replace(on_rope, interaction=replace(on_rope.interaction, precondition=_READS_FOG)),
                )
            },
            DesignLocation("item_interaction", "rope/open", "precondition"),
        ),
        ("item_use", {"item_uses": (rope_use,)}, DesignLocation("item_use", "rope", "effect")),
        (
            "section_access",
            {"section_accesses": (replace(access_to(cage), entry_condition=_READS_FOG),)},
            DesignLocation("section_access", "cage", "entry_condition"),
        ),
        (
            "passage_traversal",
            {"passage_traversals": (PassageTraversalDeclaration(passage=tunnel, condition=_READS_FOG),)},
            DesignLocation("passage_traversal", "tunnel", "condition"),
        ),
        (
            "world_stage_effects",
            {"world_stage_effects": (replace(stage_effects, when_left=_EFFECT_READING_FOG),)},
            DesignLocation("world_stage_effects", "dawn", "when_left"),
        ),
        (
            "group_decision_rules.voters",
            {"group_decision_rules": (replace(rules, voters=PeopleSelection(where=_READS_FOG)),)},
            DesignLocation("group_decision_rules", "exile", "voters"),
        ),
        (
            "group_decision_rules.choices",
            {"group_decision_rules": (replace(rules, choices=PeopleSelection(where=_READS_FOG)),)},
            DesignLocation("group_decision_rules", "exile", "choices"),
        ),
        (
            "group_decision_rules.when_decided",
            {"group_decision_rules": (replace(rules, when_decided=_EFFECT_READING_FOG),)},
            DesignLocation("group_decision_rules", "exile", "when_decided"),
        ),
        (
            "happening",
            {"happenings": (replace(_happening("mist"), notice=_AUDIENCE_READING_FOG),)},
            DesignLocation("happening", "mist", "notice"),
        ),
        (
            "reaction",
            {"reactions": (replace(reaction, when_becomes_false=_EFFECT_READING_FOG),)},
            DesignLocation("reaction", "panic", "when_becomes_false"),
        ),
        (
            "discoverable",
            {"discoverables": (replace(found, condition=_READS_FOG),)},
            DesignLocation("discoverable", "old_map", "condition"),
        ),
        (
            "joint_action",
            {"object_interactions": (door,), "joint_actions": (replace(joint, on_timeout=_EFFECT_READING_FOG),)},
            DesignLocation("joint_action", "two_doors", "on_timeout"),
        ),
        (
            "person_interaction",
            {"person_interactions": (_strike(_READS_FOG),)},
            DesignLocation("person_interaction", "strike", "precondition"),
        ),
        (
            "ending",
            {"ending": EndingDeclaration(ends_when=_READS_FOG)},
            DesignLocation("ending", "ending", "ends_when"),
        ),
        (
            "object_look",
            {
                "nouns_": nouns(
                    spots=(spot("hall"), spot("shaft")),
                    passages=(tunnel,),
                    sections=(cage,),
                    world_stages=(dawn,),
                    group_decisions=(exile,),
                    objects=(obj("lamp", "hall"),),
                ),
                "object_looks": (_looking("lamp", _READS_FOG),),
            },
            DesignLocation("object_looks", "lamp", "looks[0]"),
        ),
        (
            "built_in_action_perceptions",
            {"built_in_action_perceptions_": loud_perceptions},
            DesignLocation("built_in_action_perceptions", "PICK_UP", "announcement"),
        ),
    ]
    return [(name, {**base, **declarations}, location) for name, declarations, location in cases]


class TestEveryPlacementIsReviewed:
    """compose が、すべての種類の宣言の条件と効果を照らし合わせにかけることを保証する。"""

    @pytest.mark.parametrize(
        ("declarations", "location"),
        [(declarations, location) for _, declarations, location in _every_placement()],
        ids=[name for name, _, _ in _every_placement()],
    )
    def test_reading_undeclared_weather_is_found_in_every_placement(
        self, declarations: dict[str, object], location: DesignLocation
    ) -> None:
        """天候を宣言していない世界で、その種類の宣言のどこか 1 か所だけが霧 (WeatherIs) を読むと、その場所の DesignFlaw が 1 つだけ出る。"""
        flaws = flaws_of_composing(**declarations)

        assert [flaw.location for flaw in flaws] == [location]


class TestObjectLookConditions:
    """物の見え方の条件が世界の状態だけで決まるかを compose が確かめることを保証する。"""

    def test_look_reading_the_actor_is_a_flaw(self) -> None:
        """水門の 2 つ目の見え方が行う人 (actor) が倒れているかを読むと、looks[1] の DesignFlaw になる。"""
        gate_open = FlagDeclaration(
            flag_id=FlagId("gate_open"), meaning=DescriptionText("水門が開いている"), initially_raised=True
        )
        gate_looks = _looking(
            "gate",
            FlagIsRaisedCondition(flag=gate_open, failure_text=NoText()),
            IsDownCondition(who=Actor(), failure_text=NoText()),
        )

        flaws = flaws_of_composing(
            nouns_=nouns(flags=(gate_open,), spots=(spot("hall"),), objects=(obj("gate", "hall"),)),
            object_looks=(gate_looks,),
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_looks", "gate", "looks[1]")]

    def test_look_using_chance_is_a_flaw(self) -> None:
        """見え方が偶然 (chance) を読むと、見渡すたびに変わる見え方になるので looks[0] の DesignFlaw になる。"""
        gate_looks = _looking("gate", ChanceCondition(probability=Probability(0.5), failure_text=NoText()))

        flaws = flaws_of_composing(
            nouns_=nouns(spots=(spot("hall"),), objects=(obj("gate", "hall"),)), object_looks=(gate_looks,)
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_looks", "gate", "looks[0]")]

    def test_look_reading_a_named_person_is_allowed(self) -> None:
        """詰所の机の見え方が、名指しした源三が倒れているかを読むのは、見る人で変わらないので通る (源三の帽子が置きっぱなしになっている)。"""
        genzo = character("genzo", "hall")
        desk_looks = _looking("desk", IsDownCondition(who=NamedPerson(character=genzo), failure_text=NoText()))

        design = compose_world(
            nouns_=nouns(spots=(spot("hall"),), characters=(genzo,), objects=(obj("desk", "hall"),)),
            object_looks=(desk_looks,),
        )

        assert design.looks_of(ObjectId("desk")) == desk_looks


class TestObjectLooksDeclared:
    """物の見え方の宣言を、物ごとに 1 つ、宣言にある物に対してだけ持てることを compose が確かめることを保証する。"""

    def test_object_without_declared_looks_has_empty_looks(self) -> None:
        """見え方を宣言していない物を looks_of で引くと、見え方が空の宣言が返る。"""
        design = compose_world(nouns_=nouns(spots=(spot("hall"),), objects=(obj("desk", "hall"),)))

        assert design.looks_of(ObjectId("desk")) == ObjectLooksDeclaration(object_id=ObjectId("desk"), looks=())

    def test_looks_of_an_undeclared_object_is_a_flaw(self) -> None:
        """宣言に無い物 ghost_lamp の見え方を宣言すると、object_id の DesignFlaw になる。"""
        flaws = flaws_of_composing(object_looks=(_looking("ghost_lamp"),))

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_looks", "ghost_lamp", "object_id")]

    def test_two_looks_declarations_for_one_object_is_a_flaw(self) -> None:
        """同じ机に見え方の宣言を 2 つ置くと、どちらを使うか決まらないので DesignFlaw になる。"""
        flaws = flaws_of_composing(
            nouns_=nouns(spots=(spot("hall"),), objects=(obj("desk", "hall"),)),
            object_looks=(_looking("desk"), _looking("desk")),
        )

        assert [flaw.location for flaw in flaws] == [DesignLocation("object_looks", "desk", "object_id")]


class TestWorldWideIdsAreUnique:
    """出来事・反応・見つかる物・二人で合わせる操作の ID が重ならないことを compose が確かめることを保証する。"""

    def test_world_wide_declarations_with_the_same_id_are_flaws(self) -> None:
        """同じ ID の出来事・反応・見つかる物・二人で合わせる操作が 2 つずつあると、それぞれ ID の欄を場所とする DesignFlaw になる。"""
        reaction = ReactionDeclaration(
            reaction_id=ReactionId("panic"),
            condition=AlwaysHolds(),
            when_becomes_true=ChangesNothing(),
            when_becomes_false=ChangesNothing(),
        )
        found = DiscoverableDeclaration(
            discoverable_id=DiscoverableId("old_map"),
            spot_id=SpotId("shaft"),
            found_text=TextWithUnassignedPeople("古い地図を見つけた。"),
            condition=AlwaysHolds(),
            when_found=ChangesNothing(),
            finding=Finding.ONCE_IN_WORLD,
        )
        joint = JointActionDeclaration(
            joint_id=JointActionId("two_doors"),
            required=((ObjectId("door"), InteractionId("open")),),
            window=Ticks(3),
            distinct_people=True,
            on_complete=ChangesNothing(),
            on_timeout=ChangesNothing(),
            complete_notice=NoNotice(),
            timeout_notice=NoNotice(),
        )

        flaws = flaws_of_composing(
            object_interactions=(_open_door(),),
            happenings=(_happening("cave_in"), _happening("cave_in")),
            reactions=(reaction, reaction),
            discoverables=(found, replace(found, spot_id=SpotId("hall"))),
            joint_actions=(joint, joint),
        )

        assert {flaw.location for flaw in flaws} == {
            DesignLocation("happening", "cave_in", "happening_id"),
            DesignLocation("reaction", "panic", "reaction_id"),
            DesignLocation("discoverable", "old_map", "discoverable_id"),
            DesignLocation("joint_action", "two_doors", "joint_id"),
        }

    def test_distinct_ids_are_allowed(self) -> None:
        """ID の違う出来事 2 つなら compose は断らない。"""
        compose_world(happenings=(_happening("cave_in"), _happening("flood")))
