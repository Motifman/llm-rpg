from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused, ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
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
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration, TextArgument
from ai_rpg_world.game_world.domain.action.available_actions import AvailableAction, Doable, NotNow
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    EnterSectionAttempt,
    GroundItemPickupAttempt,
    HoldItemAttempt,
    ItemDropAttempt,
    ItemHandOverAttempt,
    ItemUseAttempt,
    LeaveSectionAttempt,
    ListeningAttempt,
    PutAwayItemAttempt,
    SpotSearchAttempt,
    TendAttempt,
    TravelAttempt,
    WaitAttempt,
)
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    CarriedItemInteractionAttempt,
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
    SomeoneInTheDark,
)
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason
from ai_rpg_world.game_world.domain.condition.condition import NoText
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
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
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
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.rules.tend_rule import TendRule
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DescriptionText,
    DisplayName,
    FlagId,
    GroupId,
    GroupingId,
    InteractionId,
    PersonId,
    Rate,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.verb_declarations_for_tests import lever_pulled_quietly, pull_lever, seen_clearly_only
from tests.game_world.support.verb_parts_for_tests import ChangesNothing
from tests.game_world.support.world_design_for_tests import (
    access_to,
    built_in_action_perceptions,
    character,
    compose_world,
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


class _Mine:
    """坑道に alice・bob・carol がいる。alice はランプを手に持ち、石を荷に入れている。bob は倒れていて、地面にロープがある。扉と、乗り込めるトロッコ、外への通路がある。"""

    def __init__(
        self,
        lighting: Lighting = Lighting.BRIGHT,
        *,
        object_interactions: tuple[InteractionDeclaration, ...] = (_UNLOCK, _KNOCK),
        person_interactions: tuple[InteractionDeclaration, ...] = (_WAVE,),
    ) -> None:
        self.design = _design(lighting, object_interactions, person_interactions)
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
) -> WorldDesign:
    return compose_world(
        nouns(
            flags=[_KEY_FOUND, _DOOR_OPENED, _LAMP_LIT],
            spots=[_mine(lighting), spot("outside")],
            passages=[_MINE_EXIT],
            objects=[_DOOR],
            item_specs=[_LAMP, _ROCK, _ROPE],
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
        world_rules=replace(world_rules_for_tests(), tend=TendRule(revive_hp_rate=Rate(0.5))),
        built_in_action_perceptions_=built_in_action_perceptions(),
    )


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
        """明るい坑道で alice が一覧を求めると、探す・耳を澄ます・待つ、外への移動、ロープを拾う、ランプと石を置く、石を持つ、ランプをしまう・使う・磨く、bob の介抱、carol へランプと石を渡す、トロッコに乗る、扉を叩く、bob と carol に手を振る、ができるにこの順で並び、扉を開けるができないに並ぶ。"""
        mine = _Mine()
        lamp, rock = mine.lamp(), mine.rock()
        door, cart = mine.design.nouns.object_of(_DOOR.object_id), mine.design.section_access(_CART.section_id)
        outside = mine.design.nouns.spot_of(spot("outside").spot_id)

        actions = mine.lists()

        assert _doable(actions) == [
            SpotSearchAttempt(_ALICE),
            ListeningAttempt(_ALICE),
            WaitAttempt(_ALICE, NoReason()),
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
            ObjectInteractionAttempt(_ALICE, door, _KNOCK, {}, Openly()),
            CarriedItemInteractionAttempt(_ALICE, lamp, _RUB, {}, Openly()),
            PersonInteractionAttempt(_ALICE, _CAROL, _WAVE, {}, Openly()),
            PersonInteractionAttempt(_ALICE, _BOB, _WAVE, {}, Openly()),
        ]
        assert _not_now(actions) == [ObjectInteractionAttempt(_ALICE, door, _UNLOCK, {}, Openly())]

    def test_every_doable_action_goes_through_when_tried(self) -> None:
        """明るい坑道でできるに分けた行為は、1 つずつ新しい坑道で試すと、どれも断られずに通る。"""
        doable = _doable(_Mine().lists())

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
        toward_carol = PersonInteractionAttempt(_ALICE, _CAROL, _HOWL_WITH, {}, Openly())

        actions = mine.lists()
        reply = mine.tries(toward_carol)

        assert [a for a in _doable(actions) if isinstance(a, PersonInteractionAttempt)] == [
            toward_carol,
            PersonInteractionAttempt(_ALICE, _BOB, _HOWL_WITH, {}, Openly()),
        ]
        assert isinstance(reply, ActionRefused)
        assert reply.refusal.text.template.template != _NOT_A_WOLF_TEXT

    def test_interaction_needing_words_is_not_listed(self) -> None:
        """文の引数がある操作 (刻む) は、一覧に出ない。"""
        mine = _Mine(object_interactions=(_CARVE,))

        actions = mine.lists()

        assert [a for a in (x.attempt for x in actions) if isinstance(a, ObjectInteractionAttempt)] == []

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

        assert attempts == [PersonInteractionAttempt(_ALICE, SomeoneInTheDark(), _TAP, {}, Openly())]

    def test_someone_in_the_dark_is_judged_by_common_rules_only(self) -> None:
        """暗がりの誰かへの操作は、行為ごとの前提 (鍵が要る) を満たしていなくてもできるに出る。相手を選ばないので、相手を引くくじも進まない。"""
        listed, untouched = (_Mine(Lighting.DARK, person_interactions=(_GREET_BY_KEY,)) for _ in range(2))

        actions = listed.lists()

        assert [a for a in _doable(actions) if isinstance(a, PersonInteractionAttempt)] == [
            PersonInteractionAttempt(_ALICE, SomeoneInTheDark(), _GREET_BY_KEY, {}, Openly())
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

    def test_person_in_a_section_may_leave_it_but_not_enter_it_again(self) -> None:
        """トロッコに乗っている alice には、トロッコから降りるが出て、乗るは出ない。"""
        mine = _Mine()
        mine.enter_cart()
        cart = mine.design.section_access(_CART.section_id)

        attempts = [action.attempt for action in mine.lists()]

        assert LeaveSectionAttempt(_ALICE, cart) in attempts
        assert EnterSectionAttempt(_ALICE, cart) not in attempts

    def test_busy_person_finds_every_action_not_now_with_the_common_rule_text(self) -> None:
        """行っている最中の alice には、一覧のどの行為もできないに分かれ、理由は共通の決まり Busy の断りの文。"""
        mine = _Mine()
        mine.keep_alice_busy()

        actions = mine.lists()

        assert _doable(actions) == []
        assert {_reason_of(actions, action.attempt) for action in actions} == {"BUSY のためできない。"}
