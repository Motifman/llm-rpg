"""人まわりの集約 (PersonVitals・PersonOutcomes・GroupMembership・PeopleRegister) の memento が JSON を行き来し、知らない形の行を止めることを保証する。"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ai_rpg_world.game_world.domain.declaration.character import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.people.people_register import PeopleRegister, PeopleRegisterMemento, PersonName
from ai_rpg_world.game_world.domain.person.group_membership import (
    GroupMembership,
    GroupMembershipMemento,
    PersonGroupInGrouping,
)
from ai_rpg_world.game_world.domain.person.life_state import (
    Alive,
    Dead,
    Down,
    LifeState,
    Starvation,
    StruckByPerson,
    WorldHappening,
)
from ai_rpg_world.game_world.domain.person.person_outcomes import (
    DeclaredOutcome,
    Died,
    PersonOutcomes,
    PersonOutcomesMemento,
)
from ai_rpg_world.game_world.domain.person.person_vitals import NotBusy, PersonVitals, PersonVitalsMemento
from ai_rpg_world.game_world.domain.person.status_effect import StatusEffect, StatusEffectType
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DisplayName,
    GroupId,
    GroupingId,
    HitPoints,
    OutcomeId,
    PersonId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS, StoredMemento
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    StoredMementoUnreadableException,
)
from tests.game_world.support.world_design_for_tests import character

_WORLD = WorldId("island")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")


def _vitals() -> PersonVitalsMemento:
    vitals = PersonVitals.start(_ALICE, HitPoints(current=10, maximum=10))
    vitals.add_status_effect(StatusEffect(StatusEffectType("poisoned"), WorldTick(9)))
    vitals.add_status_effect(StatusEffect(StatusEffectType("chilled"), WorldTick(4)))
    vitals.start_action(WorldTick(12))
    vitals.take_damage(Damage(10), WorldTick(5), StruckByPerson(_BOB))
    return vitals.memento()


def _outcomes() -> PersonOutcomesMemento:
    outcomes = PersonOutcomes.start(_WORLD, (_CAROL, _ALICE, _BOB))
    outcomes.decide(_ALICE, Died())
    outcomes.decide(
        _CAROL,
        DeclaredOutcome(
            OutcomeDeclaration(
                outcome_id=OutcomeId("escaped"),
                name=DisplayName("脱出"),
                announcement=TextWithUnassignedPeople("{actor}は島を出た。"),
            )
        ),
    )
    return outcomes.memento()


def _group(name: str, grouping: str) -> GroupDeclaration:
    return GroupDeclaration(
        group_id=GroupId(name),
        grouping=GroupingDeclaration(
            grouping_id=GroupingId(grouping),
            name=DisplayName(grouping),
            visibility=MembershipVisibility.EVERYONE,
            changes=True,
        ),
        name=DisplayName(name),
        members_know_each_other=False,
        shared_description=NoSharedDescription(),
    )


def _membership() -> GroupMembershipMemento:
    membership = GroupMembership.start(_WORLD, {_ALICE: (_group("red", "teams"),)})
    membership.join(_ALICE, _group("keeper", "roles"))
    membership.join(_BOB, _group("blue", "teams"))
    return membership.memento()


def _register() -> PeopleRegisterMemento:
    register = PeopleRegister.from_characters(_WORLD, (character("alice", "beach"), character("bob", "beach")))
    register.name(_ALICE, DisplayName("アリス"))
    register.name(_BOB, DisplayName("ボブ"))
    return register.memento()


_MEMENTOS = {
    "person_vitals": _vitals(),
    "person_outcomes": _outcomes(),
    "group_membership": _membership(),
    "people_register": _register(),
}


def _with_state(stored: StoredMemento, change: dict[str, object]) -> StoredMemento:
    state = json.loads(stored.state)
    state.update(change)
    return replace(stored, state=json.dumps(state))


class TestRoundTrip:
    """状態を変えたあとの memento を行にして読み戻すと、同じ memento になることを保証する。"""

    @pytest.mark.parametrize("kind", sorted(_MEMENTOS))
    def test_changed_memento_survives_a_round_trip(self, kind: str) -> None:
        """状態を変えた集約の memento を行にすると、その種類の行になり、読み戻すと同じ memento になる。"""
        memento = _MEMENTOS[kind]

        stored = GAME_WORLD_CODECS.stored(memento)
        restored = GAME_WORLD_CODECS.memento(stored, type(memento))

        assert (stored.kind, restored) == (kind, memento)

    @pytest.mark.parametrize(
        "life_state",
        [
            Alive(),
            Down(fell_at=WorldTick(3), cause=StruckByPerson(_BOB)),
            Down(fell_at=WorldTick(3), cause=Starvation()),
            Down(fell_at=WorldTick(3), cause=WorldHappening()),
            Dead(died_at=WorldTick(8)),
        ],
    )
    def test_every_life_state_survives_a_round_trip(self, life_state: LifeState) -> None:
        """生きている・倒れた (倒れた原因ごと)・死んだ、のどの状態も、読み戻すと同じ状態になる。"""
        hp = HitPoints(current=4 if isinstance(life_state, Alive) else 0, maximum=10)
        memento = replace(_vitals(), hp=hp, life_state=life_state, busy_until=NotBusy())

        restored = GAME_WORLD_CODECS.memento(GAME_WORLD_CODECS.stored(memento), PersonVitalsMemento)

        assert restored == memento

    def test_life_state_is_written_under_its_tag(self) -> None:
        """倒れた状態は、印 down の中に、倒れた tick と、印で包んだ原因を持つ。"""
        state = json.loads(GAME_WORLD_CODECS.stored(_MEMENTOS["person_vitals"]).state)

        assert state["life_state"] == {"down": {"fell_at": 5, "cause": {"struck_by_person": {"person": "bob"}}}}
        assert state["busy_until"] == {"world_tick": 12}

    def test_outcomes_keep_the_order_of_people(self) -> None:
        """結末の列は、memento の人の並び (carol, alice, bob) のまま書いて読む。"""
        restored = GAME_WORLD_CODECS.memento(
            GAME_WORLD_CODECS.stored(_MEMENTOS["person_outcomes"]), PersonOutcomesMemento
        )

        assert [entry.person for entry in restored.outcomes] == [_CAROL, _ALICE, _BOB]

    @pytest.mark.parametrize(
        ("memento", "listed", "sort_key"),
        [
            (
                replace(
                    _vitals(),
                    status_effects=frozenset(
                        StatusEffect(StatusEffectType(f"effect_{n}"), WorldTick(9)) for n in range(8)
                    ),
                ),
                "status_effects",
                ("kind",),
            ),
            (
                GroupMembershipMemento(
                    _WORLD,
                    frozenset(
                        PersonGroupInGrouping(PersonId(f"p{n}"), GroupingId(grouping), GroupId("g"))
                        for n in range(4)
                        for grouping in ("teams", "roles")
                    ),
                ),
                "groups",
                ("person", "grouping"),
            ),
            (
                PeopleRegisterMemento(
                    _WORLD, frozenset(PersonName(PersonId(f"p{n}"), DisplayName(f"名{n}")) for n in range(8))
                ),
                "names",
                ("person",),
            ),
        ],
        ids=["person_vitals", "group_membership", "people_register"],
    )
    def test_sets_are_written_in_key_order(self, memento: object, listed: str, sort_key: tuple[str, ...]) -> None:
        """8 件の集合は、集合の走査順に依らず、持ち主のキーの昇順に並べて書く。同じ memento がいつも同じ JSON の文字列になる。"""
        state = json.loads(GAME_WORLD_CODECS.stored(memento).state)

        keys = [tuple(item[key] for key in sort_key) for item in state[listed]]

        assert len(keys) == 8
        assert keys == sorted(keys)


class TestUnreadableRows:
    """知らない形の行を、読み捨てずに止めることを保証する。"""

    @pytest.mark.parametrize("kind", sorted(_MEMENTOS))
    def test_row_with_an_unknown_key_is_refused(self, kind: str) -> None:
        """知らないキーのある行は、そのキーの名前を添えて止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_MEMENTOS[kind]), {"mood": "calm"})

        with pytest.raises(StoredMementoUnreadableException, match="mood"):
            GAME_WORLD_CODECS.memento(stored, type(_MEMENTOS[kind]))

    def test_unknown_life_state_is_refused(self) -> None:
        """知らない印の生死の状態は、その印を添えて止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_MEMENTOS["person_vitals"]), {"life_state": {"asleep": {}}})

        with pytest.raises(StoredMementoUnreadableException, match="asleep"):
            GAME_WORLD_CODECS.memento(stored, PersonVitalsMemento)

    def test_hit_points_above_the_maximum_are_refused(self) -> None:
        """最大を超える HP の行は、ドメインが断った理由を StoredMementoUnreadableException に包んで止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_MEMENTOS["person_vitals"]), {"hp": {"current": 11, "maximum": 10}}
        )

        with pytest.raises(StoredMementoUnreadableException, match="person_vitals"):
            GAME_WORLD_CODECS.memento(stored, PersonVitalsMemento)

    def test_unknown_outcome_is_refused(self) -> None:
        """知らない印の結末は止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_MEMENTOS["person_outcomes"]),
            {"outcomes": [{"person": "alice", "outcome": {"vanished": {}}}]},
        )

        with pytest.raises(StoredMementoUnreadableException, match="vanished"):
            GAME_WORLD_CODECS.memento(stored, PersonOutcomesMemento)

    def test_person_in_two_groups_of_one_grouping_is_refused(self) -> None:
        """1 人が同じ分け方の 2 つの集団にいる行は、memento の決まりで止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_MEMENTOS["group_membership"]),
            {
                "groups": [
                    {"person": "alice", "grouping": "teams", "group": "red"},
                    {"person": "alice", "grouping": "teams", "group": "blue"},
                ]
            },
        )

        with pytest.raises(StoredMementoUnreadableException, match="group_membership"):
            GAME_WORLD_CODECS.memento(stored, GroupMembershipMemento)
