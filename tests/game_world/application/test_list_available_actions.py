from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar

import pytest

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused, ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.cast_ballot import CastBallot, CastBallotCommand
from ai_rpg_world.game_world.application.action.drop_item import DropItem, DropItemCommand
from ai_rpg_world.game_world.application.action.enter_section import EnterSection, EnterSectionCommand
from ai_rpg_world.game_world.application.action.hand_over_items import HandOverItems, HandOverItemsCommand
from ai_rpg_world.game_world.application.action.hold_item import HoldItem, HoldItemCommand
from ai_rpg_world.game_world.application.action.interact_with_carried_item import (
    InteractWithCarriedItem,
    InteractWithCarriedItemCommand,
)
from ai_rpg_world.game_world.application.action.interact_with_object import (
    InteractWithObject,
    InteractWithObjectCommand,
)
from ai_rpg_world.game_world.application.action.interact_with_person import (
    InteractWithPerson,
    InteractWithPersonCommand,
)
from ai_rpg_world.game_world.application.action.leave_section import LeaveSection, LeaveSectionCommand
from ai_rpg_world.game_world.application.action.pick_up_ground_item import PickUpGroundItem, PickUpGroundItemCommand
from ai_rpg_world.game_world.application.action.put_away_item import PutAwayItem, PutAwayItemCommand
from ai_rpg_world.game_world.application.action.search_spot import SearchSpot, SearchSpotCommand
from ai_rpg_world.game_world.application.action.speak import Speak, SpeakCommand
from ai_rpg_world.game_world.application.action.start_travel import StartTravel, StartTravelCommand
from ai_rpg_world.game_world.application.action.tend_fallen_person import TendFallenPerson, TendFallenPersonCommand
from ai_rpg_world.game_world.application.action.use_item import UseItem, UseItemCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.list_available_actions import (
    ListAvailableActions,
    ListAvailableActionsCommand,
)
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_arguments import (
    ArgumentsNotChosen,
    ChosenArguments,
    TextArgumentValue,
)
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration, ItemArgument, TextArgument
from ai_rpg_world.game_world.domain.action.available_actions import AvailableAction, Doable, NotNow
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    EnterSectionAttempt,
    GroundItemPickupAttempt,
    GroupDecisionBallotAttempt,
    HoldItemAttempt,
    ItemDropAttempt,
    ItemHandOverAttempt,
    ItemUseAttempt,
    LeaveSectionAttempt,
    ListeningAttempt,
    PutAwayItemAttempt,
    SpeechAttempt,
    SpotSearchAttempt,
    TendAttempt,
    TravelAttempt,
    WaitAttempt,
)
from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    CarriedItemInteractionAttempt,
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
    SomeoneInTheDark,
)
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.offered_action import (
    BALLOT,
    CONTENT,
    DECISION,
    DESTINATION,
    HOW,
    ITEM,
    LISTENER,
    REACH,
    RECIPIENT,
    SECTION_MOVE,
    TARGET,
    ActionChoiceKind,
    OfferedAction,
    OfferedFreeText,
    OfferedItemPick,
    OfferedStep,
    OfferedValue,
)
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, Shout, SpeechContentNotChosen, Whisper
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason
from ai_rpg_world.game_world.domain.condition.argument_condition import ArgumentEqualsCondition
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition, NotCondition
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.membership_condition import IsMemberCondition
from ai_rpg_world.game_world.domain.condition.subject import Target
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.declaration.object_and_item import ObjectAppearance
from ai_rpg_world.game_world.domain.declaration.progress import (
    FlagDeclaration,
    GroupDecisionDeclaration,
    OutcomeDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.interaction_declaration import InteractionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.item_use_declaration import ItemUseDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.noun_interaction_declarations import (
    ItemInteractionDeclaration,
    ObjectInteractionDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.body_effects import DamageEffect
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.exception.action_exception import ArgumentsNotChosenException
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PersonRef, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import DeclaredOutcome
from ai_rpg_world.game_world.domain.person.life_state import Dead, WorldHappening
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending, TendRule
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DescriptionText,
    DisplayName,
    FlagId,
    GroupId,
    GroupingId,
    InteractionId,
    OutcomeId,
    PersonId,
    Rate,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.domain.world_progress import Abstain, VoteFor
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.verb_declarations_for_tests import (
    everyone_votes_on,
    lever_pulled_quietly,
    pull_lever,
    seen_clearly_only,
)
from tests.game_world.support.verb_parts_for_tests import ChangesNothing
from tests.game_world.support.world_design_for_tests import (
    access_to,
    built_in_action_perceptions,
    character,
    compose_world,
    group_decision,
    item_spec,
    nouns,
    obj,
    passage,
    section,
    spot,
)
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_Read = TypeVar("_Read")
_WORLD = WorldId("list_available_actions_world")
_ALICE, _BOB, _CAROL = PersonId("alice"), PersonId("bob"), PersonId("carol")
_NOW = WorldTick(0)
_KEY_FOUND = FlagDeclaration(FlagId("key_found"), DescriptionText("鍵を見つけた"), initially_raised=False)
_DOOR_OPENED = FlagDeclaration(FlagId("door_opened"), DescriptionText("扉が開いた"), initially_raised=False)
_LAMP_LIT = FlagDeclaration(FlagId("lamp_lit"), DescriptionText("ランプを灯した"), initially_raised=False)
_NO_KEY_TEXT = "鍵が無い。"
_LAMP = item_spec("lamp")
_ROCK = item_spec("rock")
_ROPE = item_spec("rope")
_DOOR = replace(obj("door", "mine"), appearance=ObjectAppearance(seen_in_dark=True, hidden_until_revealed=False))
_CART = section("cart", "mine")
_MINE_EXIT = passage("mine_exit", ("mine", "outside"))
_UNLOCK = replace(
    pull_lever(()),
    interaction_id=InteractionId("unlock"),
    precondition=FlagIsRaisedCondition(_KEY_FOUND, TextWithUnassignedPeople(_NO_KEY_TEXT)),
    effect=RaiseFlagEffect(_DOOR_OPENED),
)
_KNOCK = replace(pull_lever(()), interaction_id=InteractionId("knock"))
_WOLVES = GroupDeclaration(
    group_id=GroupId("wolves"),
    grouping=GroupingDeclaration(
        grouping_id=GroupingId("side"), name=DisplayName("陣営"), visibility=MembershipVisibility.NOBODY, changes=False
    ),
    name=DisplayName("人狼"),
    members_know_each_other=False,
    shared_description=NoSharedDescription(),
)
_NOT_A_WOLF_TEXT = "仲間ではない。"
_CARVE = replace(
    pull_lever((ArgumentDeclaration(ArgumentName("words"), TextArgument()),)),
    interaction_id=InteractionId("carve"),
)
_ALREADY_OPEN_TEXT = "扉はもう開いている。"
_OPEN_WITH_CODE = replace(
    pull_lever((ArgumentDeclaration(ArgumentName("code"), TextArgument()),)),
    interaction_id=InteractionId("open_with_code"),
    precondition=AllOfCondition(
        children=(
            NotCondition(FlagIsRaisedCondition(_DOOR_OPENED, NoText()), TextWithUnassignedPeople(_ALREADY_OPEN_TEXT)),
            ArgumentEqualsCondition(ArgumentName("code"), TextArgumentValue("1907"), NoText()),
        ),
        failure_text=TextWithUnassignedPeople("扉はびくともしない。"),
    ),
    effect=RaiseFlagEffect(_DOOR_OPENED),
)
_RUB = replace(pull_lever(()), interaction_id=InteractionId("rub"), effect=RaiseFlagEffect(_KEY_FOUND))
_TAP: InteractionDeclaration = replace(
    pull_lever(()),
    interaction_id=InteractionId("tap"),
    effect=DamageEffect(Target(), Damage(1)),
    perceived_as=replace(
        lever_pulled_quietly(),
        witness=seen_clearly_only("{actor}が{target}の肩を叩いた。"),
        target=seen_clearly_only("{actor}に肩を叩かれた。"),
    ),
    reaches_unseen=True,
)
_WAVE: InteractionDeclaration = replace(
    _TAP, interaction_id=InteractionId("wave"), effect=ChangesNothing(), reaches_unseen=False
)
_HOWL_WITH: InteractionDeclaration = replace(
    _WAVE,
    interaction_id=InteractionId("howl_with"),
    precondition=IsMemberCondition(Target(), _WOLVES, TextWithUnassignedPeople(_NOT_A_WOLF_TEXT)),
)
_GREET_BY_KEY: InteractionDeclaration = replace(
    _TAP,
    interaction_id=InteractionId("greet_by_key"),
    precondition=FlagIsRaisedCondition(_KEY_FOUND, TextWithUnassignedPeople(_NO_KEY_TEXT)),
)


def _mine(lighting: Lighting) -> SpotDeclaration:
    mine = spot("mine")
    return replace(mine, atmosphere=replace(mine.atmosphere, lighting=lighting))


_RESCUED = OutcomeDeclaration(
    outcome_id=OutcomeId("rescued"),
    name=DisplayName("救出"),
    announcement=TextWithUnassignedPeople("{each_person}は外へ出た。"),
)


def _rescue_alice(session: WorldSession) -> None:
    session.aggregates().outcomes().decide(_ALICE, DeclaredOutcome(_RESCUED), WorldTick(0))
    session.aggregates().whereabouts().remove(PersonBody(_ALICE))


class _Mine:
    """坑道に alice・bob・carol がいる。alice はランプを手に持ち、石を荷に入れている。bob は倒れていて、地面にロープがある。扉と、乗り込めるトロッコ、外への通路がある。"""

    def __init__(
        self,
        lighting: Lighting = Lighting.BRIGHT,
        *,
        object_interactions: tuple[InteractionDeclaration, ...] = (_UNLOCK, _KNOCK),
        person_interactions: tuple[InteractionDeclaration, ...] = (_WAVE,),
        tending: TendRule | NoTending = TendRule(revive_hp_rate=Rate(0.5)),
    ) -> None:
        self.design = _design(lighting, object_interactions, person_interactions, tending)
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="list_available_actions_world",
            scenario_hash="list_available_actions_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=_WORLD, design=self.design))
        self.scope = CommandScope(self.store, CommittedEventsDistributor())
        self.carry_out = CarryOutAction(self.scope, self.design)
        self.rope = self.scope.run(_drop_rope_and_fell_bob)

    def lists(self, person: PersonId = _ALICE) -> tuple[AvailableAction, ...]:
        return ListAvailableActions(self.scope, self.design)(ListAvailableActionsCommand(person)).actions

    def tries(self, attempt: ActionAttempt) -> ActionReply:
        design, carry_out = self.design, self.carry_out
        if isinstance(attempt, SpotSearchAttempt):
            return SearchSpot(carry_out, design)(SearchSpotCommand(attempt))
        if isinstance(attempt, TravelAttempt):
            return StartTravel(carry_out, design)(StartTravelCommand(attempt))
        if isinstance(attempt, GroundItemPickupAttempt):
            return PickUpGroundItem(carry_out)(PickUpGroundItemCommand(attempt))
        if isinstance(attempt, ItemDropAttempt):
            return DropItem(carry_out)(DropItemCommand(attempt))
        if isinstance(attempt, HoldItemAttempt):
            return HoldItem(carry_out)(HoldItemCommand(attempt))
        if isinstance(attempt, PutAwayItemAttempt):
            return PutAwayItem(carry_out)(PutAwayItemCommand(attempt))
        if isinstance(attempt, ItemUseAttempt):
            return UseItem(carry_out, design)(UseItemCommand(attempt))
        if isinstance(attempt, TendAttempt):
            return TendFallenPerson(carry_out)(TendFallenPersonCommand(attempt))
        if isinstance(attempt, ItemHandOverAttempt):
            return HandOverItems(carry_out)(HandOverItemsCommand(attempt))
        if isinstance(attempt, EnterSectionAttempt):
            return EnterSection(carry_out, design)(EnterSectionCommand(attempt))
        if isinstance(attempt, LeaveSectionAttempt):
            return LeaveSection(carry_out, design)(LeaveSectionCommand(attempt))
        if isinstance(attempt, ObjectInteractionAttempt):
            return InteractWithObject(carry_out, design)(InteractWithObjectCommand(attempt))
        if isinstance(attempt, CarriedItemInteractionAttempt):
            return InteractWithCarriedItem(carry_out, design)(InteractWithCarriedItemCommand(attempt))
        if isinstance(attempt, PersonInteractionAttempt):
            return InteractWithPerson(carry_out, design)(InteractWithPersonCommand(attempt))
        if isinstance(attempt, ListeningAttempt | WaitAttempt):
            return carry_out(attempt, _ChangesNothing())
        raise AssertionError(f"no use case for {attempt}")

    def lamp(self) -> ItemInstanceId:
        return self._read(lambda facts: facts.inventory(_ALICE).held_items()[0])

    def rock(self) -> ItemInstanceId:
        return self._read(lambda facts: facts.inventory(_ALICE).packed_items()[0])

    def enter_cart(self) -> None:
        self.scope.run(
            lambda session: session.aggregates().whereabouts().enter_section(PersonBody(_ALICE), _CART, frozenset())
        )

    def open_door(self) -> None:
        self.scope.run(
            lambda session: session.aggregates().flags().raise_flag(_DOOR_OPENED, ActionAttemptForTests(actor_id=_BOB))
        )

    def offered(
        self, attempt: ActionAttempt, items_seen_on: dict[PersonId, tuple[ItemInstanceId, ...]] | None = None
    ) -> OfferedAction:
        def read(facts: WorldFacts) -> OfferedAction:
            people = WorldPerceptionSenses(facts).view_for(_ALICE)
            return attempt.offered_as(ChoiceWording(_ALICE, self.design, facts, people, items_seen_on or {}))

        return self._read(read)

    def ref_of(self, person: PersonId) -> PersonRef:
        return self._read(lambda facts: WorldPerceptionSenses(facts).view_for(_ALICE).ref_of(person))

    def keep_alice_busy(self) -> None:
        self.scope.run(
            lambda session: (
                session.aggregates()
                .vitals(_ALICE)
                .start_acting(pull_lever(()).exertion, _NOW + Ticks(5), session.facts().rules().fatigue)
            )
        )

    def next_fraction(self) -> float:
        return self._read(lambda facts: facts.random().next_fraction())

    def _read(self, read: Callable[[WorldFacts], _Read]) -> _Read:
        session = self.store.session()
        value = read(session.facts())
        session.roll_back()
        return value


class _ChangesNothing:
    def unmet_precondition(self, attempt: ActionAttempt, facts: WorldFacts) -> None:
        return None

    def change_world(self, attempt: ActionAttempt, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        return Ticks(0)


def _drop_rope_and_fell_bob(session: WorldSession) -> ItemInstanceId:
    world = session.aggregates()
    rope = world.bring_item_into_world(_ROPE, _NOW)
    world.ground_items(_mine(Lighting.BRIGHT).spot_id).place(rope)
    world.vitals(_BOB).take_damage(Damage(999), _NOW, WorldHappening())
    return rope


def _design(
    lighting: Lighting,
    object_interactions: tuple[InteractionDeclaration, ...],
    person_interactions: tuple[InteractionDeclaration, ...],
    tending: TendRule | NoTending,
) -> WorldDesign:
    return compose_world(
        nouns(
            flags=[_KEY_FOUND, _DOOR_OPENED, _LAMP_LIT],
            spots=[_mine(lighting), spot("outside")],
            passages=[_MINE_EXIT],
            objects=[_DOOR],
            item_specs=[_LAMP, _ROCK, _ROPE],
            outcomes=[_RESCUED],
            groupings=[_WOLVES.grouping],
            groups=[_WOLVES],
            sections=[_CART],
            characters=[
                replace(
                    character("alice", "mine"),
                    initial_items=(_LAMP.item_spec_id, _ROCK.item_spec_id),
                    initial_held=(_LAMP.item_spec_id,),
                ),
                replace(character("bob", "mine"), initial_groups=(_WOLVES.group_id,)),
                character("carol", "mine"),
            ],
        ),
        object_interactions=[ObjectInteractionDeclaration(obj=_DOOR, interaction=i) for i in object_interactions],
        item_interactions=[ItemInteractionDeclaration(item_spec=_LAMP, interaction=_RUB)],
        item_uses=[ItemUseDeclaration(item_spec=_LAMP, effect=RaiseFlagEffect(_LAMP_LIT))],
        section_accesses=[access_to(_CART)],
        person_interactions=person_interactions,
        world_rules=replace(world_rules_for_tests(), tend=tending),
        built_in_action_perceptions_=built_in_action_perceptions(),
    )


_UNWORDED = SpeechContentNotChosen()


def _worded(attempts: list[ActionAttempt]) -> list[ActionAttempt]:
    return [
        a
        for a in attempts
        if not isinstance(a, SpeechAttempt)
        and not (isinstance(a, ObjectInteractionAttempt) and isinstance(a.arguments, ArgumentsNotChosen))
    ]


def _doable(actions: tuple[AvailableAction, ...]) -> list[ActionAttempt]:
    return [action.attempt for action in actions if isinstance(action.standing, Doable)]


def _not_now(actions: tuple[AvailableAction, ...]) -> list[ActionAttempt]:
    return [action.attempt for action in actions if isinstance(action.standing, NotNow)]


def _reason_of(actions: tuple[AvailableAction, ...], attempt: ActionAttempt) -> str:
    standing = next(action.standing for action in actions if action.attempt == attempt)
    assert isinstance(standing, NotNow)
    return standing.reason.template.template


class TestListAvailableActions:
    """ListAvailableActions が、場面に見えるものと持ち物を候補にし、試したときと同じ確認でできる・できないに分ける挙動を保証する。"""

    def test_bright_mine_lists_every_candidate_from_surroundings_and_belongings(self) -> None:
        """明るい坑道で alice が一覧を求めると、探す・耳を澄ます・待つ、ふつうの声で話す・叫ぶ・carol にささやく、外への移動、ロープを拾う、ランプと石を置く、石を持つ、ランプをしまう・使う・磨く、bob の介抱、carol へランプと石を渡す、トロッコに乗る、扉を叩く、bob と carol に手を振る、ができるにこの順で並び、扉を開けるができないに並ぶ。"""
        mine = _Mine()
        lamp, rock = mine.lamp(), mine.rock()
        door, cart = mine.design.nouns.object_of(_DOOR.object_id), mine.design.section_access(_CART.section_id)
        outside = mine.design.nouns.spot_of(spot("outside").spot_id)

        actions = mine.lists()

        assert _doable(actions) == list[ActionAttempt](
            [
                SpotSearchAttempt(_ALICE),
                ListeningAttempt(_ALICE),
                WaitAttempt(_ALICE, NoReason()),
                SpeechAttempt(_ALICE, OrdinaryVoice(), _UNWORDED),
                SpeechAttempt(_ALICE, Shout(), _UNWORDED),
                SpeechAttempt(_ALICE, Whisper(_CAROL), _UNWORDED),
                TravelAttempt(_ALICE, outside),
                GroundItemPickupAttempt(_ALICE, mine.rope, Openly()),
                ItemDropAttempt(_ALICE, lamp, Openly()),
                ItemDropAttempt(_ALICE, rock, Openly()),
                HoldItemAttempt(_ALICE, rock),
                PutAwayItemAttempt(_ALICE, lamp),
                ItemUseAttempt(_ALICE, lamp),
                TendAttempt(_ALICE, _BOB),
                ItemHandOverAttempt(_ALICE, _CAROL, (lamp,), Openly()),
                ItemHandOverAttempt(_ALICE, _CAROL, (rock,), Openly()),
                EnterSectionAttempt(_ALICE, cart),
                ObjectInteractionAttempt(_ALICE, door, _KNOCK, ChosenArguments(), Openly()),
                CarriedItemInteractionAttempt(_ALICE, lamp, _RUB, ChosenArguments(), Openly()),
                PersonInteractionAttempt(_ALICE, _CAROL, _WAVE, ChosenArguments(), Openly()),
                PersonInteractionAttempt(_ALICE, _BOB, _WAVE, ChosenArguments(), Openly()),
            ]
        )
        assert _not_now(actions) == [ObjectInteractionAttempt(_ALICE, door, _UNLOCK, ChosenArguments(), Openly())]

    def test_every_doable_action_goes_through_when_tried(self) -> None:
        """明るい坑道でできるに分けた行為のうち、値を選ぶ必要の無いものは、1 つずつ新しい坑道で試すと、どれも断られずに通る。"""
        doable = _worded(_doable(_Mine().lists()))

        replies = [(attempt, _Mine().tries(attempt)) for attempt in doable]

        assert [(attempt, reply) for attempt, reply in replies if not isinstance(reply, ActionDone)] == []
        assert len(replies) == 18

    def test_not_now_action_is_refused_when_tried_with_the_same_text(self) -> None:
        """鍵が無いあいだ、扉を開けるはできないに分かれ、理由は作者の failure_text。試すと同じ文で断られる。"""
        mine = _Mine()
        actions = mine.lists()
        [unlock] = _not_now(actions)

        reply = mine.tries(unlock)

        assert _reason_of(actions, unlock) == _NO_KEY_TEXT
        assert isinstance(reply, ActionRefused)
        assert reply.refusal.text.template.template == _NO_KEY_TEXT

    def test_action_with_hidden_failure_is_listed_as_doable(self) -> None:
        """誰にも見えない陣営の所属を前提にする操作 (人狼と遠吠えする) は、相手が仲間でない carol でもできるに出る。試すと、伏せた理由で断られる。"""
        mine = _Mine(person_interactions=(_HOWL_WITH,))
        toward_carol = PersonInteractionAttempt(_ALICE, _CAROL, _HOWL_WITH, ChosenArguments(), Openly())

        actions = mine.lists()
        reply = mine.tries(toward_carol)

        assert [a for a in _doable(actions) if isinstance(a, PersonInteractionAttempt)] == [
            toward_carol,
            PersonInteractionAttempt(_ALICE, _BOB, _HOWL_WITH, ChosenArguments(), Openly()),
        ]
        assert isinstance(reply, ActionRefused)
        assert reply.refusal.text.template.template != _NOT_A_WOLF_TEXT

    def test_interaction_needing_words_is_listed_with_arguments_not_chosen(self) -> None:
        """文の引数がある操作 (刻む) は、引数をまだ選んでいない試みとして、できるに出る。"""
        mine = _Mine(object_interactions=(_CARVE,))
        door = mine.design.nouns.object_of(_DOOR.object_id)

        actions = mine.lists()

        assert [a for a in _doable(actions) if isinstance(a, ObjectInteractionAttempt)] == [
            ObjectInteractionAttempt(_ALICE, door, _CARVE, ArgumentsNotChosen(), Openly())
        ]

    def test_interaction_awaiting_its_code_is_doable_while_the_door_is_closed(self) -> None:
        """「扉が開いていない」かつ「番号が 1907」を前提にする操作は、扉が閉じているあいだ、番号を読まずにできるに出る。"""
        mine = _Mine(object_interactions=(_OPEN_WITH_CODE,))
        door = mine.design.nouns.object_of(_DOOR.object_id)

        actions = mine.lists()

        assert ObjectInteractionAttempt(_ALICE, door, _OPEN_WITH_CODE, ArgumentsNotChosen(), Openly()) in _doable(
            actions
        )

    def test_interaction_awaiting_its_code_is_not_now_once_the_door_is_open(self) -> None:
        """扉が開いたあとは、番号が分からなくても前提の前半が成り立たないので、作者の文を理由にできないに出る。"""
        mine = _Mine(object_interactions=(_OPEN_WITH_CODE,))
        mine.open_door()
        door = mine.design.nouns.object_of(_DOOR.object_id)
        unworded = ObjectInteractionAttempt(_ALICE, door, _OPEN_WITH_CODE, ArgumentsNotChosen(), Openly())

        actions = mine.lists()

        assert unworded in _not_now(actions)
        assert _reason_of(actions, unworded) == _ALREADY_OPEN_TEXT

    def test_interaction_with_arguments_not_chosen_cannot_take_effect(self) -> None:
        """引数をまだ選んでいない試みを試すと、世界を変えずに ArgumentsNotChosenException を投げる。"""
        mine = _Mine(object_interactions=(_OPEN_WITH_CODE,))
        door = mine.design.nouns.object_of(_DOOR.object_id)

        with pytest.raises(ArgumentsNotChosenException):
            mine.tries(ObjectInteractionAttempt(_ALICE, door, _OPEN_WITH_CODE, ArgumentsNotChosen(), Openly()))

    def test_dark_mine_hides_ground_items_and_unidentified_people(self) -> None:
        """暗い坑道では、地面のロープを拾う、誰か分からない bob の介抱、carol へ渡す、は候補に出ない。暗がりで見える扉の操作は出る。"""
        mine = _Mine(Lighting.DARK)

        attempts = [action.attempt for action in mine.lists()]

        assert [a for a in attempts if isinstance(a, GroundItemPickupAttempt | TendAttempt | ItemHandOverAttempt)] == []
        assert len([a for a in attempts if isinstance(a, ObjectInteractionAttempt)]) == 2

    def test_dark_mine_offers_only_interactions_reaching_the_unseen_toward_someone_in_the_dark(self) -> None:
        """暗い坑道に誰か分からない人がいると、人への操作は reaches_unseen の肩を叩くだけが、SomeoneInTheDark に 1 件出る。"""
        mine = _Mine(Lighting.DARK, person_interactions=(_TAP, _WAVE))

        attempts = [a.attempt for a in mine.lists() if isinstance(a.attempt, PersonInteractionAttempt)]

        assert attempts == [PersonInteractionAttempt(_ALICE, SomeoneInTheDark(), _TAP, ChosenArguments(), Openly())]

    def test_someone_in_the_dark_is_judged_by_common_rules_only(self) -> None:
        """暗がりの誰かへの操作は、行為ごとの前提 (鍵が要る) を満たしていなくてもできるに出る。相手を選ばないので、相手を引くくじも進まない。"""
        listed, untouched = (_Mine(Lighting.DARK, person_interactions=(_GREET_BY_KEY,)) for _ in range(2))

        actions = listed.lists()

        assert [a for a in _doable(actions) if isinstance(a, PersonInteractionAttempt)] == [
            PersonInteractionAttempt(_ALICE, SomeoneInTheDark(), _GREET_BY_KEY, ChosenArguments(), Openly())
        ]
        assert listed.next_fraction() == untouched.next_fraction()

    def test_pitch_dark_mine_offers_nothing_toward_people_or_the_ground(self) -> None:
        """真っ暗な坑道では人がいることも分からず、介抱・渡す・人への操作・暗がりの誰かへの操作と、地面のロープを拾うは出ない。"""
        mine = _Mine(Lighting.PITCH_DARK, person_interactions=(_TAP,))

        attempts = [action.attempt for action in mine.lists()]

        assert [
            a
            for a in attempts
            if isinstance(a, TendAttempt | ItemHandOverAttempt | PersonInteractionAttempt | GroundItemPickupAttempt)
        ] == []

    def test_world_without_tending_offers_no_tending(self) -> None:
        """介抱の規則が無い世界 (NoTending) では、倒れた bob が見えていても介抱は候補に出ない。"""
        mine = _Mine(tending=NoTending())

        attempts = [action.attempt for action in mine.lists()]

        assert [a for a in attempts if isinstance(a, TendAttempt)] == []

    def test_person_in_a_section_may_leave_it_but_not_enter_it_again(self) -> None:
        """トロッコに乗っている alice には、トロッコから降りるが出て、乗るは出ない。"""
        mine = _Mine()
        mine.enter_cart()
        cart = mine.design.section_access(_CART.section_id)

        attempts = [action.attempt for action in mine.lists()]

        assert LeaveSectionAttempt(_ALICE, cart) in attempts
        assert EnterSectionAttempt(_ALICE, cart) not in attempts

    def test_person_who_left_the_world_can_do_nothing(self) -> None:
        """結末が「救出」に決まって世界から外れた alice には、明るい坑道にいたことに関わらず、できる行為が 1 つも無い。"""
        mine = _Mine()
        mine.scope.run(_rescue_alice)

        assert _doable(mine.lists()) == []

    def test_speech_without_content_cannot_take_effect(self) -> None:
        """中身をまだ書いていない発話を試すと、世界を変える前に ArgumentsNotChosenException を投げる。"""
        mine = _Mine()

        with pytest.raises(ArgumentsNotChosenException):
            Speak(mine.carry_out)(SpeakCommand(SpeechAttempt(_ALICE, OrdinaryVoice(), _UNWORDED)))

    def test_busy_person_can_only_speak(self) -> None:
        """行っている最中の alice は、話すことだけができるに分かれ、ほかの行為はどれも共通の決まり Busy の断りの文でできないに分かれる。"""
        mine = _Mine()
        mine.keep_alice_busy()

        actions = mine.lists()

        assert _doable(actions) == [
            SpeechAttempt(_ALICE, OrdinaryVoice(), _UNWORDED),
            SpeechAttempt(_ALICE, Shout(), _UNWORDED),
            SpeechAttempt(_ALICE, Whisper(_CAROL), _UNWORDED),
        ]
        assert {_reason_of(actions, attempt) for attempt in _not_now(actions)} == {"BUSY のためできない。"}

    def test_dark_mine_offers_no_whisper_to_unidentified_people(self) -> None:
        """暗い坑道では、誰か分からない人にはささやけず、ふつうの声で話すと叫ぶだけが出る。"""
        mine = _Mine(Lighting.DARK)

        speeches = [a for a in _doable(mine.lists()) if isinstance(a, SpeechAttempt)]

        assert speeches == [
            SpeechAttempt(_ALICE, OrdinaryVoice(), _UNWORDED),
            SpeechAttempt(_ALICE, Shout(), _UNWORDED),
        ]


_GRAB = replace(
    pull_lever((ArgumentDeclaration(ArgumentName("loot"), ItemArgument()),)),
    interaction_id=InteractionId("grab"),
    display_label=DisplayName("持ち物をつかむ"),
)


class TestOfferedActions:
    """行為の試みが、どの行動の選択肢の、どの候補の道筋に当たるかを、alice に見えている名前で返すことを保証する。"""

    def test_travel_is_offered_as_travel_to_with_the_destination_name(self) -> None:
        """外への移動は「行く」の、行き先「outside」の道筋になる。"""
        mine = _Mine()
        outside = mine.design.nouns.spot_of(spot("outside").spot_id)

        offered = mine.offered(TravelAttempt(_ALICE, outside))

        assert offered == OfferedAction(ActionChoiceKind.TRAVEL_TO, (OfferedStep(DESTINATION, DisplayName("outside")),))

    def test_whisper_is_offered_with_the_listener_as_seen_and_free_content(self) -> None:
        """carol へのささやきは「話す」の、届け方「ささやく」→ 相手 carol (alice に見えている人の印) の道筋で、中身を自由に書く。"""
        mine = _Mine()

        offered = mine.offered(SpeechAttempt(_ALICE, Whisper(_CAROL), _UNWORDED))

        assert offered == OfferedAction(
            ActionChoiceKind.SPEAK,
            (OfferedStep(REACH, DisplayName("ささやく")), OfferedStep(LISTENER, mine.ref_of(_CAROL))),
            (OfferedFreeText(CONTENT),),
        )

    def test_object_interaction_offers_its_label_and_text_arguments(self) -> None:
        """扉を刻む操作は「操作する」の、相手「door」→ 操作の表示名の道筋で、引数 words を自由に書く。"""
        mine = _Mine(object_interactions=(_CARVE,))
        door = mine.design.nouns.object_of(_DOOR.object_id)

        offered = mine.offered(ObjectInteractionAttempt(_ALICE, door, _CARVE, ArgumentsNotChosen(), Openly()))

        assert offered == OfferedAction(
            ActionChoiceKind.INTERACT,
            (OfferedStep(TARGET, DisplayName("door")), OfferedStep(HOW, _CARVE.display_label)),
            (OfferedFreeText(OfferedValue("words", "words")),),
        )

    def test_carried_item_is_a_target_that_remembers_which_item_it_is(self) -> None:
        """ランプを磨く操作は、相手の候補がランプの品名で、どの品物かを数えるために品物の印を持つ。"""
        mine = _Mine()
        lamp = mine.lamp()

        offered = mine.offered(CarriedItemInteractionAttempt(_ALICE, lamp, _RUB, {}, Openly()))

        assert offered.steps == (OfferedStep(TARGET, DisplayName("lamp"), lamp), OfferedStep(HOW, _RUB.display_label))

    def test_item_argument_of_an_object_interaction_offers_the_actors_items(self) -> None:
        """物への操作の品物の引数は、行う人 (alice) の持ち物 (ランプと石) を候補にする。"""
        mine = _Mine(object_interactions=(_GRAB,))
        door, lamp, rock = mine.design.nouns.object_of(_DOOR.object_id), mine.lamp(), mine.rock()
        loot = OfferedValue("loot", "loot")

        offered = mine.offered(ObjectInteractionAttempt(_ALICE, door, _GRAB, ArgumentsNotChosen(), Openly()))

        assert offered.inputs == (
            OfferedItemPick(
                loot, (OfferedStep(loot, DisplayName("lamp"), lamp), OfferedStep(loot, DisplayName("rock"), rock))
            ),
        )

    def test_item_argument_of_a_person_interaction_offers_the_items_seen_on_the_target(self) -> None:
        """人への操作の品物の引数は、相手に見えている持ち物だけを候補にする。"""
        mine = _Mine(person_interactions=(_GRAB,))
        rock = mine.rock()
        loot = OfferedValue("loot", "loot")

        offered = mine.offered(
            PersonInteractionAttempt(_ALICE, _CAROL, _GRAB, ArgumentsNotChosen(), Openly()), {_CAROL: (rock,)}
        )

        assert offered.inputs == (OfferedItemPick(loot, (OfferedStep(loot, DisplayName("rock"), rock),)),)

    def test_someone_in_the_dark_is_offered_by_a_fixed_label(self) -> None:
        """暗がりの誰かへの操作は、相手の候補が「暗がりの誰か」になる。"""
        mine = _Mine(Lighting.DARK, person_interactions=(_TAP,))

        offered = mine.offered(PersonInteractionAttempt(_ALICE, SomeoneInTheDark(), _TAP, {}, Openly()))

        assert offered.steps[0] == OfferedStep(TARGET, DisplayName("暗がりの誰か"))

    def test_hand_over_and_section_entry_and_waiting(self) -> None:
        """carol へランプを渡すは「渡す」の carol → ランプ、トロッコに乗るは「区画に出入りする」の作者の文、待つは道筋の無い「待つ」。"""
        mine = _Mine()
        lamp, cart = mine.lamp(), mine.design.section_access(_CART.section_id)

        hand_over = mine.offered(ItemHandOverAttempt(_ALICE, _CAROL, (lamp,), Openly()))
        entry = mine.offered(EnterSectionAttempt(_ALICE, cart))
        waiting = mine.offered(WaitAttempt(_ALICE, NoReason()))

        assert hand_over.steps == (
            OfferedStep(RECIPIENT, mine.ref_of(_CAROL)),
            OfferedStep(ITEM, DisplayName("lamp"), lamp),
        )
        assert entry == OfferedAction(
            ActionChoiceKind.SET_SUB_LOCATION, (OfferedStep(SECTION_MOVE, DisplayName("乗り込む")),)
        )
        assert waiting == OfferedAction(ActionChoiceKind.WAIT)


_HARU, _NATSU, _AKI = PersonId("haru"), PersonId("natsu"), PersonId("aki")
_STAY_IN_MINE = group_decision("stay_in_mine")
_WATCH_TONIGHT = group_decision("watch_tonight")


class _Village:
    """広場にハルとナツが、坑道にアキがいる。ハルからアキは見えない。「誰を坑道に残すか」と「今夜の見張り」の 2 つの集団の決定が、この順に宣言されている。どちらも棄権を許す。"""

    def __init__(self) -> None:
        self.design = compose_world(
            nouns(
                spots=[spot("square"), spot("mine")],
                characters=[character("haru", "square"), character("natsu", "square"), character("aki", "mine")],
                group_decisions=[_STAY_IN_MINE, _WATCH_TONIGHT],
            ),
            group_decision_rules=[everyone_votes_on(_STAY_IN_MINE), everyone_votes_on(_WATCH_TONIGHT)],
            person_interactions=(_WAVE,),
            built_in_action_perceptions_=built_in_action_perceptions(),
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="list_available_actions_village",
            scenario_hash="list_available_actions_village",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=_WORLD, design=self.design))
        self.scope = CommandScope(self.store, CommittedEventsDistributor())
        self.carry_out = CarryOutAction(self.scope, self.design)

    def open(
        self, decision: GroupDecisionDeclaration, voters: frozenset[PersonId] = frozenset({_HARU, _NATSU, _AKI})
    ) -> None:
        self.scope.run(
            lambda session: (
                session.aggregates().group_decision(decision).start(voters, frozenset({_HARU, _NATSU, _AKI}))
            )
        )

    def withdraw_dead(self, decision: GroupDecisionDeclaration, person: PersonId) -> None:
        self.scope.run(
            lambda session: session.aggregates().group_decision(decision).withdraw_person(person, Dead(died_at=_NOW))
        )

    def lists(self, person: PersonId = _HARU) -> tuple[AvailableAction, ...]:
        return ListAvailableActions(self.scope, self.design)(ListAvailableActionsCommand(person)).actions

    def offered(self, attempt: ActionAttempt) -> tuple[OfferedAction, PersonRef]:
        session = self.store.session()
        facts = session.facts()
        people = WorldPerceptionSenses(facts).view_for(_HARU)
        offered = attempt.offered_as(ChoiceWording(_HARU, self.design, facts, people, {}))
        natsu = people.ref_of(_NATSU)
        session.roll_back()
        return offered, natsu

    def votes(self, attempt: GroupDecisionBallotAttempt) -> ActionReply:
        return CastBallot(self.carry_out)(CastBallotCommand(attempt))

    def votes_and_waits_it_out(self, attempt: GroupDecisionBallotAttempt) -> None:
        self.votes(attempt)
        for _ in range(self.design.world_rules.action_durations[ActionKind.CAST_BALLOT].value):
            self.scope.run(lambda session: session.clock().advance(self.design.day_night, session.facts()))


def _ballots(actions: tuple[AvailableAction, ...]) -> list[AvailableAction]:
    return [action for action in actions if isinstance(action.attempt, GroupDecisionBallotAttempt)]


def _ballot(decision: GroupDecisionDeclaration, choice: VoteFor | Abstain) -> GroupDecisionBallotAttempt:
    return GroupDecisionBallotAttempt(_HARU, decision, choice)


_EVERY_BALLOT_OF_HARU = [
    _ballot(_STAY_IN_MINE, VoteFor(_HARU)),
    _ballot(_STAY_IN_MINE, VoteFor(_NATSU)),
    _ballot(_STAY_IN_MINE, VoteFor(_AKI)),
    _ballot(_STAY_IN_MINE, Abstain()),
]


class TestListAvailableBallots:
    """ListAvailableActions が、開いている集団の決定の票を投票する人に並べ、GroupDecision と同じ判断でできる・できないに分ける挙動を保証する。"""

    def test_voter_lists_vote_for_every_choice_including_self_then_abstain(self) -> None:
        """「誰を坑道に残すか」が開いていると、ハルの一覧には、ハル・ナツと、場面に見えないアキへの票と棄権が人の宣言の順にできるで並び、人への操作より後に置かれる。"""
        village = _Village()
        village.open(_STAY_IN_MINE)

        actions = village.lists()

        assert [action.attempt for action in _ballots(actions)] == _EVERY_BALLOT_OF_HARU
        assert all(isinstance(action.standing, Doable) for action in _ballots(actions))
        kinds = [type(action.attempt) for action in actions]
        assert kinds.index(GroupDecisionBallotAttempt) > max(
            index for index, kind in enumerate(kinds) if kind is PersonInteractionAttempt
        )

    def test_every_doable_ballot_goes_through_when_tried(self) -> None:
        """2 つの決定が開いているとき、ハルのできるに分けた票は、1 つずつ新しい村で試すと、どれも断られずに通る。"""
        doable = [a for a in _doable(_opened_both().lists()) if isinstance(a, GroupDecisionBallotAttempt)]

        replies = [(attempt, _opened_both().votes(attempt)) for attempt in doable]

        assert [(attempt, reply) for attempt, reply in replies if not isinstance(reply, ActionDone)] == []
        assert len(replies) == 8

    def test_person_not_voting_finds_no_ballot(self) -> None:
        """投票する人がハルとナツだけの決定では、アキの一覧に票は 1 つも出ない。"""
        village = _Village()
        village.open(_STAY_IN_MINE, voters=frozenset({_HARU, _NATSU}))

        assert _ballots(village.lists(_AKI)) == []

    def test_voter_who_has_cast_finds_every_ballot_not_now_and_is_refused_with_the_same_text(self) -> None:
        """ナツに投票したハルの一覧には、4 つの票がすべてできないで並ぶ。試すと、一覧の理由と同じ文で断られる。"""
        village = _Village()
        village.open(_STAY_IN_MINE)
        village.votes_and_waits_it_out(_ballot(_STAY_IN_MINE, VoteFor(_NATSU)))

        actions = village.lists()
        reply = village.votes(_ballot(_STAY_IN_MINE, Abstain()))

        assert _not_now(tuple(_ballots(actions))) == _EVERY_BALLOT_OF_HARU
        assert isinstance(reply, ActionRefused)
        assert isinstance(reply.refusal.reason, WorldStateRefusal)
        assert {_reason_of(actions, attempt) for attempt in _EVERY_BALLOT_OF_HARU} == {
            reply.refusal.text.template.template
        }

    def test_dead_choice_vanishes_and_the_returned_voter_may_vote_again(self) -> None:
        """アキに投票したあとでアキが死ぬと、ハルの一覧からアキへの票が消え、戻った票でハル・ナツへの票と棄権ができるで並ぶ。"""
        village = _Village()
        village.open(_STAY_IN_MINE)
        village.votes_and_waits_it_out(_ballot(_STAY_IN_MINE, VoteFor(_AKI)))
        village.withdraw_dead(_STAY_IN_MINE, _AKI)

        actions = village.lists()

        assert [a.attempt for a in _ballots(actions) if isinstance(a.standing, Doable)] == [
            _ballot(_STAY_IN_MINE, VoteFor(_HARU)),
            _ballot(_STAY_IN_MINE, VoteFor(_NATSU)),
            _ballot(_STAY_IN_MINE, Abstain()),
        ]
        assert _not_now(tuple(_ballots(actions))) == []

    def test_ballot_is_offered_as_decision_then_choice(self) -> None:
        """ナツへの票は「投票する」の、決めごとの名前 → ナツ (ハルに見えている人の印) の道筋、棄権は「棄権する」になる。"""
        village = _Village()

        for_natsu, natsu = village.offered(_ballot(_STAY_IN_MINE, VoteFor(_NATSU)))
        abstain, _ = village.offered(_ballot(_STAY_IN_MINE, Abstain()))

        decision = OfferedStep(DECISION, _STAY_IN_MINE.name)
        assert for_natsu == OfferedAction(ActionChoiceKind.VOTE, (decision, OfferedStep(BALLOT, natsu)))
        assert abstain == OfferedAction(ActionChoiceKind.VOTE, (decision, OfferedStep(BALLOT, DisplayName("棄権する"))))

    def test_ballots_of_several_open_decisions_follow_declaration_order(self) -> None:
        """今夜の見張りを先に開いても、ハルの一覧は宣言の順に「誰を坑道に残すか」の票 4 つ、次に「今夜の見張り」の票 4 つと並ぶ。"""
        village = _Village()
        village.open(_WATCH_TONIGHT)
        village.open(_STAY_IN_MINE)

        attempts = [action.attempt for action in _ballots(village.lists())]

        assert attempts == [
            *_EVERY_BALLOT_OF_HARU,
            *(_ballot(_WATCH_TONIGHT, ballot.choice) for ballot in _EVERY_BALLOT_OF_HARU),
        ]


def _opened_both() -> _Village:
    village = _Village()
    village.open(_STAY_IN_MINE)
    village.open(_WATCH_TONIGHT)
    return village
