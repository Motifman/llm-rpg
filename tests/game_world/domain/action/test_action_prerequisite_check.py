from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt, LivingOrDeparted
from ai_rpg_world.game_world.domain.action.action_prerequisite_check import ActionPrerequisiteCheck
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    GroundItemPickupAttempt,
    GroupDecisionBallotAttempt,
    ListeningAttempt,
    SpeechAttempt,
    SpotSearchAttempt,
    TendAttempt,
    TravelAttempt,
)
from ai_rpg_world.game_world.domain.action.common_rule_refusal import (
    ActorCannotAct,
    Busy,
    CommonRuleRefusalKind,
    NotAllowedInThisStage,
    NotTogether,
    OutOfReach,
    TooTired,
)
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
)
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, SpeechContent
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import DeclaredOutcome, PersonVitals, WorldHappening
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel, FatigueLevelName, FatigueRule
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DescriptionText,
    DisplayName,
    FatigueAmount,
    GroupDecisionId,
    HitPoints,
    InteractionId,
    OutcomeId,
    PersonId,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, PersonBody
from ai_rpg_world.game_world.domain.world_progress import WorldStage
from ai_rpg_world.game_world.domain.world_progress.group_decision import VoteFor
from tests.game_world.domain.whereabouts._builders import WORLD, section, spot, thing
from tests.game_world.support.declarations_for_tests import InteractionForTests
from tests.game_world.support.world_in_memory import WorldInMemory
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

ALICE = PersonId("alice")
BOB = PersonId("bob")
LANDING = spot("lift_landing")
SHORE = spot("shore")
LEVER = thing("lever", "lift_landing")
CAGE = section("lift_cage", "lift_landing", reachable=("lever",))
PULL = InteractionForTests(InteractionId("pull"))
EXILE = GroupDecisionDeclaration(
    decision_id=GroupDecisionId("exile"), name=DisplayName("追放"), abstain_allowed=True, reveals_ballots=False
)
TEXTS = RefusalTexts(
    common_rules={
        kind: TextWithUnassignedPeople(f"{{actor}}は {kind.name} でできない。") for kind in CommonRuleRefusalKind
    },
    world_state={},
    hidden=TextWithUnassignedPeople("今はできない。"),
)

_CHECK = ActionPrerequisiteCheck()


def _world(**overrides: object) -> WorldInMemory:
    arguments: dict[str, object] = {
        "world": WORLD,
        "people": (ALICE, BOB),
        "spots": (LANDING, SHORE),
        "objects": (LEVER,),
        "sections": (CAGE,),
        "vitals": (PersonVitals.start(ALICE, HitPoints(10, 10)), PersonVitals.start(BOB, HitPoints(10, 10))),
    }
    arguments.update(overrides)
    world = WorldInMemory(**arguments)  # type: ignore[arg-type]
    world.whereabouts.place(PersonBody(ALICE), LANDING)
    world.whereabouts.place(PersonBody(BOB), LANDING)
    return world


def _reason(attempt: ActionAttempt, world: WorldInMemory) -> object:
    refusal = _CHECK.refusal(attempt, world.facts(), TEXTS)
    return None if refusal is None else refusal.reason


def _speak() -> SpeechAttempt:
    return SpeechAttempt(ALICE, OrdinaryVoice(), SpeechContent("おはよう"))


def _make_dead(world: WorldInMemory, person: PersonId) -> None:
    vitals = world.vitals[person]
    vitals.take_damage(Damage(10), WorldTick(0), WorldHappening())
    vitals.pass_time(WorldTick(0) + world.rules.death.grace, world.rules.death, world.rules.hunger)


class TestNothingBroken:
    """共通の前提をどれも破っていない行為を、断らないことを保証する。"""

    def test_returns_none_when_every_rule_holds(self) -> None:
        """動ける人が、段階の無い世界で、手が空いて疲れてもおらず、相手と同じ場所で介抱しようとすると、None を返す。"""
        assert _CHECK.refusal(TendAttempt(ALICE, BOB), _world().facts(), TEXTS) is None


class TestBusy:
    """前の行為を行っているあいだは、話すこと以外を Busy で断ることを保証する。"""

    def test_busy_person_is_refused_except_for_speaking(self) -> None:
        """行っている最中 (is_busy) の人が探そうとすると Busy で断り、話すことは断らない。"""
        world = _world()
        world.vitals[ALICE].start_action(until=WorldTick(5))

        assert _reason(SpotSearchAttempt(ALICE), world) == Busy()
        assert _reason(_speak(), world) is None

    def test_person_whose_action_has_ended_is_not_busy(self) -> None:
        """行っているあいだが今の tick までに終わっていれば、Busy で断らない。"""
        world = _world()
        world.vitals[ALICE].start_action(until=WorldTick(0))

        assert _reason(SpotSearchAttempt(ALICE), world) is None


class TestReach:
    """物に届くか、同じ場所にいるかを、居場所と区画の宣言で確かめることを保証する。"""

    def test_object_reachable_only_from_section_is_out_of_reach_from_outside(self) -> None:
        """籠の中からしか届かないレバーに、同じ場所の籠の外から触ろうとすると OutOfReach で断る。"""
        attempt = ObjectInteractionAttempt(ALICE, LEVER, PULL, {}, Openly())

        assert _reason(attempt, _world()) == OutOfReach()

    def test_object_reachable_only_from_section_is_reachable_from_inside(self) -> None:
        """籠の中にいれば、籠の中からしか届かないレバーに触れる。"""
        world = _world()
        world.whereabouts.enter_section(PersonBody(ALICE), CAGE, frozenset())
        attempt = ObjectInteractionAttempt(ALICE, LEVER, PULL, {}, Openly())

        assert _reason(attempt, world) is None

    def test_object_at_another_spot_is_not_together(self) -> None:
        """別の場所にある物に触ろうとすると、区画より先に NotTogether で断る。"""
        world = _world()
        world.whereabouts.teleport(PersonBody(ALICE), SHORE)
        attempt = ObjectInteractionAttempt(ALICE, LEVER, PULL, {}, Openly())

        assert _reason(attempt, world) == NotTogether()

    def test_person_at_another_spot_is_not_together(self) -> None:
        """相手が別の場所にいるのに介抱しようとすると NotTogether で断る。"""
        world = _world()
        world.whereabouts.teleport(PersonBody(BOB), SHORE)

        assert _reason(TendAttempt(ALICE, BOB), world) == NotTogether()

    def test_ground_item_at_another_spot_is_not_together(self) -> None:
        """拾おうとした品物が、いる場所の地面に無ければ NotTogether で断り、あれば断らない。"""
        world = _world()
        lamp = ItemInstanceId("lamp_1")
        world.ground_items_at(SHORE.spot_id).place(lamp)
        attempt = GroundItemPickupAttempt(ALICE, lamp, Openly())

        assert _reason(attempt, world) == NotTogether()
        world.whereabouts.teleport(PersonBody(ALICE), SHORE)
        assert _reason(attempt, world) is None


def _stage(allowed: frozenset[ActionKind | InteractionId]) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId("night"),
        name=DisplayName("夜"),
        description=DescriptionText("夜"),
        allowed_actions=allowed,
    )


def _world_in_stage(declaration: WorldStageDeclaration) -> WorldInMemory:
    return _world(
        world_stage=WorldStage.open(WORLD, declaration, WorldTick(0)),
        stage_declarations=(declaration,),
    )


class TestStage:
    """段階で許されていない行為を NotAllowedInThisStage で断ることを保証する。"""

    def test_built_in_attempt_is_checked_by_action_kind(self) -> None:
        """段階が SPEAK だけを許すとき、話すことは断らず、探すことは NotAllowedInThisStage で断る。"""
        world = _world_in_stage(_stage(frozenset({ActionKind.SPEAK})))

        assert _reason(_speak(), world) is None
        assert _reason(SpotSearchAttempt(ALICE), world) == NotAllowedInThisStage()

    def test_interaction_is_checked_by_interaction_id(self) -> None:
        """段階が InteractionId("bite") だけを許すとき、噛む操作は断らず、INTERACT_WITH_PERSON だけでは殴る操作を NotAllowedInThisStage で断る。"""
        world = _world_in_stage(_stage(frozenset({InteractionId("bite"), ActionKind.INTERACT_WITH_PERSON})))
        bite = PersonInteractionAttempt(ALICE, BOB, InteractionForTests(InteractionId("bite")), {}, Openly())
        hit = PersonInteractionAttempt(ALICE, BOB, InteractionForTests(InteractionId("hit")), {}, Openly())

        assert _reason(bite, world) is None
        assert _reason(hit, world) == NotAllowedInThisStage()


class TestActorCannotAct:
    """倒れた人、結末が決まった人、去った人に許されない行為を ActorCannotAct で断ることを保証する。"""

    def test_departed_person_can_travel_but_not_speak(self) -> None:
        """departed_persons_act の世界で死んで去った人は、移動と耳を澄ますことは断られず、話すことは ActorCannotAct で断る。"""
        world = _world(rules=replace(world_rules_for_tests(), departed_persons_act=True))
        _make_dead(world, ALICE)
        world.whereabouts.place(DepartedPerson(ALICE), LANDING)

        assert _reason(TravelAttempt(ALICE, SHORE), world) is None
        assert _reason(ListeningAttempt(ALICE), world) is None
        assert _reason(_speak(), world) == ActorCannotAct()

    def test_departed_person_is_checked_at_the_departed_whereabouts(self) -> None:
        """去った人にもできる物への操作は、体ではなく去った人の居場所で届くかを確かめる。"""
        world = _world(rules=replace(world_rules_for_tests(), departed_persons_act=True))
        _make_dead(world, ALICE)
        world.whereabouts.place(DepartedPerson(ALICE), SHORE)
        haunt = InteractionForTests(InteractionId("haunt"), actor_requirement=LivingOrDeparted())

        assert _reason(ObjectInteractionAttempt(ALICE, LEVER, haunt, {}, Openly()), world) == NotTogether()

    def test_dead_person_cannot_act_where_departed_persons_do_not_act(self) -> None:
        """departed_persons_act が偽の世界では、死んだ人は移動も ActorCannotAct で断る。"""
        world = _world()
        _make_dead(world, ALICE)

        assert _reason(TravelAttempt(ALICE, SHORE), world) == ActorCannotAct()

    def test_fallen_person_cannot_act(self) -> None:
        """倒れた (Down) 人は、去った人にもできる移動も ActorCannotAct で断る。"""
        world = _world(rules=replace(world_rules_for_tests(), departed_persons_act=True))
        world.vitals[ALICE].take_damage(Damage(10), WorldTick(0), WorldHappening())

        assert _reason(TravelAttempt(ALICE, SHORE), world) == ActorCannotAct()

    def test_person_whose_outcome_is_decided_cannot_act(self) -> None:
        """生きていても結末が決まった人は、ActorCannotAct で断る。"""
        world = _world()
        world.outcomes.decide(ALICE, DeclaredOutcome(OutcomeId("rescued")))

        assert _reason(_speak(), world) == ActorCannotAct()


class TestTooTired:
    """疲れの限界では、体を使う行為だけを TooTired で断ることを保証する。"""

    def test_ballot_is_not_refused_at_fatigue_limit_but_search_is(self) -> None:
        """疲れが限界に届いた人の、体を使わない投票は断らず、体を使う探すことは TooTired で断る。"""
        fatigue = FatigueRule(
            per_exertion=FatigueAmount(2),
            limit=FatigueAmount(2),
            levels=(FatigueLevel(FatigueAmount(0), FatigueLevelName("元気")),),
        )
        world = _world(rules=replace(world_rules_for_tests(), fatigue=fatigue))
        world.vitals[ALICE].exert(fatigue)

        assert _reason(GroupDecisionBallotAttempt(ALICE, EXILE, VoteFor(BOB)), world) is None
        assert _reason(SpotSearchAttempt(ALICE), world) == TooTired()


class TestRefusalText:
    """断った理由の文が、RefusalTexts の文に行った人を当てたものであることを保証する。"""

    def test_refusal_carries_the_attempt_and_the_text_about_the_actor(self) -> None:
        """Busy で断ると、ActionRefusal は試した行為と、RefusalTexts の BUSY の文に行った人を当てた TextAboutPeople を持つ。"""
        world = _world()
        world.vitals[ALICE].start_action(until=WorldTick(5))
        attempt = SpotSearchAttempt(ALICE)

        assert _CHECK.refusal(attempt, world.facts(), TEXTS) == ActionRefusal(
            attempt=attempt,
            reason=Busy(),
            text=TextAboutPeople(TextWithUnassignedPeople("{actor}は BUSY でできない。"), {"actor": ALICE}),
        )


class TestOrderOfRules:
    """複数の前提を破っているとき、どの理由で断るかを保証する。"""

    def test_fallen_busy_person_is_refused_as_unable_to_act(self) -> None:
        """行っている最中に倒れた人は、Busy ではなく ActorCannotAct で断る。"""
        world = _world()
        world.vitals[ALICE].start_action(until=WorldTick(5))
        world.vitals[ALICE].take_damage(Damage(10), WorldTick(0), WorldHappening())

        assert _reason(SpotSearchAttempt(ALICE), world) == ActorCannotAct()

    def test_stage_is_checked_before_busy(self) -> None:
        """段階で許されず、行っている最中でもある行為は、NotAllowedInThisStage で断る。"""
        world = _world_in_stage(_stage(frozenset({ActionKind.SPEAK})))
        world.vitals[ALICE].start_action(until=WorldTick(5))

        assert _reason(SpotSearchAttempt(ALICE), world) == NotAllowedInThisStage()
