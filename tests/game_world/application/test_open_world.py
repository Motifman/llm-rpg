from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import WeatherDeclaration, WeatherState
from ai_rpg_world.game_world.domain.declaration.time_and_weather.changes_every import NoChange
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.world_contents_exception import WorldAlreadyStartedException
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    ItemSpecId,
    PersonId,
    SpotId,
    WorldId,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, PersonBody
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on
from tests.game_world.support.world_design_for_tests import (
    character,
    compose_world,
    group_decision,
    item_spec,
    nouns,
    obj,
    spot,
    world_stage,
)

_MINE_VILLAGE = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_WORLD = WorldId("world")


def _store(path: Path, design: WorldDesign) -> SqliteWorldStore:
    return SqliteWorldStore.create(
        path, world_id=_WORLD, scenario="scenario", scenario_hash="hash", design=design, random=SeedableRandomSource(0)
    )


def _opened(path: Path, design: WorldDesign) -> SqliteWorldStore:
    store = _store(path, design)
    OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
    return store


def _rows_by_kind(path: Path) -> Counter[str]:
    connection = sqlite3.connect(path)
    try:
        return Counter(kind for (kind,) in connection.execute("SELECT kind FROM world_state"))
    finally:
        connection.close()


@pytest.fixture(scope="module")
def mine_village() -> WorldDesign:
    return load_scenario(_MINE_VILLAGE).design


class _Recorder:
    def __init__(self) -> None:
        self.batches: list[tuple[DomainEvent, ...]] = []

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.batches.append(events)


def _with_lamp(person: CharacterDeclaration, held: bool) -> CharacterDeclaration:
    lamp = ItemSpecId("lamp")
    return CharacterDeclaration(
        person_id=person.person_id,
        appearance=person.appearance,
        spawn_spot=person.spawn_spot,
        initial_items=(lamp, lamp),
        initial_held=(lamp,) if held else (),
        initial_groups=(),
        knows_at_start=(),
        max_hp=person.max_hp,
        pack_capacity=person.pack_capacity,
    )


def _everything_declared() -> WorldDesign:
    meeting = group_decision("meeting")
    dawn = world_stage("dawn")
    return compose_world(
        nouns_=nouns(
            spots=(spot("hall"), spot("yard")),
            objects=(obj("well", "yard"),),
            item_specs=(item_spec("lamp"),),
            characters=(_with_lamp(character("haru", "hall"), held=True), character("mio", "yard")),
            world_stages=(dawn,),
            group_decisions=(meeting,),
        ),
        group_decision_rules=(everyone_votes_on(meeting),),
        weather=WeatherDeclaration(
            initial=WeatherType.SNOW, changes=NoChange(), announce_changes=False, obscuring=frozenset()
        ),
        initial_stage=dawn,
    )


class TestOpenMineVillage:
    """OpenWorld が廃坑の山村 v2 の宣言どおりに始まりの世界を書くことを保証する。"""

    def test_four_people_stand_at_their_declared_spots(self, tmp_path: Path, mine_village: WorldDesign) -> None:
        """開くと、4 人が宣言の出発の場所 (haru と mio は北の竪坑口、gen と sayo は南の坑口) にいる。"""
        session = _opened(tmp_path / "world.db", mine_village).session()

        whereabouts = session.facts().whereabouts()
        places = {
            person: whereabouts.location_of(PersonBody(PersonId(person))) for person in ("haru", "mio", "gen", "sayo")
        }

        assert {person: location.spot for person, location in places.items() if isinstance(location, AtSpot)} == {
            "haru": SpotId("north_shaft_head"),
            "mio": SpotId("north_shaft_head"),
            "gen": SpotId("south_adit_mouth"),
            "sayo": SpotId("south_adit_mouth"),
        }

    def test_each_person_carries_the_declared_items(self, tmp_path: Path, mine_village: WorldDesign) -> None:
        """開くと、各人の持ち物の品物の種類と数が、宣言の initial_items と同じになる。"""
        session = _opened(tmp_path / "world.db", mine_village).session()
        facts = session.facts()

        for starting in mine_village.initial_world().people:
            inventory = facts.inventory(starting.person)
            declared = Counter(spec.item_spec_id for spec in starting.items)
            assert {spec: inventory.count_of(spec) for spec in declared} == {
                spec: Count(count) for spec, count in declared.items()
            }
            assert len(inventory.items()) == sum(declared.values())

    def test_flags_and_object_states_are_as_declared(self, tmp_path: Path, mine_village: WorldDesign) -> None:
        """開くと、どの旗も宣言の initially_raised のままで、どの物の状態も宣言の initial の値になっている。"""
        session = _opened(tmp_path / "world.db", mine_village).session()
        facts = session.facts()
        now = facts.clock().now()

        for flag in mine_village.nouns.all_flags():
            assert facts.flags().is_raised(flag) is flag.initially_raised
        for declared in mine_village.nouns.all_objects():
            state = facts.object_state(declared.object_id)
            for state_key in declared.state_keys:
                assert state.value_of(state_key, now) == state_key.initial

    def test_every_declared_spot_person_and_object_can_be_read(self, tmp_path: Path, mine_village: WorldDesign) -> None:
        """開いた世界で、宣言されたどの場所の地面と探した記録、どの人の体と持ち物と知らせ、どの物の状態を引いても例外にならない。"""
        session = _opened(tmp_path / "world.db", mine_village).session()
        facts = session.facts()

        for declared_spot in mine_village.nouns.all_spots():
            facts.ground_items(declared_spot.spot_id)
            facts.search_progress(declared_spot.spot_id)
        for person in mine_village.nouns.all_characters():
            facts.vitals(person.person_id)
            facts.inventory(person.person_id)
            facts.missed_notices(person.person_id)
        for declared in mine_village.nouns.all_objects():
            facts.object_state(declared.object_id)


class TestOpenWorldWritesEveryKind:
    """OpenWorld が、変換を登録したすべての種類の集約を、宣言の分だけ書くことを保証する。"""

    def test_every_registered_kind_is_written_when_everything_is_declared(self, tmp_path: Path) -> None:
        """天候・段階・物・品物・集団の決定をすべて宣言した世界を開くと、GAME_WORLD_CODECS に登録したどの種類の行も書かれる。"""
        path = tmp_path / "world.db"

        _opened(path, _everything_declared())

        registered = {GAME_WORLD_CODECS.kind_of(memento_type) for memento_type in GAME_WORLD_CODECS.memento_types()}
        assert set(_rows_by_kind(path)) == registered

    def test_owned_kinds_are_written_once_per_declared_owner(self, tmp_path: Path) -> None:
        """場所 2 つ・人 2 人・物 1 つ・集団の決定 1 つ・品物 2 つの世界を開くと、持ち主ごとの集約がその数だけ書かれる。"""
        path = tmp_path / "world.db"

        _opened(path, _everything_declared())

        rows = _rows_by_kind(path)
        expected = {"ground_items": 2, "spot_search_progress": 2, "person_vitals": 2, "person_inventory": 2}
        expected |= {"missed_notices": 2, "object_state": 1, "group_decision": 1, "item": 2}
        assert {kind: rows[kind] for kind in expected} == expected

    def test_weather_and_stage_start_as_declared(self, tmp_path: Path) -> None:
        """初めの天候を雪、最初の段階を夜明けと宣言した世界を開くと、天候は雪、段階は夜明けから始まる。"""
        session = _opened(tmp_path / "world.db", _everything_declared()).session()

        aggregates = session.aggregates()

        assert (aggregates.weather().current(), aggregates.world_stage().current()) == (
            WeatherState(WeatherType.SNOW),
            WorldStageId("dawn"),
        )

    def test_declared_held_item_is_in_hand_and_the_rest_is_packed(self, tmp_path: Path) -> None:
        """ランプを 2 つ持ち、そのうち 1 つを手に持つと宣言した人は、開くと 1 つを手に持ち、もう 1 つを荷物に入れている。"""
        session = _opened(tmp_path / "world.db", _everything_declared()).session()

        inventory = session.facts().inventory(PersonId("haru"))

        assert (len(inventory.held_items()), len(inventory.packed_items())) == (1, 1)

    def test_items_brought_in_later_do_not_reuse_starting_item_ids(self, tmp_path: Path) -> None:
        """始まりに品物を 2 つ作った世界では、あとで持ち込む品物の ID が始まりの品物の ID と重ならない。"""
        design = _everything_declared()
        session = _opened(tmp_path / "world.db", design).session()
        starting = set(session.facts().inventory(PersonId("haru")).items())

        later = session.aggregates().bring_item_into_world(design.nouns.item_spec_of(ItemSpecId("lamp")), WorldTick(0))

        assert later not in starting


class TestOpenWorldEvents:
    """始まりの集約を作るときに出たイベント (人を置いた、品物を受け取った、など) が、開いたあとの確定の範囲に持ち越されないことを保証する (#1978 の E1)。"""

    def test_first_scope_after_opening_hands_no_events_to_receivers(
        self, tmp_path: Path, mine_village: WorldDesign
    ) -> None:
        """開いたあと、同じ世界で読むだけの確定の範囲を 1 つ回しても、始まりのイベントは受け手に 1 つも届かない。"""
        store = _opened(tmp_path / "world.db", mine_village)
        distributor = CommittedEventsDistributor()
        recorder = _Recorder()
        distributor.register_receiver(recorder)

        CommandScope(store, distributor).run(lambda session: session.facts().whereabouts())

        assert recorder.batches == []


class TestOpenWorldOnce:
    """始まりの世界を一度しか書かないことを保証する。"""

    def test_opening_a_world_that_already_holds_aggregates_is_refused(
        self, tmp_path: Path, mine_village: WorldDesign
    ) -> None:
        """一度開いた DB をもう一度開こうとすると WorldAlreadyStartedException になり、行の数は変わらない。"""
        path = tmp_path / "world.db"
        store = _opened(path, mine_village)
        before = _rows_by_kind(path)

        with pytest.raises(WorldAlreadyStartedException):
            OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=mine_village))

        assert _rows_by_kind(path) == before
