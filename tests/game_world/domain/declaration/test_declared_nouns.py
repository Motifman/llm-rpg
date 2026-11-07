from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import pytest

from ai_rpg_world.game_world.domain.declaration.character import (
    CharacterDeclaration,
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    FlagStateKind,
    FlagValue,
    ItemSpecDeclaration,
    NotALightSource,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress import (
    AllActionsAllowed,
    FlagDeclaration,
    GroupDecisionDeclaration,
    OutcomeDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.spot import (
    NoAmbientSound,
    NoCapacity,
    NoSmell,
    PassageDeclaration,
    SpotAtmosphere,
    SpotDeclaration,
    SpotSectionDeclaration,
    Temperature,
)
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.world_design_exception import UnknownNameFlaw, WorldDesignFlawsException
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    FlagId,
    GroupDecisionId,
    GroupId,
    GroupingId,
    ItemSpecId,
    ObjectId,
    OutcomeId,
    PassageId,
    PersonId,
    SpotId,
    SpotSectionId,
    StateKeyId,
    Ticks,
    WorldStageId,
)

_LOOKUP_AT = DesignLocation("object_interaction", "pull_lever", "object")


def _spot(name: str) -> SpotDeclaration:
    return SpotDeclaration(
        spot_id=SpotId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の様子"),
        atmosphere=SpotAtmosphere(
            lighting=Lighting.BRIGHT,
            outdoor=False,
            temperature=Temperature.NORMAL,
            ambient_sound=NoAmbientSound(),
            smell=NoSmell(),
        ),
    )


def _passage(name: str, ends: tuple[str, str]) -> PassageDeclaration:
    return PassageDeclaration(
        passage_id=PassageId(name),
        ends=(SpotId(ends[0]), SpotId(ends[1])),
        two_way=True,
        travel_ticks=Ticks(1),
    )


def _object(name: str, spot: str, state_keys: tuple[str, ...] = ()) -> ObjectDeclaration:
    return ObjectDeclaration(
        object_id=ObjectId(name),
        spot_id=SpotId(spot),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の見た目"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=False),
        state_keys=tuple(
            ObjectStateKeyDeclaration(
                object_id=ObjectId(name), key=StateKeyId(key), kind=FlagStateKind(), initial=FlagValue(raised=False)
            )
            for key in state_keys
        ),
    )


def _item_spec(name: str) -> ItemSpecDeclaration:
    return ItemSpecDeclaration(
        item_spec_id=ItemSpecId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の見た目"),
        state_keys=(),
        lights_up=NotALightSource(),
    )


def _grouping(name: str, visibility: MembershipVisibility = MembershipVisibility.SELF_ONLY) -> GroupingDeclaration:
    return GroupingDeclaration(grouping_id=GroupingId(name), name=DisplayName(name), visibility=visibility, changes=False)


def _group(name: str, grouping: GroupingDeclaration) -> GroupDeclaration:
    return GroupDeclaration(
        group_id=GroupId(name),
        grouping=grouping,
        name=DisplayName(name),
        members_know_each_other=False,
        shared_description=NoSharedDescription(),
    )


def _character(
    name: str,
    spawn_spot: str,
    initial_items: tuple[str, ...] = (),
    initial_groups: tuple[str, ...] = (),
    knows_at_start: tuple[str, ...] = (),
) -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=PersonId(name),
        appearance=DescriptionText(f"{name} の見た目"),
        spawn_spot=SpotId(spawn_spot),
        initial_items=tuple(ItemSpecId(item) for item in initial_items),
        initial_held=(),
        initial_groups=tuple(GroupId(group) for group in initial_groups),
        knows_at_start=tuple(PersonId(person) for person in knows_at_start),
    )


def _section(name: str, spot: str, reachable_objects: tuple[str, ...] = ()) -> SpotSectionDeclaration:
    return SpotSectionDeclaration(
        section_id=SpotSectionId(name),
        spot_id=SpotId(spot),
        name=DisplayName(name),
        capacity=NoCapacity(),
        reachable_objects=tuple(ObjectId(obj) for obj in reachable_objects),
    )


def _flag(name: str) -> FlagDeclaration:
    return FlagDeclaration(flag_id=FlagId(name), meaning=DescriptionText(f"{name} の意味"), initially_raised=False)


def _world_stage(name: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        allowed_actions=AllActionsAllowed(),
    )


def _group_decision(name: str) -> GroupDecisionDeclaration:
    return GroupDecisionDeclaration(
        decision_id=GroupDecisionId(name), name=DisplayName(name), abstain_allowed=True, reveals_ballots=False
    )


def _outcome(name: str) -> OutcomeDeclaration:
    return OutcomeDeclaration(
        outcome_id=OutcomeId(name),
        name=DisplayName(name),
        announcement=TextWithUnassignedPeople("{person}は外へ出た。"),
    )


def _nouns(
    flags: Iterable[FlagDeclaration] = (),
    spots: Iterable[SpotDeclaration] = (),
    passages: Iterable[PassageDeclaration] = (),
    objects: Iterable[ObjectDeclaration] = (),
    item_specs: Iterable[ItemSpecDeclaration] = (),
    groupings: Iterable[GroupingDeclaration] = (),
    groups: Iterable[GroupDeclaration] = (),
    characters: Iterable[CharacterDeclaration] = (),
    world_stages: Iterable[WorldStageDeclaration] = (),
    group_decisions: Iterable[GroupDecisionDeclaration] = (),
    sections: Iterable[SpotSectionDeclaration] = (),
    outcomes: Iterable[OutcomeDeclaration] = (),
) -> DeclaredNouns:
    return DeclaredNouns(
        flags=flags,
        spots=spots,
        passages=passages,
        objects=objects,
        item_specs=item_specs,
        groupings=groupings,
        groups=groups,
        characters=characters,
        world_stages=world_stages,
        group_decisions=group_decisions,
        sections=sections,
        outcomes=outcomes,
    )


def _flaws_of(build: Callable[[], DeclaredNouns]) -> tuple[DesignFlaw, ...]:
    with pytest.raises(WorldDesignFlawsException) as raised:
        build()
    return raised.value.flaws


_FACTION = _grouping("faction")


class _Kind:
    def __init__(
        self,
        declaration: str,
        id_field: str,
        argument: str,
        make: Callable[[str], Any],
        lookup: Callable[[DeclaredNouns, str, DesignLocation], Any] | None,
    ) -> None:
        self.declaration = declaration
        self.id_field = id_field
        self.argument = argument
        self.make = make
        self.lookup = lookup

    def __repr__(self) -> str:
        return self.declaration


_KINDS = [
    _Kind("flag", "flag_id", "flags", _flag, DeclaredNouns.flag),
    _Kind("spot", "spot_id", "spots", _spot, DeclaredNouns.spot),
    _Kind("passage", "passage_id", "passages", lambda name: _passage(name, ("hall", "cellar")), DeclaredNouns.passage),
    _Kind("object", "object_id", "objects", lambda name: _object(name, "hall"), DeclaredNouns.object),
    _Kind("item_spec", "item_spec_id", "item_specs", _item_spec, DeclaredNouns.item_spec),
    _Kind("grouping", "grouping_id", "groupings", _grouping, None),
    _Kind("group", "group_id", "groups", lambda name: _group(name, _FACTION), DeclaredNouns.group),
    _Kind(
        "character", "person_id", "characters", lambda name: _character(name, "hall"), DeclaredNouns.character
    ),
    _Kind("world_stage", "stage_id", "world_stages", _world_stage, DeclaredNouns.world_stage),
    _Kind("group_decision", "decision_id", "group_decisions", _group_decision, DeclaredNouns.group_decision),
    _Kind("section", "section_id", "sections", lambda name: _section(name, "hall"), DeclaredNouns.section),
    _Kind("outcome", "outcome_id", "outcomes", _outcome, DeclaredNouns.outcome),
]

_LOOKUP_KINDS = [kind for kind in _KINDS if kind.lookup is not None]


def _supporting_nouns(kind: _Kind, declarations: list[Any]) -> DeclaredNouns:
    supporting: dict[str, list[Any]] = {
        "spots": [_spot("hall"), _spot("cellar")],
        "groupings": [_FACTION],
    }
    supporting[kind.argument] = [*supporting.get(kind.argument, []), *declarations]
    return _nouns(**supporting)


class TestLookupByName:
    """DeclaredNouns が、名前から宣言を引き、引けない名前を UnknownNameFlaw で知らせることを保証する。"""

    @pytest.mark.parametrize("kind", _LOOKUP_KINDS, ids=repr)
    def test_declared_name_returns_its_declaration(self, kind: _Kind) -> None:
        """宣言にある名前で引くと、その名前の宣言を返す。"""
        wanted = kind.make("lift")
        nouns = _supporting_nouns(kind, [kind.make("bell"), wanted])

        assert kind.lookup is not None
        found = kind.lookup(nouns, "lift", _LOOKUP_AT)

        assert found == wanted

    @pytest.mark.parametrize("kind", _LOOKUP_KINDS, ids=repr)
    def test_undeclared_name_raises_unknown_name_flaw_at_the_given_location(self, kind: _Kind) -> None:
        """宣言に無い名前で引くと、渡した DesignLocation と「<種類> '<名前>' is not declared」を持つ UnknownNameFlaw を投げる。"""
        nouns = _supporting_nouns(kind, [kind.make("bell")])

        assert kind.lookup is not None
        with pytest.raises(UnknownNameFlaw) as raised:
            kind.lookup(nouns, "lift", _LOOKUP_AT)

        assert raised.value.flaw == DesignFlaw(_LOOKUP_AT, f"{kind.declaration} 'lift' is not declared")


class TestObjectStateKey:
    """DeclaredNouns.object_state_key が、物の名前と鍵の名前から物の状態の宣言を引くことを保証する。"""

    def test_declared_key_of_declared_object_returns_its_state_key(self) -> None:
        """宣言にある物の、宣言にある鍵で引くと、その鍵の ObjectStateKeyDeclaration を返す。"""
        lever = _object("lift_lever", "hall", state_keys=("pulled", "broken"))
        nouns = _nouns(spots=[_spot("hall")], objects=[lever])

        found = nouns.object_state_key("lift_lever", "broken", _LOOKUP_AT)

        assert found == lever.state_keys[1]

    def test_undeclared_object_raises_unknown_name_flaw(self) -> None:
        """宣言に無い物で引くと、渡した DesignLocation と「object '<名前>' is not declared」を持つ UnknownNameFlaw を投げる。"""
        nouns = _nouns(spots=[_spot("hall")], objects=[_object("lift_lever", "hall", state_keys=("pulled",))])

        with pytest.raises(UnknownNameFlaw) as raised:
            nouns.object_state_key("lift_bell", "pulled", _LOOKUP_AT)

        assert raised.value.flaw == DesignFlaw(_LOOKUP_AT, "object 'lift_bell' is not declared")

    def test_undeclared_key_raises_unknown_name_flaw(self) -> None:
        """宣言にある物の、宣言に無い鍵で引くと、渡した DesignLocation と「object '<物>' has no state key '<鍵>'」を持つ UnknownNameFlaw を投げる。"""
        nouns = _nouns(spots=[_spot("hall")], objects=[_object("lift_lever", "hall", state_keys=("pulled",))])

        with pytest.raises(UnknownNameFlaw) as raised:
            nouns.object_state_key("lift_lever", "broken", _LOOKUP_AT)

        assert raised.value.flaw == DesignFlaw(_LOOKUP_AT, "object 'lift_lever' has no state key 'broken'")


class TestGroupsIn:
    """DeclaredNouns.groups_in が、1 つの分け方に入る集まりだけを返すことを保証する。"""

    def test_returns_only_groups_of_the_grouping_in_declared_order(self) -> None:
        """分け方を渡すと、その分け方の集まりだけを宣言した順に返し、ほかの分け方の集まりは返さない。"""
        squad = _grouping("squad")
        wolves = _group("wolves", _FACTION)
        first_squad = _group("first_squad", squad)
        villagers = _group("villagers", _FACTION)
        nouns = _nouns(groupings=[_FACTION, squad], groups=[wolves, first_squad, villagers])

        assert nouns.groups_in(_FACTION) == (wolves, villagers)

    def test_grouping_without_groups_returns_empty(self) -> None:
        """集まりが 1 つも無い分け方を渡すと、空を返す。"""
        squad = _grouping("squad")
        nouns = _nouns(groupings=[_FACTION, squad], groups=[_group("wolves", _FACTION)])

        assert nouns.groups_in(squad) == ()


class TestSectionsAt:
    """DeclaredNouns.sections_at が、1 つの場所にある区画だけを返すことを保証する。"""

    def test_returns_only_sections_of_the_spot_in_declared_order(self) -> None:
        """場所を渡すと、その場所の区画だけを宣言した順に返し、ほかの場所の区画は返さない。"""
        cage = _section("lift_cage", "lift_landing")
        boat = _section("boat", "shore")
        watchtower = _section("watchtower", "lift_landing")
        nouns = _nouns(spots=[_spot("lift_landing"), _spot("shore")], sections=[cage, boat, watchtower])

        assert nouns.sections_at(SpotId("lift_landing")) == (cage, watchtower)

    def test_spot_without_sections_returns_empty(self) -> None:
        """区画が 1 つも無い場所を渡すと、空を返す。"""
        nouns = _nouns(spots=[_spot("lift_landing"), _spot("shore")], sections=[_section("boat", "shore")])

        assert nouns.sections_at(SpotId("lift_landing")) == ()
