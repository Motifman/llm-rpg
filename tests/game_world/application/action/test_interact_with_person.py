from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NoOneFoundInTheDark
from ai_rpg_world.game_world.domain.action.interaction_attempts import PersonInteractionAttempt, SomeoneInTheDark
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.world_records import ActionAttemptFailedEvent, PersonActedEvent
from tests.game_world.application.action.world_for_interaction_tests import (
    ALICE,
    BOB,
    CAROL,
    WorldForInteractions,
)

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


class TestInteractWithNamedPerson:
    """InteractWithPerson が、名指しした相手に人への操作の宣言の効果を起こすことを保証する。"""

    def test_effect_on_target_reaches_named_person(self) -> None:
        """bob の肩を叩くと ActionDone が返り、相手 (Target) への効果のとおり bob だけが傷つく。"""
        world = WorldForInteractions(carol_at="dam")

        reply = world.tap(ALICE, BOB)

        assert reply == ActionDone()
        assert _damaged(world, (ALICE, BOB, CAROL)) == [BOB]


class TestInteractWithSomeoneInTheDark:
    """InteractWithPerson が、暗がりの誰かに向けた操作の相手を世界がその場から選び、選んだ相手を効果とイベントに使うことを保証する。"""

    def test_only_person_together_is_chosen_and_carried_by_event(self) -> None:
        """一緒にいるのが bob だけのとき、暗がりの誰かの肩を叩くと bob が傷つき、PersonActedEvent の試みの相手は bob になる。"""
        world = WorldForInteractions()

        reply = world.tap(ALICE, SomeoneInTheDark())

        assert reply == ActionDone()
        assert _damaged(world, (ALICE, BOB, CAROL)) == [BOB]
        assert _acted_targets(world) == [BOB]

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
