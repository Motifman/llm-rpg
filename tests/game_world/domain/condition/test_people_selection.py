from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.condition.condition import Condition, FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Actor, EachPerson, SubjectKind
from ai_rpg_world.game_world.domain.person import PersonVitals, WorldHappening
from ai_rpg_world.game_world.domain.value_object import Damage, HitPoints, PersonId, WorldId, WorldTick
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.world_in_memory import WorldInMemory

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts

_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")


@dataclass(frozen=True)
class _IsNotTheActor(Condition):
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return EachPerson().person_in(trigger) != Actor().person_in(trigger)

    def requirements(self) -> Requirements:
        return Actor().requirements().combined_with(EachPerson().requirements())

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        return None

    def explains_failure(self) -> bool:
        return False


@dataclass(frozen=True)
class _CanAct(Condition):
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.vitals(EachPerson().person_in(trigger)).can_act()

    def requirements(self) -> Requirements:
        return EachPerson().requirements()

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        return None

    def explains_failure(self) -> bool:
        return False


def _world() -> WorldInMemory:
    return WorldInMemory(
        world=WorldId("island"),
        people=(_ALICE, _BOB, _CAROL),
        vitals=tuple(PersonVitals.start(p, HitPoints(current=3, maximum=3)) for p in (_ALICE, _BOB, _CAROL)),
    )


class TestSelect:
    """PeopleSelection.select が、世界の全員を 1 人ずつ「その人」として where に尋ね、真になった人を選ぶことを保証する。"""

    def test_outer_trigger_is_kept_while_looking_at_each_person(self) -> None:
        """alice の行為の中で「行為をした人ではない人」を選ぶと、bob と carol が選ばれる。"""
        world = _world()

        selected = PeopleSelection(where=_IsNotTheActor()).select(world.facts(), ActionAttemptForTests(_ALICE))

        assert selected == frozenset({_BOB, _CAROL})

    def test_where_reads_the_world(self) -> None:
        """bob が倒れた世界で、時間の経過をきっかけに「動ける人」を選ぶと、alice と carol が選ばれる。"""
        world = _world()
        world.aggregates().vitals(_BOB).take_damage(Damage(3), WorldTick(0), WorldHappening())

        selected = PeopleSelection(where=_CanAct()).select(world.facts(), WorldTimePassing(WorldTick(0)))

        assert selected == frozenset({_ALICE, _CAROL})

    def test_no_one_matching_selects_no_one(self) -> None:
        """全員が倒れた世界で「動ける人」を選ぶと、誰も選ばれない。"""
        world = _world()
        for person in (_ALICE, _BOB, _CAROL):
            world.aggregates().vitals(person).take_damage(Damage(3), WorldTick(0), WorldHappening())

        selected = PeopleSelection(where=_CanAct()).select(world.facts(), WorldTimePassing(WorldTick(0)))

        assert selected == frozenset()


class TestRequirements:
    """PeopleSelection.requirements が、where の要求から中だけで使える EACH_PERSON を外して外へ出すことを保証する。"""

    def test_each_person_is_not_required_outside(self) -> None:
        """where が行為の人と「その人」を要るとき、選ぶことの要求は行為の人だけ。"""
        requirements = PeopleSelection(where=_IsNotTheActor()).requirements()

        assert requirements.subjects == frozenset({SubjectKind.ACTOR})
