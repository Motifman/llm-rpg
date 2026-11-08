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
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import UsesWorldDefault
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
from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
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
from ai_rpg_world.game_world.domain.value_object.hands_needed import HandsNeeded
from tests.game_world.support.declarations_for_tests import OPEN as OPEN_STATE
from tests.game_world.support.declarations_for_tests import open_passage_states

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
        states=open_passage_states(),
        initial_state=OPEN_STATE,
        hidden_until_revealed=False,
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
        hands_needed=HandsNeeded(1),
    )


def _grouping(name: str, visibility: MembershipVisibility = MembershipVisibility.SELF_ONLY) -> GroupingDeclaration:
    return GroupingDeclaration(
        grouping_id=GroupingId(name), name=DisplayName(name), visibility=visibility, changes=False
    )


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
        max_hp=UsesWorldDefault(),
        pack_capacity=UsesWorldDefault(),
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
    _Kind("character", "person_id", "characters", lambda name: _character(name, "hall"), DeclaredNouns.character),
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


class TestLookupById:
    """DeclaredNouns.world_stage_of / object_of が、実行時に集約が持つ ID から宣言を引くことを保証する。"""

    def test_world_stage_of_returns_the_declaration_with_the_id(self) -> None:
        """宣言した段階の WorldStageId を渡すと、その WorldStageDeclaration を返す。"""
        night = _world_stage("night")
        nouns = _nouns(world_stages=[_world_stage("day"), night])

        assert nouns.world_stage_of(WorldStageId("night")) == night

    def test_object_of_returns_the_declaration_with_the_id(self) -> None:
        """宣言した物の ObjectId を渡すと、その ObjectDeclaration を返す。"""
        lever = _object("lever", "lift_landing")
        nouns = _nouns(spots=[_spot("lift_landing")], objects=[lever])

        assert nouns.object_of(ObjectId("lever")) == lever

    def test_undeclared_id_raises_undeclared_noun_exception(self) -> None:
        """宣言に無い WorldStageId や ObjectId を渡すと UndeclaredNounException を投げる。"""
        nouns = _nouns(world_stages=[_world_stage("day")])

        with pytest.raises(UndeclaredNounException):
            nouns.world_stage_of(WorldStageId("night"))
        with pytest.raises(UndeclaredNounException):
            nouns.object_of(ObjectId("lever"))


def _flaw(declaration: str, name: str, field: str, reason: str) -> DesignFlaw:
    return DesignFlaw(DesignLocation(declaration, name, field), reason)


class TestCollectingFlaws:
    """DeclaredNouns が、作るときに見つけた誤りを最初の 1 つで止めずに集めて投げることを保証する。"""

    def test_consistent_declarations_are_accepted(self) -> None:
        """どの ID も宣言にあり、名前の重なりも無い宣言なら、断らずに作れる。"""
        cage_lever = _object("cage_lever", "lift_landing")
        nouns = _nouns(
            flags=[_flag("lift_repaired")],
            spots=[_spot("lift_landing"), _spot("cellar")],
            passages=[_passage("stairs", ("lift_landing", "cellar"))],
            objects=[cage_lever],
            item_specs=[_item_spec("lantern")],
            groupings=[_FACTION],
            groups=[_group("villagers", _FACTION)],
            characters=[
                _character(
                    "aki",
                    "lift_landing",
                    initial_items=("lantern",),
                    initial_groups=("villagers",),
                    knows_at_start=("aki", "haru"),
                ),
                _character("haru", "cellar"),
            ],
            world_stages=[_world_stage("night")],
            group_decisions=[_group_decision("exile_vote")],
            sections=[_section("lift_cage", "lift_landing", reachable_objects=("cage_lever",))],
            outcomes=[_outcome("rescued")],
        )

        assert nouns.object("cage_lever", _LOOKUP_AT) == cage_lever

    def test_undeclared_spawn_spot_and_duplicated_object_are_both_reported(self) -> None:
        """宣言に無い場所を spawn_spot に持つ登場人物と、同じ名前の物が 2 つあるとき、両方の DesignFlaw を持つ WorldDesignFlawsException を投げる。"""
        flaws = _flaws_of(
            lambda: _nouns(
                spots=[_spot("hall")],
                objects=[_object("lift_lever", "hall"), _object("lift_lever", "hall")],
                characters=[_character("aki", "cellar")],
            )
        )

        assert set(flaws) == {
            _flaw("character", "aki", "spawn_spot", "spot 'cellar' is not declared"),
            _flaw("object", "lift_lever", "object_id", "object 'lift_lever' is declared more than once"),
        }


class TestDuplicatedNames:
    """DeclaredNouns が、同じ種類の宣言で名前が重なると誤りにすることを保証する。"""

    @pytest.mark.parametrize("kind", _KINDS, ids=repr)
    def test_same_name_declared_twice_is_a_flaw(self, kind: _Kind) -> None:
        """同じ種類の宣言を同じ名前で 2 つ書くと、その名前の ID の欄を指す DesignFlaw を 1 つだけ持つ WorldDesignFlawsException を投げる。"""
        flaws = _flaws_of(lambda: _supporting_nouns(kind, [kind.make("lift"), kind.make("lift")]))

        assert flaws == (
            _flaw(kind.declaration, "lift", kind.id_field, f"{kind.declaration} 'lift' is declared more than once"),
        )

    def test_same_name_in_different_kinds_is_accepted(self) -> None:
        """場所と物のように種類が違えば、同じ名前を使っても断らない。"""
        nouns = _nouns(spots=[_spot("lift")], objects=[_object("lift", "lift")], sections=[_section("lift", "lift")])

        assert nouns.section("lift", _LOOKUP_AT).spot_id == SpotId("lift")


class TestReferencesToSpots:
    """DeclaredNouns が、場所を指す ID が宣言に無いと誤りにすることを保証する。"""

    def test_object_at_undeclared_spot_is_a_flaw(self) -> None:
        """物の spot_id が宣言に無い場所なら、その物の spot_id を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(lambda: _nouns(spots=[_spot("hall")], objects=[_object("lift_lever", "cellar")]))

        assert flaws == (_flaw("object", "lift_lever", "spot_id", "spot 'cellar' is not declared"),)

    def test_section_at_undeclared_spot_is_a_flaw(self) -> None:
        """区画の spot_id が宣言に無い場所なら、その区画の spot_id を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(lambda: _nouns(spots=[_spot("hall")], sections=[_section("lift_cage", "cellar")]))

        assert flaws == (_flaw("section", "lift_cage", "spot_id", "spot 'cellar' is not declared"),)

    def test_passage_end_at_undeclared_spot_is_a_flaw(self) -> None:
        """通路の ends の片方が宣言に無い場所なら、その端の位置 (ends[1]) を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(lambda: _nouns(spots=[_spot("hall")], passages=[_passage("stairs", ("hall", "cellar"))]))

        assert flaws == (_flaw("passage", "stairs", "ends[1]", "spot 'cellar' is not declared"),)

    def test_passage_with_both_ends_undeclared_reports_each_end(self) -> None:
        """通路の両端がどちらも宣言に無い場所なら、ends[0] と ends[1] の DesignFlaw を両方投げる。"""
        flaws = _flaws_of(lambda: _nouns(passages=[_passage("stairs", ("hall", "cellar"))]))

        assert flaws == (
            _flaw("passage", "stairs", "ends[0]", "spot 'hall' is not declared"),
            _flaw("passage", "stairs", "ends[1]", "spot 'cellar' is not declared"),
        )

    def test_character_spawning_at_undeclared_spot_is_a_flaw(self) -> None:
        """登場人物の spawn_spot が宣言に無い場所なら、その登場人物の spawn_spot を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(lambda: _nouns(spots=[_spot("hall")], characters=[_character("aki", "cellar")]))

        assert flaws == (_flaw("character", "aki", "spawn_spot", "spot 'cellar' is not declared"),)


class TestSectionReachableObjects:
    """DeclaredNouns が、区画の中から届く物が宣言にあり、区画と同じ場所に置かれていることを確かめることを保証する。"""

    def test_undeclared_reachable_object_is_a_flaw(self) -> None:
        """reachable_objects に宣言に無い物があると、その位置 (reachable_objects[1]) を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(
            lambda: _nouns(
                spots=[_spot("lift_landing")],
                objects=[_object("cage_lever", "lift_landing")],
                sections=[_section("lift_cage", "lift_landing", reachable_objects=("cage_lever", "cage_bell"))],
            )
        )

        assert flaws == (_flaw("section", "lift_cage", "reachable_objects[1]", "object 'cage_bell' is not declared"),)

    def test_reachable_object_at_another_spot_is_a_flaw(self) -> None:
        """reachable_objects の物が区画と違う場所に置かれていると、その位置を指し、両方の場所を書いた DesignFlaw を投げる。"""
        flaws = _flaws_of(
            lambda: _nouns(
                spots=[_spot("lift_landing"), _spot("storeroom")],
                objects=[_object("cage_lever", "storeroom")],
                sections=[_section("lift_cage", "lift_landing", reachable_objects=("cage_lever",))],
            )
        )

        assert flaws == (
            _flaw(
                "section",
                "lift_cage",
                "reachable_objects[0]",
                "object 'cage_lever' is at spot 'storeroom', not 'lift_landing'",
            ),
        )


class TestGroupGrouping:
    """DeclaredNouns が、集まりの持つ分け方が分け方の宣言と一致することを確かめることを保証する。"""

    def test_group_of_undeclared_grouping_is_a_flaw(self) -> None:
        """集まりの分け方が groupings に無いと、その集まりの grouping を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(lambda: _nouns(groupings=[_FACTION], groups=[_group("first_squad", _grouping("squad"))]))

        assert flaws == (_flaw("group", "first_squad", "grouping", "grouping 'squad' is not declared"),)

    def test_group_whose_grouping_differs_from_the_declared_one_is_a_flaw(self) -> None:
        """集まりの分け方が、groupings にある同じ grouping_id の分け方と中身が違うと、その集まりの grouping を指す DesignFlaw を投げる。"""
        open_faction = _grouping("faction", visibility=MembershipVisibility.EVERYONE)
        flaws = _flaws_of(lambda: _nouns(groupings=[_FACTION], groups=[_group("wolves", open_faction)]))

        assert flaws == (_flaw("group", "wolves", "grouping", "grouping 'faction' differs from its declaration"),)


class TestCharacterReferences:
    """DeclaredNouns が、登場人物が最初に持つ物・入る集まり・知っている人が宣言にあることを確かめることを保証する。"""

    def test_undeclared_initial_item_is_a_flaw(self) -> None:
        """initial_items に宣言に無い品物があると、その位置 (initial_items[1]) を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(
            lambda: _nouns(
                spots=[_spot("hall")],
                item_specs=[_item_spec("lantern")],
                characters=[_character("aki", "hall", initial_items=("lantern", "pickaxe"))],
            )
        )

        assert flaws == (_flaw("character", "aki", "initial_items[1]", "item_spec 'pickaxe' is not declared"),)

    def test_undeclared_initial_group_is_a_flaw(self) -> None:
        """initial_groups に宣言に無い集まりがあると、その位置 (initial_groups[0]) を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(
            lambda: _nouns(
                spots=[_spot("hall")],
                groupings=[_FACTION],
                characters=[_character("aki", "hall", initial_groups=("wolves",))],
            )
        )

        assert flaws == (_flaw("character", "aki", "initial_groups[0]", "group 'wolves' is not declared"),)

    def test_undeclared_known_person_is_a_flaw(self) -> None:
        """knows_at_start に登場人物として宣言されていない人がいると、その位置 (knows_at_start[1]) を指す DesignFlaw を投げる。"""
        flaws = _flaws_of(
            lambda: _nouns(
                spots=[_spot("hall")],
                characters=[_character("aki", "hall", knows_at_start=("aki", "natsu"))],
            )
        )

        assert flaws == (_flaw("character", "aki", "knows_at_start[1]", "character 'natsu' is not declared"),)

    def test_two_groups_of_the_same_grouping_is_a_flaw(self) -> None:
        """initial_groups に同じ分け方の集まりを 2 つ書くと、2 つめの位置を指し、両方の集まりと分け方を書いた DesignFlaw を投げる。"""
        flaws = _flaws_of(
            lambda: _nouns(
                spots=[_spot("hall")],
                groupings=[_FACTION],
                groups=[_group("villagers", _FACTION), _group("wolves", _FACTION)],
                characters=[_character("aki", "hall", initial_groups=("villagers", "wolves"))],
            )
        )

        assert flaws == (
            _flaw(
                "character",
                "aki",
                "initial_groups[1]",
                "group 'wolves' and group 'villagers' both belong to grouping 'faction'",
            ),
        )

    def test_groups_of_different_groupings_are_accepted(self) -> None:
        """initial_groups の集まりの分け方がどれも違えば、断らずに作れる。"""
        squad = _grouping("squad")
        nouns = _nouns(
            spots=[_spot("hall")],
            groupings=[_FACTION, squad],
            groups=[_group("villagers", _FACTION), _group("first_squad", squad)],
            characters=[_character("aki", "hall", initial_groups=("villagers", "first_squad"))],
        )

        assert nouns.character("aki", _LOOKUP_AT).initial_groups == (GroupId("villagers"), GroupId("first_squad"))
