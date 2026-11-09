from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItems,
    ObjectState,
    PersonInventory,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.people import PeopleRegister
from ai_rpg_world.game_world.domain.person import GroupMembership, PersonOutcomes, PersonVitals
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    DescriptionText,
    FlagId,
    HitPoints,
    PersonId,
    SpotId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import PassageStates, SpotAtmospheres, Whereabouts
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, WorldClock
from ai_rpg_world.game_world.domain.world_records import LatestActions, MissedNotices, ScenarioProgress, WorldFlags
from ai_rpg_world.game_world.infrastructure.world.in_memory_world import InMemoryWorld
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from tests.game_world.support.world_design_for_tests import group_decision, item_spec, obj
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_WORLD = WorldId("mine_village")
_HANA = PersonId("hana")
_SHAFT = SpotId("shaft")
_GATE_OPEN = FlagDeclaration(FlagId("gate_open"), DescriptionText("門が開いた"), initially_raised=False)


_NO_KEYED_AGGREGATES: dict[str, tuple[object, ...]] = {
    "vitals": (),
    "inventories": (),
    "items": (),
    "object_states": (),
    "ground_items": (),
    "search_progresses": (),
    "missed_notices": (),
    "group_decisions": (),
}


def _world(**keyed_aggregates: tuple[object, ...]) -> InMemoryWorld:
    return InMemoryWorld(
        rules=world_rules_for_tests(),
        nouns=DeclaredNouns(
            flags=(_GATE_OPEN,),
            spots=(),
            passages=(),
            objects=(),
            item_specs=(),
            groupings=(),
            groups=(),
            characters=(),
            world_stages=(),
            group_decisions=(),
            sections=(),
            outcomes=(),
        ),
        day_night=NoDayNight(),
        random=SeedableRandomSource(seed=1),
        people=(_HANA,),
        people_register=PeopleRegister(_WORLD, ()),
        whereabouts=Whereabouts(_WORLD),
        passages=PassageStates(_WORLD, ()),
        atmospheres=SpotAtmospheres(_WORLD, ()),
        outcomes=PersonOutcomes(_WORLD, (_HANA,)),
        membership=GroupMembership(_WORLD),
        clock=WorldClock(_WORLD),
        weather=NoWeather(),
        world_stage=NoWorldStages(),
        flags=WorldFlags(_WORLD),
        scenario_progress=ScenarioProgress(_WORLD),
        latest_actions=LatestActions(_WORLD),
        **(_NO_KEYED_AGGREGATES | keyed_aggregates),
    )


class TestInMemoryWorldSharesAggregates:
    """InMemoryWorld が、効果の入口で書き換えた集約を条件の入口からそのまま読ませることを保証する。"""

    def test_flag_raised_through_aggregates_is_read_as_raised_through_facts(self) -> None:
        """aggregates() の flags で旗を立てると、facts() の flags からその旗が立っていると読める。"""
        world = _world()

        world.aggregates().flags().raise_flag(_GATE_OPEN, WorldTimePassing(WorldTick(1)))

        assert world.facts().flags().is_raised(_GATE_OPEN)

    def test_clock_advanced_through_world_moves_now_read_through_facts(self) -> None:
        """入れ物の clock() で時計を 1 つ進めると、facts().now() が tick 1 を返す。"""
        world = _world()

        world.clock().advance(NoDayNight())

        assert world.facts().now() == WorldTick(1)


class TestInMemoryWorldBringsItemsInAndOut:
    """InMemoryWorld が、世界に入れた品物を引けるようにし、世界から出した品物を引けなくすることを保証する。"""

    def test_item_brought_into_world_is_read_through_facts_with_its_spec(self) -> None:
        """bring_item_into_world で入れた品物は、返された ID で facts() から引け、入れた種類を答える。"""
        world = _world()
        lamp = item_spec("lamp")

        item = world.aggregates().bring_item_into_world(lamp, WorldTick(0))

        assert world.facts().item(item).spec_id == lamp.item_spec_id

    def test_item_taken_out_of_world_raises_aggregate_not_in_world(self) -> None:
        """take_item_out_of_world で出した品物を facts() から引くと AggregateNotInWorldException を投げる。"""
        world = _world()
        item = world.aggregates().bring_item_into_world(item_spec("lamp"), WorldTick(0))

        world.aggregates().take_item_out_of_world(item)

        with pytest.raises(AggregateNotInWorldException):
            world.facts().item(item)


class TestInMemoryWorldFindsAggregatesByOwner:
    """InMemoryWorld が、持ち主ごとの集約を、その持ち主で引いたときに入れたものそのものを返すことを保証する。"""

    def test_each_keyed_aggregate_is_found_by_its_owner_through_aggregates(self) -> None:
        """人・場所・物・集団の決定ごとの集約を 1 つずつ入れると、aggregates() からその持ち主で引いて同じものが返る。"""
        mine_gate = obj("mine_gate", at_spot="shaft")
        vote = group_decision("vote")
        vitals = PersonVitals(_HANA, HitPoints(10, 10))
        inventory = PersonInventory(_HANA, Capacity(5))
        object_state = ObjectState(mine_gate, WorldTick(0))
        ground = GroundItems(_SHAFT)
        search = SpotSearchProgress(_SHAFT)
        notices = MissedNotices(_HANA)
        decision = GroupDecision(vote)
        world = _world(
            vitals=(vitals,),
            inventories=(inventory,),
            object_states=(object_state,),
            ground_items=(ground,),
            search_progresses=(search,),
            missed_notices=(notices,),
            group_decisions=(decision,),
        )

        found = world.aggregates()

        assert found.vitals(_HANA) is vitals
        assert found.inventory(_HANA) is inventory
        assert found.object_state(mine_gate.object_id) is object_state
        assert found.ground_items(_SHAFT) is ground
        assert found.search_progress(_SHAFT) is search
        assert found.missed_notices(_HANA) is notices
        assert found.group_decision(vote) is decision


class TestInMemoryWorldDoesNotCreateMissingAggregates:
    """InMemoryWorld が、入っていない集約を引かれても作らず、ドメイン例外で無いことを伝えることを保証する。"""

    def test_inventory_of_person_without_one_raises_aggregate_not_in_world(self) -> None:
        """持ち物を入れていない人の inventory を aggregates() から引くと AggregateNotInWorldException を投げる。"""
        world = _world()

        with pytest.raises(AggregateNotInWorldException):
            world.aggregates().inventory(_HANA)

    def test_ground_items_of_spot_without_one_raises_and_stays_missing(self) -> None:
        """地面の品物を入れていない場所を facts() から引くと例外を投げ、そのあと aggregates() から引いても例外のまま。"""
        world = _world()

        with pytest.raises(AggregateNotInWorldException):
            world.facts().ground_items(_SHAFT)
        with pytest.raises(AggregateNotInWorldException):
            world.aggregates().ground_items(_SHAFT)

    def test_weather_of_world_without_weather_raises_through_aggregates_but_reads_no_weather(self) -> None:
        """天候を宣言しない世界では、aggregates().weather() は例外を投げ、facts().weather() は NoWeather を返す。"""
        world = _world()

        with pytest.raises(AggregateNotInWorldException):
            world.aggregates().weather()
        assert world.facts().weather() == NoWeather()


class TestInMemoryWorldRejectsDuplicatedAggregates:
    """InMemoryWorld が、同じ持ち主の集約を 2 つ渡されたとき、片方を黙って捨てないことを保証する。"""

    def test_two_inventories_of_one_person_raise_value_error(self) -> None:
        """同じ人の PersonInventory を 2 つ渡すと、組み立てるときに ValueError を投げる。"""
        with pytest.raises(ValueError):
            _world(inventories=(PersonInventory(_HANA, Capacity(5)), PersonInventory(_HANA, Capacity(5))))
