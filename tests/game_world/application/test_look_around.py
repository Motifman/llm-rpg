from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.look_around import LookAround, LookAroundCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.object_state_conditions import ObjectValueIsCondition
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    ObjectAppearance,
    ObjectStateKeyDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.object_looks_declaration import (
    NoLook,
    ObjectLook,
    ObjectLooksDeclaration,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import Unidentified
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DescriptionText,
    ObjectId,
    PersonId,
    StateKeyId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import PersonBody, Route
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import (
    character,
    compose_world,
    item_spec,
    nouns,
    obj,
    passage,
    spot,
)
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_WORLD = WorldId("look_around_world")
_ALICE, _BOB, _CAROL = PersonId("alice"), PersonId("bob"), PersonId("carol")
_NOW = WorldTick(0)
_ROPE = item_spec("rope")
_LID = ObjectStateKeyDeclaration(
    object_id=ObjectId("chest"),
    key=StateKeyId("lid"),
    kind=ChoiceStateKind(choices=(ChoiceName("shut"), ChoiceName("open"))),
    initial=ChoiceValue(ChoiceName("shut")),
)
_CHEST = replace(obj("chest", "cave"), state_keys=(_LID,))
_HIDDEN_NICHE = replace(
    obj("niche", "cave"), appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=True)
)
_FAR_SHELF = obj("shelf", "hut")
_CHEST_LOOKS = ObjectLooksDeclaration(
    object_id=_CHEST.object_id,
    looks=(
        ObjectLook(
            when=ObjectValueIsCondition(key=_LID, value=ChoiceValue(ChoiceName("open")), failure_text=NoText()),
            text=DescriptionText("蓋が開いている"),
        ),
    ),
)
_CAVE_TO_HUT = passage("cave_hut", ("cave", "hut"))


def _cave(lighting: Lighting) -> SpotDeclaration:
    cave = spot("cave")
    return replace(cave, atmosphere=replace(cave.atmosphere, lighting=lighting))


class _World:
    """洞窟に alice・bob・carol がいて、宝箱と隠れた壁龕がある。小屋には棚と dave。洞窟と小屋が道でつながる。bob はロープを 2 本持ち、1 本を手に持つ。"""

    def __init__(self, lighting: Lighting = Lighting.BRIGHT, *, departed_persons_act: bool = False) -> None:
        bob = replace(
            character("bob", "cave"),
            initial_items=(_ROPE.item_spec_id, _ROPE.item_spec_id),
            initial_held=(_ROPE.item_spec_id,),
        )
        self.design = compose_world(
            nouns(
                spots=[_cave(lighting), spot("hut")],
                passages=[_CAVE_TO_HUT],
                objects=[_CHEST, _HIDDEN_NICHE, _FAR_SHELF],
                item_specs=[_ROPE],
                characters=[character("alice", "cave"), bob, character("carol", "cave"), character("dave", "hut")],
            ),
            object_looks=[_CHEST_LOOKS],
            world_rules=replace(world_rules_for_tests(), departed_persons_act=departed_persons_act),
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="look_around_world",
            scenario_hash="look_around_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=_WORLD, design=self.design))
        self.scope = CommandScope(self.store, CommittedEventsDistributor())
        self._look_around = LookAround(self.scope, self.design)

    def looks_around(self, person: PersonId) -> VisibleSurroundings | NothingInView:
        return self._look_around(LookAroundCommand(person))

    def change(self, work: Callable[[WorldSession], None]) -> None:
        self.scope.run(work)

    def drops_a_rope_in_the_cave(self) -> ItemInstanceId:
        def work(session: WorldSession) -> ItemInstanceId:
            rope = session.aggregates().bring_item_into_world(_ROPE, _NOW)
            session.aggregates().ground_items(_cave(Lighting.BRIGHT).spot_id).place(rope)
            return rope

        return self.scope.run(work)

    def handle_of(self, person: PersonId) -> int:
        session = self.store.session()
        handle = session.facts().people_register().handle_of(person).value
        session.roll_back()
        return handle

    def held_items_of(self, person: PersonId) -> tuple[ItemInstanceId, ...]:
        session = self.store.session()
        items = session.facts().inventory(person).held_items()
        session.roll_back()
        return items

    def items_of(self, person: PersonId) -> tuple[ItemInstanceId, ...]:
        session = self.store.session()
        items = session.facts().inventory(person).items()
        session.roll_back()
        return items


def _falls(person: PersonId) -> Callable[[WorldSession], None]:
    return lambda session: session.aggregates().vitals(person).take_damage(Damage(999), _NOW, WorldHappening())


def _dies(person: PersonId) -> Callable[[WorldSession], None]:
    def work(session: WorldSession) -> None:
        _falls(person)(session)
        session.aggregates().vitals(person).pass_time(_NOW, DeathRule(grace=Ticks(0)), session.facts().rules().hunger)
        session.aggregates().whereabouts().place_departed(person, departed_persons_act=True)

    return work


def _seen(surroundings: VisibleSurroundings | NothingInView) -> VisibleSurroundings:
    assert isinstance(surroundings, VisibleSurroundings)
    return surroundings


def _handles(surroundings: VisibleSurroundings) -> list[int | None]:
    return [None if isinstance(seen.person, Unidentified) else seen.person.handle.value for seen in surroundings.people]


class TestLookAround:
    """LookAround が、見渡す人のいる場所の SpotContents と明るさから VisibleSurroundings を組む挙動を保証する。"""

    def test_bright_spot_shows_other_people_objects_and_ground_items(self) -> None:
        """明るい洞窟で alice が見渡すと、自分以外の bob と carol、宝箱、地面のロープ、bob が手に持つロープ 1 本だけが出る。小屋の dave と、bob の荷の中のロープは出ない。"""
        world = _World(Lighting.BRIGHT)
        ground_rope = world.drops_a_rope_in_the_cave()

        surroundings = _seen(world.looks_around(_ALICE))

        assert surroundings.shows_description
        assert len(surroundings.people) == 2
        assert [seen.declaration.object_id for seen in surroundings.objects] == [_CHEST.object_id]
        assert surroundings.ground_items == (ground_rope,)
        assert [seen.visible_items for seen in surroundings.people if seen.visible_items] == [world.held_items_of(_BOB)]

    def test_hidden_object_appears_only_after_it_is_revealed(self) -> None:
        """洞窟の隠れた壁龕は現れるまで場面に出ず、現した後に出る。小屋の棚は洞窟の場面に出ない。"""
        world = _World(Lighting.BRIGHT)
        before = _seen(world.looks_around(_ALICE)).objects

        world.change(lambda s: s.aggregates().object_state(_HIDDEN_NICHE.object_id).reveal())
        after = _seen(world.looks_around(_ALICE)).objects

        assert [seen.declaration.object_id for seen in before] == [_CHEST.object_id]
        assert [seen.declaration.object_id for seen in after] == [_CHEST.object_id, _HIDDEN_NICHE.object_id]

    def test_viewer_is_not_among_the_people_in_view(self) -> None:
        """見渡す本人は場面の人に入らない。alice の場面には bob と carol が、bob の場面には alice と carol が出る。"""
        world = _World(Lighting.BRIGHT)

        alice_view = _handles(_seen(world.looks_around(_ALICE)))
        bob_view = _handles(_seen(world.looks_around(_BOB)))

        assert set(alice_view) == {world.handle_of(_BOB), world.handle_of(_CAROL)}
        assert set(bob_view) == {world.handle_of(_ALICE), world.handle_of(_CAROL)}

    def test_pitch_dark_spot_shows_neither_people_objects_nor_ground_items_but_passages(self) -> None:
        """真っ暗な洞窟では、人・宝箱・地面のロープも説明も出ず、手探りで分かる通路だけが出る。"""
        world = _World(Lighting.PITCH_DARK)
        world.drops_a_rope_in_the_cave()

        surroundings = _seen(world.looks_around(_ALICE))

        assert not surroundings.shows_description
        assert surroundings.people == ()
        assert surroundings.objects == ()
        assert surroundings.ground_items == ()
        assert [p.passage.passage_id for p in surroundings.passages] == [_CAVE_TO_HUT.passage_id]

    def test_dark_spot_shows_people_as_unidentified_without_items(self) -> None:
        """暗い洞窟では、人は「誰か」として出て、手に持つ物は出ない。"""
        world = _World(Lighting.DARK)

        surroundings = _seen(world.looks_around(_ALICE))

        assert _handles(surroundings) == [None, None]
        assert all(seen.visible_items == () for seen in surroundings.people)

    def test_object_appears_with_the_look_matching_its_current_state(self) -> None:
        """宝箱は、蓋が閉じているあいだは見え方無しで、蓋を開けた後は「蓋が開いている」で出る。"""
        world = _World(Lighting.BRIGHT)
        before = _seen(world.looks_around(_ALICE)).objects

        world.change(
            lambda s: s.aggregates().object_state(_CHEST.object_id).set(_LID, ChoiceValue(ChoiceName("open")), _NOW)
        )
        after = _seen(world.looks_around(_ALICE)).objects

        assert [seen.look for seen in before] == [NoLook()]
        assert [seen.look for seen in after] == [DescriptionText("蓋が開いている")]

    def test_fallen_person_appears_among_bodies_with_everything_carried(self) -> None:
        """bob が倒れると、bob は場面の人ではなく倒れた体に出て、持ち物すべてが見える。"""
        world = _World(Lighting.BRIGHT)
        rope = world.held_items_of(_BOB)[0]
        world.change(lambda s: s.aggregates().inventory(_BOB).put_away(rope))
        world.change(_falls(_BOB))

        surroundings = _seen(world.looks_around(_ALICE))

        assert len(surroundings.people) == 1
        assert [seen.visible_items for seen in surroundings.bodies] == [world.items_of(_BOB)]

    def test_fallen_viewer_has_nothing_in_view(self) -> None:
        """倒れている alice が見渡すと、明るい洞窟でも場面は無い。"""
        world = _World(Lighting.BRIGHT)
        world.change(_falls(_ALICE))

        assert world.looks_around(_ALICE) == NothingInView()

    def test_traveling_person_has_nothing_in_view(self) -> None:
        """小屋へ向かって歩いている alice が見渡すと、場面は無い。"""
        world = _World(Lighting.BRIGHT)
        world.change(
            lambda s: (
                s.aggregates()
                .whereabouts()
                .start_travel(PersonBody(_ALICE), Route(start=_cave(Lighting.BRIGHT).spot_id, passages=(_CAVE_TO_HUT,)))
            )
        )

        assert world.looks_around(_ALICE) == NothingInView()

    def test_departed_person_does_not_appear_in_the_living_view(self) -> None:
        """去った人が動く世界で carol が死ぬと、alice の場面では carol は倒れた体として出て、去った人としては出ない。"""
        world = _World(Lighting.BRIGHT, departed_persons_act=True)
        world.change(_dies(_CAROL))

        surroundings = _seen(world.looks_around(_ALICE))

        assert len(surroundings.people) == 1
        assert len(surroundings.bodies) == 1

    def test_departed_person_sees_clearly_even_in_pitch_dark(self) -> None:
        """真っ暗な洞窟でも、去った carol が見渡すと、生きている alice と bob が見分けられて出る。"""
        world = _World(Lighting.PITCH_DARK, departed_persons_act=True)
        world.change(_dies(_CAROL))

        surroundings = _seen(world.looks_around(_CAROL))

        assert None not in _handles(surroundings)
        assert len(surroundings.people) == 2

    def test_dead_person_in_a_world_where_the_departed_do_not_act_has_nothing_in_view(self) -> None:
        """去った人が動かない世界で死んだ carol が見渡すと、場面は無い。"""
        world = _World(Lighting.BRIGHT)
        world.change(_falls(_CAROL))
        world.change(
            lambda s: s.aggregates().vitals(_CAROL).pass_time(_NOW, DeathRule(grace=Ticks(0)), s.facts().rules().hunger)
        )

        assert world.looks_around(_CAROL) == NothingInView()
