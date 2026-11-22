from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.check_readiness_to_act import (
    CheckReadinessToAct,
    CheckReadinessToActCommand,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.person import Died
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import Damage, PersonId
from ai_rpg_world.game_world.domain.value_object.readiness_to_act import FreeToAct, InTheMiddleOfAction, UnableToAct
from tests.game_world.application.action.world_for_action_tests import ALICE, BOB, SHAFT, WorldForActions
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests


def _readiness(world: WorldForActions, person: PersonId) -> object:
    return CheckReadinessToAct(world.scope)(CheckReadinessToActCommand(people=(person,)))[person]


def _fall(world: WorldForActions, person: PersonId) -> None:
    world.scope.run(
        lambda session: (
            session.aggregates().vitals(person).take_damage(Damage(999), session.facts().now(), WorldHappening())
        )
    )


def _die(world: WorldForActions, person: PersonId) -> None:
    def die(session: WorldSession) -> None:
        facts = session.facts()
        vitals = session.aggregates().vitals(person)
        vitals.take_damage(Damage(999), facts.now(), WorldHappening())
        vitals.pass_time(facts.now() + facts.rules().death.grace, facts.rules().death, facts.rules().hunger)

    world.scope.run(die)


class TestCheckReadinessToAct:
    """CheckReadinessToAct が、人ごとに、いま行為を始められるか・行っている最中か・動けないかを答えることを保証する。"""

    def test_person_with_nothing_going_on_is_free_to_act(self) -> None:
        """何もしていない生きた人は FreeToAct と答える。"""
        world = WorldForActions()

        assert _readiness(world, ALICE) == FreeToAct()

    def test_person_travelling_is_in_the_middle_of_action(self) -> None:
        """3 tick かかる梯子を降り始めた人は、着くまで InTheMiddleOfAction と答える。"""
        world = WorldForActions()
        world.travel(ALICE, SHAFT)

        assert _readiness(world, ALICE) == InTheMiddleOfAction()

    def test_person_becomes_free_again_once_the_action_is_over(self) -> None:
        """梯子を降り始めた人も、3 tick 経てば FreeToAct に戻る。"""
        world = WorldForActions()
        world.travel(ALICE, SHAFT)
        world.pass_ticks(3)

        assert _readiness(world, ALICE) == FreeToAct()

    def test_fallen_person_is_unable_to_act(self) -> None:
        """気を失った人は UnableToAct と答える。"""
        world = WorldForActions()
        _fall(world, ALICE)

        assert _readiness(world, ALICE) == UnableToAct()

    def test_dead_person_is_unable_to_act(self) -> None:
        """死んだ人は UnableToAct と答える。"""
        world = WorldForActions()
        _die(world, ALICE)

        assert _readiness(world, ALICE) == UnableToAct()

    def test_dead_person_is_unable_to_act_even_where_the_departed_act(self) -> None:
        """死者が動ける設定 (departed_persons_act) の世界でも、死んだ人は UnableToAct と答える。"""
        world = WorldForActions(rules=replace(world_rules_for_tests(), departed_persons_act=True))
        _die(world, ALICE)

        assert _readiness(world, ALICE) == UnableToAct()

    def test_person_whose_outcome_is_decided_is_unable_to_act(self) -> None:
        """体が生きていても、結末が決まった人は UnableToAct と答える。"""
        world = WorldForActions()
        world.scope.run(lambda session: session.aggregates().outcomes().decide(ALICE, Died(), session.facts().now()))

        assert _readiness(world, ALICE) == UnableToAct()

    def test_answers_each_person_asked_about(self) -> None:
        """2 人について問うと、2 人それぞれの答えが返り、片方が動けなくても他方は変わらない。"""
        world = WorldForActions()
        _fall(world, BOB)

        readiness = CheckReadinessToAct(world.scope)(CheckReadinessToActCommand(people=(ALICE, BOB)))

        assert readiness == {ALICE: FreeToAct(), BOB: UnableToAct()}
