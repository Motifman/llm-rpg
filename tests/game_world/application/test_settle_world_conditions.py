from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.interact_with_object import InteractWithObject, InteractWithObjectCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.settle_world_conditions import (
    SettleWorldConditions,
    SettleWorldConditionsCommand,
    WorldConditionsDidNotSettleError,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.interaction_attempts import ObjectInteractionAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode
from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.condition.chance_condition import ChanceCondition
from ai_rpg_world.game_world.domain.condition.condition import Condition, NoText
from ai_rpg_world.game_world.domain.condition.connectives import NotCondition
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.settling_occasion import SettlingOccasion
from ai_rpg_world.game_world.domain.condition.subject import EachPerson, NamedPerson
from ai_rpg_world.game_world.domain.declaration.object_and_item import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.ending_declaration import EndingDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import AnnouncementTo, HappeningNotice, NoNotice
from ai_rpg_world.game_world.domain.declaration.verb.joint_action_declaration import JointActionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.combined_effects import ForEveryoneEffect, NoEffect, SequenceEffect
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.flag_effects import LowerFlagEffect, RaiseFlagEffect
from ai_rpg_world.game_world.domain.effect.item_effects import GiveItemEffect
from ai_rpg_world.game_world.domain.objects_and_items import ItemCameIntoWorldEvent
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Notable
from ai_rpg_world.game_world.domain.value_object import Capacity, Count, DescriptionText, FlagId, PersonId, WorldId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.probability import Probability
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.world_progress import WorldEndedEvent
from ai_rpg_world.game_world.domain.world_records import (
    HappeningFiredEvent,
    JointActionCompletedEvent,
    JointActionTimedOutEvent,
    ReactionFiredEvent,
    ScenarioProgress,
)
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.joint_actions_for_tests import PUSH, both_levers, levers_at, pushing
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_design_for_tests import character, compose_world, item_spec, nouns, spot

_WORLD = WorldId("settle_world")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_ROPE = item_spec("rope")
_BELL = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)
_DOOR = FlagDeclaration(FlagId("door_opened"), DescriptionText("扉が開いた"), initially_raised=False)
_BOB_WITH_FULL_PACK = replace(character("bob", "cave"), initial_items=(_ROPE.item_spec_id,), pack_capacity=Capacity(1))
_ROCK_MOVED = FlagDeclaration(FlagId("rock_moved"), DescriptionText("岩が動いた"), initially_raised=False)
_LEVERS = levers_at("cave")
_LEFT, _RIGHT = _LEVERS
_AFTER_TIME = SettleWorldConditionsCommand(SettlingOccasion.AFTER_WORLD_TIME_PASSED)
_AFTER_COMMAND = SettleWorldConditionsCommand(SettlingOccasion.AFTER_COMMAND)


def _raised(flag: FlagDeclaration) -> Condition:
    return FlagIsRaisedCondition(flag=flag, failure_text=NoText())


def _happening(
    name: str,
    condition: Condition,
    effect: Effect,
    *,
    once: bool = False,
    notice: HappeningNotice | NoNotice = NoNotice(),
) -> HappeningDeclaration:
    return HappeningDeclaration(HappeningId(name), condition, effect, once, notice)


def _reaction(
    name: str, condition: Condition, when_true: Effect, when_false: Effect = NoEffect()
) -> ReactionDeclaration:
    return ReactionDeclaration(ReactionId(name), condition, when_true, when_false)


def _announcement_to_everyone_while(condition: Condition) -> AnnouncementTo:
    return AnnouncementTo(PeopleSelection(where=condition), TextWithUnassignedPeople("鐘の音が止んだ"), Notable())


_NEVER_RINGS_ANYTHING = HappeningDeclaration(
    HappeningId("never"),
    NotCondition(AlwaysHolds(), NoText()),
    SequenceEffect((RaiseFlagEffect(_BELL), RaiseFlagEffect(_DOOR))),
    False,
    NoNotice(),
)


class _SettledWorld:
    def __init__(
        self,
        *,
        happenings: tuple[HappeningDeclaration, ...] = (),
        reactions: tuple[ReactionDeclaration, ...] = (),
        joint_actions: tuple[JointActionDeclaration, ...] = (),
        ends_when: Condition | None = None,
        bob_pack_full: bool = False,
        declares_never_firing_happening: bool = True,
    ) -> None:
        bob = _BOB_WITH_FULL_PACK if bob_pack_full else character("bob", "cave")
        never_firing = (_NEVER_RINGS_ANYTHING,) if declares_never_firing_happening else ()
        design = compose_world(
            nouns(
                flags=[_BELL, _DOOR, _ROCK_MOVED],
                spots=[spot("cave")],
                objects=_LEVERS,
                characters=[character("alice", "cave"), bob],
                item_specs=[_ROPE],
            ),
            object_interactions=pushing(_LEVERS, precondition=NotCondition(_raised(_DOOR), TextWithUnassignedPeople("扉が開いている。"))),
            happenings=(*happenings, *never_firing),
            reactions=reactions,
            joint_actions=joint_actions,
            ending=EndingDeclaration(
                ends_when=ends_when if ends_when is not None else NotCondition(AlwaysHolds(), NoText())
            ),
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="settle.yaml",
            scenario_hash="hash",
            design=design,
            random=SeedableRandomSource(1),
        )
        OpenWorld(self.store)(OpenWorldCommand(_WORLD, design))
        self._design = design
        self.events: list[DomainEvent] = []
        distributor = CommittedEventsDistributor()
        distributor.register_receiver(self)
        self.scope = CommandScope(self.store, distributor)
        self.settle = SettleWorldConditions(self.scope, design)
        self._carry_out = CarryOutAction(self.scope, design)

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.events.extend(events)

    def pass_time(self) -> None:
        self.scope.run(lambda session: session.clock().advance(self._design.day_night))

    def push(self, person: PersonId, lever: ObjectDeclaration) -> ActionReply:
        interaction = self._design.interaction_on_object(lever.object_id, PUSH)
        attempt = ObjectInteractionAttempt(person, lever, interaction, {}, Openly())
        return InteractWithObject(self._carry_out, self._design)(InteractWithObjectCommand(attempt))

    def raise_flag(self, flag: FlagDeclaration) -> None:
        self.scope.run(
            lambda session: session.aggregates().flags().raise_flag(flag, WorldTimePassing(session.clock().now()))
        )

    def lower_flag(self, flag: FlagDeclaration) -> None:
        self.scope.run(
            lambda session: session.aggregates().flags().lower_flag(flag, WorldTimePassing(session.clock().now()))
        )

    def read(self, flag: FlagDeclaration) -> bool:
        return self.scope.run(lambda session: session.facts().flags().is_raised(flag))

    def items_carried_by(self, person: PersonId) -> int:
        def count(session: WorldSession) -> int:
            return len(session.facts().inventory(person).memento().packed)

        return self.scope.run(count)

    def fired_happenings(self) -> list[HappeningFiredEvent]:
        return [event for event in self.events if isinstance(event, HappeningFiredEvent)]

    def fired_reactions(self) -> list[ReactionFiredEvent]:
        return [event for event in self.events if isinstance(event, ReactionFiredEvent)]

    def settled_joint_actions(self) -> list[JointActionCompletedEvent | JointActionTimedOutEvent]:
        return [event for event in self.events if isinstance(event, (JointActionCompletedEvent, JointActionTimedOutEvent))]


class TestSettleWorldConditionsHappenings:
    """SettleWorldConditions が、条件が真の出来事を 1 tick に 1 回だけ、落ち着くまで続けて発火することを保証する。"""

    def test_true_happening_fires_once_per_tick(self) -> None:
        """条件が常に真の鐘の出来事は、同じ tick に 2 度落ち着かせても 1 回だけ発火し、次の tick にもう 1 回発火する。"""
        world = _SettledWorld(happenings=(_happening("bell", AlwaysHolds(), RaiseFlagEffect(_BELL)),))

        world.settle(_AFTER_TIME)
        world.settle(_AFTER_COMMAND)
        world.pass_time()
        world.settle(_AFTER_TIME)

        assert [event.happening_id for event in world.fired_happenings()] == [HappeningId("bell")] * 2
        assert world.read(_BELL) is True

    def test_happening_made_true_by_another_firing_fires_in_the_same_settling(self) -> None:
        """鐘が鳴ったら扉が開く出来事を先に宣言しても、同じ回で鐘が鳴ったあとに続けて発火し、扉が開く。"""
        world = _SettledWorld(
            happenings=(
                _happening("door", _raised(_BELL), RaiseFlagEffect(_DOOR)),
                _happening("bell", AlwaysHolds(), RaiseFlagEffect(_BELL)),
            )
        )

        world.settle(_AFTER_TIME)

        assert [event.happening_id for event in world.fired_happenings()] == [HappeningId("bell"), HappeningId("door")]
        assert world.read(_DOOR) is True

    def test_happenings_true_in_the_same_state_all_fire_even_if_an_earlier_one_falsifies_another(self) -> None:
        """鐘が鳴っていれば鐘を止める出来事と、鐘が鳴っていれば扉を開く出来事は、同じ世界の状態で確かめるので、先の出来事が鐘を止めても両方が発火する。"""
        world = _SettledWorld(
            happenings=(
                _happening("silence", _raised(_BELL), LowerFlagEffect(_BELL)),
                _happening("door", _raised(_BELL), RaiseFlagEffect(_DOOR)),
            )
        )
        world.raise_flag(_BELL)

        world.settle(_AFTER_TIME)

        assert [event.happening_id for event in world.fired_happenings()] == [
            HappeningId("silence"),
            HappeningId("door"),
        ]
        assert world.read(_DOOR) is True

    def test_happening_whose_condition_is_false_does_not_fire(self) -> None:
        """鐘が鳴っていなければ、鐘が鳴ったら扉を開く出来事は発火せず、扉は閉じたまま。"""
        world = _SettledWorld(happenings=(_happening("door", _raised(_BELL), RaiseFlagEffect(_DOOR)),))

        world.settle(_AFTER_TIME)

        assert world.fired_happenings() == []
        assert world.read(_DOOR) is False


class TestSettleWorldConditionsChance:
    """SettleWorldConditions が、偶然を使う条件を時間を進めたときだけ確かめることを保証する (D2。くじを 1 tick に何度も引かないため)。"""

    def test_chance_happening_is_not_checked_after_a_command(self) -> None:
        """必ず当たる偶然の出来事は、コマンドの後に落ち着かせても発火せず、時間を進めた後に落ち着かせると発火する。"""
        world = _SettledWorld(
            happenings=(_happening("gust", ChanceCondition(Probability(1.0), NoText()), RaiseFlagEffect(_BELL)),)
        )

        world.settle(_AFTER_COMMAND)
        fired_after_command = list(world.fired_happenings())
        world.settle(_AFTER_TIME)

        assert fired_after_command == []
        assert [event.happening_id for event in world.fired_happenings()] == [HappeningId("gust")]

    def test_chance_reaction_is_not_checked_after_a_command(self) -> None:
        """必ず当たる偶然の反応は、コマンドの後には確かめないので真偽を記録せず、時間を進めた後に初めて真を記録する。"""
        world = _SettledWorld(
            reactions=(_reaction("draft", ChanceCondition(Probability(1.0), NoText()), RaiseFlagEffect(_BELL)),)
        )

        world.settle(_AFTER_COMMAND)
        noted_after_command = world.scope.run(lambda session: session.scenario_progress().memento().reaction_truths)
        world.settle(_AFTER_TIME)
        noted_after_time = world.scope.run(lambda session: session.scenario_progress().memento().reaction_truths)

        assert noted_after_command == frozenset()
        assert [noted.truth for noted in noted_after_time] == [True]


class TestSettleWorldConditionsReactions:
    """SettleWorldConditions が、反応を真偽が変わったときだけ、1 回の落ち着かせに 1 回まで発火することを保証する。"""

    def test_reaction_fires_only_when_its_truth_changes(self) -> None:
        """最初に確かめたときは偽を記録するだけで発火せず、鐘が鳴って真になったら 1 回発火して扉を開き、真のままなら発火しない。"""
        world = _SettledWorld(reactions=(_reaction("door", _raised(_BELL), RaiseFlagEffect(_DOOR)),))

        world.settle(_AFTER_TIME)
        fired_at_first = list(world.fired_reactions())
        world.raise_flag(_BELL)
        world.settle(_AFTER_COMMAND)
        world.settle(_AFTER_COMMAND)

        assert fired_at_first == []
        assert [(event.reaction_id, event.became) for event in world.fired_reactions()] == [(ReactionId("door"), True)]
        assert world.read(_DOOR) is True

    def test_reaction_that_undoes_its_own_condition_fires_once_per_settling(self) -> None:
        """鐘が鳴ったら止め、止んだら鳴らす反応は、1 回の落ち着かせでは 1 回だけ発火して止まり、次の落ち着かせで逆向きに 1 回発火する。"""
        world = _SettledWorld(
            reactions=(_reaction("echo", _raised(_BELL), LowerFlagEffect(_BELL), RaiseFlagEffect(_BELL)),)
        )
        world.settle(_AFTER_TIME)
        world.raise_flag(_BELL)

        world.settle(_AFTER_COMMAND)
        after_first = [event.became for event in world.fired_reactions()]
        world.settle(_AFTER_COMMAND)

        assert after_first == [True]
        assert [event.became for event in world.fired_reactions()] == [True, False]
        assert world.read(_BELL) is True


class TestSettleWorldConditionsRefusal:
    """SettleWorldConditions が、集約が断った発火だけを巻き戻し、「その回は起きた」と断った理由を記録することを保証する (E2)。"""

    def test_refused_happening_leaves_no_change_and_is_noted_with_its_reason(self) -> None:
        """鐘を鳴らしてから荷が満杯の bob に縄を渡す出来事は、鐘も bob の荷も変えず、品物も増やさず、断った理由を載せた発火として記録される。"""
        world = _SettledWorld(
            happenings=(
                _happening(
                    "reward",
                    AlwaysHolds(),
                    SequenceEffect(
                        (RaiseFlagEffect(_BELL), GiveItemEffect(NamedPerson(_BOB_WITH_FULL_PACK), _ROPE, Count(1)))
                    ),
                    notice=_announcement_to_everyone_while(AlwaysHolds()),
                ),
            ),
            bob_pack_full=True,
        )

        world.settle(_AFTER_TIME)

        [fired] = world.fired_happenings()
        assert fired.refusal == RefusalCode("GAME_WORLD.INVENTORY_FULL")
        assert fired.audience == frozenset()
        assert world.read(_BELL) is False
        assert world.items_carried_by(_BOB) == 1
        assert not any(isinstance(event, ItemCameIntoWorldEvent) for event in world.events)

    def test_refused_once_happening_never_fires_again(self) -> None:
        """荷が満杯の bob に縄を渡す once の出来事は、断られたあと、次の tick に落ち着かせても試し直さない。"""
        world = _SettledWorld(
            happenings=(
                _happening(
                    "reward",
                    AlwaysHolds(),
                    GiveItemEffect(NamedPerson(_BOB_WITH_FULL_PACK), _ROPE, Count(1)),
                    once=True,
                ),
            ),
            bob_pack_full=True,
        )

        world.settle(_AFTER_TIME)
        world.pass_time()
        world.settle(_AFTER_TIME)

        assert len(world.fired_happenings()) == 1

    def test_refused_reaction_keeps_no_change_and_notes_its_new_truth(self) -> None:
        """鐘が鳴ったら荷が満杯の bob に縄を渡す反応は、断られても真になったと記録して理由を載せ、同じ真のままなら試し直さない。"""
        world = _SettledWorld(
            reactions=(
                _reaction("reward", _raised(_BELL), GiveItemEffect(NamedPerson(_BOB_WITH_FULL_PACK), _ROPE, Count(1))),
            ),
            bob_pack_full=True,
        )
        world.settle(_AFTER_TIME)
        world.raise_flag(_BELL)

        world.settle(_AFTER_COMMAND)
        world.settle(_AFTER_COMMAND)

        assert [(event.became, event.refusal) for event in world.fired_reactions()] == [
            (True, RefusalCode("GAME_WORLD.INVENTORY_FULL"))
        ]
        assert world.items_carried_by(_BOB) == 1

    def test_for_everyone_gives_to_the_others_when_one_pack_is_full(self) -> None:
        """全員に縄を 1 本渡す出来事は、bob の荷が満杯でも alice には渡り、bob の荷は変わらず、発火は断られなかったと記録される (E3)。"""
        world = _SettledWorld(
            happenings=(
                _happening(
                    "supply",
                    AlwaysHolds(),
                    ForEveryoneEffect(
                        PeopleSelection(where=AlwaysHolds()), GiveItemEffect(EachPerson(), _ROPE, Count(1))
                    ),
                ),
            ),
            bob_pack_full=True,
        )

        world.settle(_AFTER_TIME)

        [fired] = world.fired_happenings()
        assert fired.refusal == NoRefusal()
        assert world.items_carried_by(_ALICE) == 1
        assert world.items_carried_by(_BOB) == 1


class TestSettleWorldConditionsNotice:
    """SettleWorldConditions が、出来事の知らせの相手を、その出来事の効果を当てる前の世界で選ぶことを保証する。"""

    def test_audience_is_chosen_before_the_effect(self) -> None:
        """鐘が鳴っている人に「鐘の音が止んだ」と知らせて鐘を止める出来事は、止める前に選んだ alice と bob を相手に載せる。"""
        world = _SettledWorld(
            happenings=(
                _happening(
                    "silence",
                    _raised(_BELL),
                    LowerFlagEffect(_BELL),
                    notice=_announcement_to_everyone_while(_raised(_BELL)),
                ),
            )
        )
        world.raise_flag(_BELL)

        world.settle(_AFTER_TIME)

        [fired] = world.fired_happenings()
        assert fired.audience == frozenset({_ALICE, _BOB})


class TestSettleWorldConditionsEnding:
    """SettleWorldConditions が、落ち着いたあとに終わりの条件を確かめ、真なら世界を終わらせることを保証する。"""

    def test_world_ends_after_happenings_settle_when_ending_condition_holds(self) -> None:
        """鐘が鳴ったら終わる世界で、鐘を鳴らす出来事が発火すると、その発火のあとに WorldEndedEvent が出る。"""
        world = _SettledWorld(
            happenings=(_happening("bell", AlwaysHolds(), RaiseFlagEffect(_BELL)),), ends_when=_raised(_BELL)
        )

        world.settle(_AFTER_TIME)

        assert [type(event) for event in world.events if not isinstance(event, ReactionFiredEvent)][-2:] == [
            HappeningFiredEvent,
            WorldEndedEvent,
        ]

    def test_world_does_not_end_while_ending_condition_is_false(self) -> None:
        """鐘が鳴ったら終わる世界で、鐘が鳴っていなければ WorldEndedEvent は出ない。"""
        world = _SettledWorld(ends_when=_raised(_BELL))

        world.settle(_AFTER_TIME)

        assert not any(isinstance(event, WorldEndedEvent) for event in world.events)

    def test_ended_world_is_not_ended_twice(self) -> None:
        """終わった世界をもう一度落ち着かせても、断られずに済み、WorldEndedEvent は 1 つのまま。"""
        world = _SettledWorld(ends_when=AlwaysHolds())

        world.settle(_AFTER_TIME)
        world.settle(_AFTER_COMMAND)

        assert [type(event) for event in world.events].count(WorldEndedEvent) == 1


class TestSettleWorldConditionsRoundLimit:
    """SettleWorldConditions が、宣言の数 (出来事 + 反応 + 二人で合わせる操作) + 1 回を超えて回ったら、コードの誤りとして止まることを保証する。"""

    def test_settling_that_never_ends_stops_and_leaves_no_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """帳簿が「同じ tick にもう一度起きてよい」と答え続ける誤りがあると、常に真の鐘の出来事で落ち着かせると WorldConditionsDidNotSettleError を投げ、鐘は鳴らず、断りとしても数えない。"""
        world = _SettledWorld(happenings=(_happening("bell", AlwaysHolds(), RaiseFlagEffect(_BELL)),))
        monkeypatch.setattr(ScenarioProgress, "may_fire", lambda self, happening, now: True)

        with pytest.raises(WorldConditionsDidNotSettleError):
            world.settle(_AFTER_TIME)

        assert world.read(_BELL) is False
        assert world.fired_happenings() == []
        assert world.scope.refusals == {}


def _everyone_hears(text: str) -> AnnouncementTo:
    return AnnouncementTo(PeopleSelection(where=AlwaysHolds()), TextWithUnassignedPeople(text), Notable())


class TestSettleWorldConditionsJointActions:
    """SettleWorldConditions が、行為で埋まった二人で合わせる操作を、揃えば on_complete、窓を過ぎれば on_timeout で 1 回だけ発火することを保証する。"""

    def test_two_people_on_both_levers_apply_on_complete_once(self) -> None:
        """alice が左、窓の中で bob が右の梃子を押すと、同じ tick に 2 度落ち着かせても揃いは 1 回だけ発火し、岩が動く。"""
        world = _SettledWorld(joint_actions=(both_levers(_LEVERS, on_complete=RaiseFlagEffect(_ROCK_MOVED)),))
        world.push(_ALICE, _LEFT)
        world.push(_BOB, _RIGHT)

        world.settle(_AFTER_COMMAND)
        world.settle(_AFTER_COMMAND)

        assert [type(event) for event in world.settled_joint_actions()] == [JointActionCompletedEvent]
        assert world.read(_ROCK_MOVED) is True

    def test_completion_is_told_to_the_audience_of_its_notice(self) -> None:
        """揃いの知らせが全員宛てなら、揃ったイベントの相手は alice と bob になる。"""
        world = _SettledWorld(joint_actions=(both_levers(_LEVERS, complete_notice=_everyone_hears("岩が動いた")),))
        world.push(_ALICE, _LEFT)
        world.push(_BOB, _RIGHT)

        world.settle(_AFTER_COMMAND)

        [completed] = world.settled_joint_actions()
        assert completed.audience == frozenset({_ALICE, _BOB})

    def test_one_lever_left_past_the_window_applies_on_timeout_once(self) -> None:
        """alice が tick 0 に左を押しただけで窓 2 tick を過ぎると、tick 3 に 2 度落ち着かせても時間切れは 1 回だけ発火し、鐘が鳴り、岩は動かない。"""
        world = _SettledWorld(
            joint_actions=(
                both_levers(_LEVERS, on_complete=RaiseFlagEffect(_ROCK_MOVED), on_timeout=RaiseFlagEffect(_BELL)),
            )
        )
        world.push(_ALICE, _LEFT)
        for _ in range(3):
            world.pass_time()
            world.settle(_AFTER_TIME)

        world.settle(_AFTER_COMMAND)

        assert [type(event) for event in world.settled_joint_actions()] == [JointActionTimedOutEvent]
        assert (world.read(_BELL), world.read(_ROCK_MOVED)) == (True, False)

    def test_refused_completion_leaves_no_change_and_is_noted_with_its_reason(self) -> None:
        """岩を動かしてから荷が満杯の bob に縄を渡す揃いの効果は、岩も bob の荷も変えず、断った理由を載せ、相手の無い揃いとして記録される。"""
        world = _SettledWorld(
            joint_actions=(
                both_levers(
                    _LEVERS,
                    on_complete=SequenceEffect(
                        (RaiseFlagEffect(_ROCK_MOVED), GiveItemEffect(NamedPerson(_BOB_WITH_FULL_PACK), _ROPE, Count(1)))
                    ),
                    complete_notice=_everyone_hears("岩が動いた"),
                ),
            ),
            bob_pack_full=True,
        )
        world.push(_ALICE, _LEFT)
        world.push(_BOB, _RIGHT)

        world.settle(_AFTER_COMMAND)

        [completed] = world.settled_joint_actions()
        assert (completed.refusal, completed.audience) == (RefusalCode("GAME_WORLD.INVENTORY_FULL"), frozenset())
        assert world.read(_ROCK_MOVED) is False
        assert world.items_carried_by(_BOB) == 1

    def test_refused_push_is_not_a_part(self) -> None:
        """扉が開いていて alice の左の梃子が断られると、bob が右を押しても揃わず、岩は動かない。"""
        world = _SettledWorld(joint_actions=(both_levers(_LEVERS, on_complete=RaiseFlagEffect(_ROCK_MOVED)),))
        world.raise_flag(_DOOR)
        world.push(_ALICE, _LEFT)
        world.lower_flag(_DOOR)
        world.push(_BOB, _RIGHT)

        world.settle(_AFTER_COMMAND)

        assert world.settled_joint_actions() == []
        assert world.read(_ROCK_MOVED) is False

    def test_happening_set_off_by_a_completion_fires_in_the_same_settling(self) -> None:
        """揃うと鐘が鳴り、鐘が鳴ったら扉が開く出来事だけの世界でも、上限で止まらずに同じ回で扉まで開く。"""
        world = _SettledWorld(
            happenings=(_happening("door", _raised(_BELL), RaiseFlagEffect(_DOOR)),),
            joint_actions=(both_levers(_LEVERS, on_complete=RaiseFlagEffect(_BELL)),),
            declares_never_firing_happening=False,
        )
        world.push(_ALICE, _LEFT)
        world.push(_BOB, _RIGHT)

        world.settle(_AFTER_COMMAND)

        assert world.read(_DOOR) is True
