from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.person_conditions import IsAtSpotCondition
from ai_rpg_world.game_world.domain.condition.subject import EachPerson
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayPhaseDeclaration, TimeOfDay
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_name import DayPhaseName
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import AnnouncementStimulus, Background
from ai_rpg_world.game_world.domain.person import DeclaredOutcome, PersonVitals
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DisplayName,
    HitPoints,
    OutcomeId,
    PersonId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, PersonBody, Route
from tests.game_world.support.world_design_for_tests import passage, spot
from tests.game_world.support.world_in_memory import world_in_memory
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_AT = WorldTick(12)
_HARU, _AKI, _SAYO, _GEN, _NATSU, _TOMO = (PersonId(name) for name in ("haru", "aki", "sayo", "gen", "natsu", "tomo"))
_SQUARE = spot("village_square")
_TUNNEL = spot("deep_tunnel")
_PASS = passage("snow_pass", ("village_square", "deep_tunnel"), travel_ticks=3)
_RESCUED = OutcomeDeclaration(
    outcome_id=OutcomeId("rescued"),
    name=DisplayName("救出"),
    announcement=TextWithUnassignedPeople("{each_person}は昇降機で外へ出た。"),
)
_MORNING = TextWithUnassignedPeople("空が白み、朝になった。")


def _morning(audience: PeopleSelection | EveryoneAwake) -> DayPhaseDeclaration:
    return DayPhaseDeclaration(
        name=DayPhaseName("morning"),
        display_name=DisplayName("morning"),
        begins_at=TimeOfDay(12),
        dark=False,
        announcement=_MORNING,
        audience=audience,
    )


def _outdoors() -> PeopleSelection:
    return PeopleSelection(where=IsAtSpotCondition(who=EachPerson(), spot=_SQUARE, failure_text=NoText()))


def _vitals(person: PersonId) -> PersonVitals:
    return PersonVitals.start(person, HitPoints(current=10, maximum=10))


def _village() -> WorldSession:
    """広場にハル (起きている)、アキ (気を失っている)、サヨ (昇降機で外へ出た) がいた。坑道にゲン、広場から坑道へ向かう峠にナツ、広場には死んで去った人として動くトモがいる。"""
    fainted, dead = _vitals(_AKI), _vitals(_TOMO)
    fainted.take_damage(Damage(10), WorldTick(0), WorldHappening())
    dead.take_damage(Damage(10), WorldTick(0), WorldHappening())
    dead.pass_time(WorldTick(1), DeathRule(grace=Ticks(0)), world_rules_for_tests().hunger)
    people = (_HARU, _AKI, _SAYO, _GEN, _NATSU, _TOMO)
    world = world_in_memory(
        world=WorldId("village"),
        rules=replace(world_rules_for_tests(), departed_persons_act=True),
        people=people,
        spots=(_SQUARE, _TUNNEL),
        passages=(_PASS,),
        vitals=tuple(fainted if p == _AKI else dead if p == _TOMO else _vitals(p) for p in people),
    )
    whereabouts = world.aggregates().whereabouts()
    for person in (_HARU, _AKI, _SAYO, _NATSU):
        whereabouts.place(PersonBody(person), _SQUARE)
    whereabouts.place(PersonBody(_GEN), _TUNNEL)
    whereabouts.place(DepartedPerson(_TOMO), _SQUARE)
    whereabouts.start_travel(PersonBody(_NATSU), Route(start=_SQUARE.spot_id, passages=(_PASS,)))
    world.aggregates().outcomes().decide(_SAYO, DeclaredOutcome(_RESCUED), WorldTick(2))
    whereabouts.remove(PersonBody(_SAYO))
    return world


class TestDayPhaseAddressees:
    """DayPhaseDeclaration.addressees が、作者の選んだ相手から、倒れている人と世界から外れた人を外して時間帯の知らせの相手を決めることを保証する。"""

    def test_everyone_awake_includes_the_departed_and_travellers_but_not_the_fainted_or_those_who_left(self) -> None:
        """相手を書かない (EveryoneAwake) 朝の知らせは、ハル・坑道のゲン・峠のナツ・去ったトモに届き、気を失ったアキと外へ出たサヨには届かない。"""
        addressees = _morning(EveryoneAwake()).addressees(_village().facts(), _AT)

        assert addressees == frozenset({_HARU, _GEN, _NATSU, _TOMO})

    def test_written_audience_reaches_only_those_chosen_and_awake(self) -> None:
        """広場にいる人を相手に書いた朝の知らせは、広場のハルと去ったトモにだけ届き、広場で気を失ったアキ・坑道のゲン・峠のナツには届かない。"""
        addressees = _morning(_outdoors()).addressees(_village().facts(), _AT)

        assert addressees == frozenset({_HARU, _TOMO})


class TestDayPhaseAnnouncement:
    """DayPhaseDeclaration.stimuli_when_entered が、時間帯に入ったことを、その時点の世界で決まる相手への目立たない世界の知らせにすることを保証する。"""

    def test_announcement_becomes_a_background_announcement_to_the_addressees(self) -> None:
        """広場にいる人を相手に書いた朝に入ると、相手に選ばれて起きている広場のハルと去ったトモに宛てた、目立たない世界の知らせ「空が白み、朝になった。」になる。"""
        [stimulus] = _morning(_outdoors()).stimuli_when_entered(_village().facts(), _AT)

        assert stimulus == AnnouncementStimulus(
            audience=frozenset({_HARU, _TOMO}),
            text=_MORNING.about({}),
            salience=Background(),
            at=_AT,
            kept_while_fainted=False,
        )

    def test_phase_without_announcement_makes_no_stimulus(self) -> None:
        """知らせの文を書いていない時間帯に入っても、刺激を作らない。"""
        phase = replace(_morning(EveryoneAwake()), announcement=NoAnnouncement())

        assert phase.stimuli_when_entered(_village().facts(), _AT) == ()
