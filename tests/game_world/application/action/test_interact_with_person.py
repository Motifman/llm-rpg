from __future__ import annotations

from ai_rpg_world.being.contract import TextWithPeople
from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.application.stimulus_translator import StimulusTranslator
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_refusal import PreconditionRefusal, WorldStateRefusal
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NoOneFoundInTheDark
from ai_rpg_world.game_world.domain.action.interaction_attempts import PersonInteractionAttempt, SomeoneInTheDark
from ai_rpg_world.game_world.domain.perception import NoTarget, SightStimulus
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.world_records import ActionAttemptFailedEvent, PersonActedEvent
from tests.game_world.application.action.world_for_interaction_tests import (
    ALICE,
    BOB,
    CAROL,
    PUSH_IN_THE_DARK,
    TAKE_KEY_IN_THE_DARK,
    WorldForInteractions,
)
from tests.game_world.support.facts_not_read import FACTS_NOT_READ

_FULL_HP = 100


def _damaged(world: WorldForInteractions, people: tuple[PersonId, ...]) -> list[PersonId]:
    session = world.read()
    facts = session.facts()
    damaged = [person for person in people if facts.vitals(person).hp().current < _FULL_HP]
    session.roll_back()
    return damaged


def _acted_targets(world: WorldForInteractions) -> list[PersonId | SomeoneInTheDark]:
    return [
        event.attempt.target
        for event in world.events_received
        if isinstance(event, PersonActedEvent) and isinstance(event.attempt, PersonInteractionAttempt)
    ]


def _failed_targets(world: WorldForInteractions) -> list[PersonId | SomeoneInTheDark]:
    return [
        event.refusal.attempt.target
        for event in world.events_received
        if isinstance(event, ActionAttemptFailedEvent) and isinstance(event.refusal.attempt, PersonInteractionAttempt)
    ]


class TestInteractWithNamedPerson:
    """InteractWithPerson が、名指しした相手に人への操作の宣言の効果を起こすことを保証する。"""

    def test_effect_on_target_reaches_named_person(self) -> None:
        """bob の肩を叩くと ActionDone が返り、相手 (Target) への効果のとおり bob だけが傷つく。"""
        world = WorldForInteractions(carol_at="dam")

        reply = world.tap(ALICE, BOB)

        assert isinstance(reply, ActionDone)
        assert _damaged(world, (ALICE, BOB, CAROL)) == [BOB]


class TestInteractWithSomeoneInTheDark:
    """InteractWithPerson が、暗がりの誰かに向けた操作の相手を世界がその場から選び、選んだ相手を効果とイベントに使うことを保証する。"""

    def test_only_person_together_is_chosen_and_carried_by_event(self) -> None:
        """一緒にいるのが bob だけのとき、暗がりの誰かの肩を叩くと bob が傷つき、PersonActedEvent の試みの相手は bob になる。"""
        world = WorldForInteractions()

        reply = world.tap(ALICE, SomeoneInTheDark())

        assert isinstance(reply, ActionDone)
        assert _damaged(world, (ALICE, BOB, CAROL)) == [BOB]
        assert _acted_targets(world) == [BOB]

    def test_done_reply_carries_the_attempt_with_the_chosen_target(self) -> None:
        """一緒にいるのが bob だけのとき、暗がりの誰かの肩を叩くと、返事の ActionDone の試みの相手は bob になっている。"""
        world = WorldForInteractions()

        reply = world.tap(ALICE, SomeoneInTheDark())

        assert isinstance(reply, ActionDone)
        assert isinstance(reply.attempt, PersonInteractionAttempt)
        assert reply.attempt.target == BOB

    def test_event_of_chosen_target_is_translated_into_target_stimulus(self) -> None:
        """相手への文を宣言した操作を暗がりの誰かに行うと、PersonActedEvent から選んだ bob に向けた見える刺激が作れる。"""
        world = WorldForInteractions()
        world.tap(ALICE, SomeoneInTheDark())
        acted = [event for event in world.events_received if isinstance(event, PersonActedEvent)]

        stimuli = StimulusTranslator().stimuli_of(acted[0], world.design, FACTS_NOT_READ)

        sights = [stimulus for stimulus in stimuli if isinstance(stimulus, SightStimulus)]
        assert [sight.involved for sight in sights] == [(ALICE, BOB)]
        assert not isinstance(sights[0].target, NoTarget)

    def test_one_of_several_people_together_is_chosen(self) -> None:
        """bob と carol が一緒にいるとき、相手はそのどちらか 1 人に決まり、傷つくのもイベントの相手もその人だけになる。"""
        world = WorldForInteractions(carol_at="dam")

        world.tap(ALICE, SomeoneInTheDark())

        damaged = _damaged(world, (ALICE, BOB, CAROL))
        assert len(damaged) == 1
        assert damaged[0] in (BOB, CAROL)
        assert _acted_targets(world) == damaged

    def test_dead_person_is_not_chosen(self) -> None:
        """一緒にいる bob が死んでいて carol だけが生きているとき、相手は carol に決まる。"""
        world = WorldForInteractions(carol_at="dam")
        world.let_die(BOB)

        world.tap(ALICE, SomeoneInTheDark())

        assert _acted_targets(world) == [CAROL]

    def test_no_one_together_is_refused_with_common_rule(self) -> None:
        """一緒にいる人が誰もいないと共通の規則 NoOneFoundInTheDark で断られ、ActionAttemptFailedEvent が残り、誰も傷つかない。"""
        world = WorldForInteractions(bob_at="shore")

        reply = world.tap(ALICE, SomeoneInTheDark())

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == NoOneFoundInTheDark()
        assert any(isinstance(event, ActionAttemptFailedEvent) for event in world.events_received)
        assert _damaged(world, (ALICE, BOB, CAROL)) == []

    def test_refused_by_precondition_failed_event_carries_chosen_target(self) -> None:
        """暗がりの誰かへの操作が前提で断られたとき、ActionAttemptFailedEvent の試みの相手は選んだ bob になる。"""
        world = WorldForInteractions()

        reply = world.tap(ALICE, SomeoneInTheDark(), PUSH_IN_THE_DARK)

        assert isinstance(reply, ActionRefused)
        assert isinstance(reply.refusal.reason, PreconditionRefusal)
        assert _failed_targets(world) == [BOB]

    def test_refused_by_aggregate_failed_event_carries_chosen_target(self) -> None:
        """暗がりの誰かの鍵を取る効果が集約に断られたとき、ActionAttemptFailedEvent の試みの相手は選んだ bob になる。"""
        world = WorldForInteractions()

        reply = world.tap(ALICE, SomeoneInTheDark(), TAKE_KEY_IN_THE_DARK)

        assert isinstance(reply, ActionRefused)
        assert isinstance(reply.refusal.reason, WorldStateRefusal)
        assert _failed_targets(world) == [BOB]

    def test_refusal_before_anyone_is_chosen_is_summarized_without_a_name(self) -> None:
        """一緒にいる人が誰もいないまま暗がりの誰かの肩を叩いて断られると、要約は相手の名前の無い、暗がりの相手の行の文になる。"""
        world = WorldForInteractions(bob_at="shore")

        reply = world.tap(ALICE, SomeoneInTheDark())

        assert isinstance(reply, ActionRefused)
        summary = _summary_for(world, reply, ALICE)
        assert isinstance(summary, TextWithPeople)
        assert summary.template == "interact_with_someone_in_the_darkした tap_shoulder"


def _summary_for(world: WorldForInteractions, reply: ActionRefused, actor: PersonId) -> object:
    def read(session: WorldSession) -> object:
        facts = session.facts()
        return reply.summary_for_actor(world.design, facts, WorldPerceptionSenses(facts).view_for(actor))

    return world.scope.run(read)
