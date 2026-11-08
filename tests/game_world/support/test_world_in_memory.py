from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.character.group_declaration import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    CountStateKind,
    CountValue,
    ItemSpecDeclaration,
    NotALightSource,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress import (
    AllActionsAllowed,
    GroupDecisionDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseDeclaration,
    DayPhaseName,
    NoDayNight,
    NoWeather,
    TimeOfDay,
    WeatherState,
    WeatherType,
)
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.objects_and_items import Item, ObjectState, PersonInventory
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import (
    Alive,
    Died,
    Down,
    GroupMembership,
    PersonVitals,
    StruckByPerson,
    Undecided,
)
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel, FatigueLevelName, FatigueRule
from ai_rpg_world.game_world.domain.rules.hunger_rule import (
    HungerLevel,
    HungerLevelName,
    HungerRule,
    NoStarvationDamage,
)
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Count,
    Damage,
    DescriptionText,
    DisplayName,
    FatigueAmount,
    Gold,
    GroupDecisionId,
    GroupId,
    GroupingId,
    HandsNeeded,
    HitPoints,
    HungerAmount,
    ItemSpecId,
    ObjectId,
    PersonId,
    SpotId,
    StateKeyId,
    Ticks,
    WorldId,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, OpenArea, PersonBody, Route, TravelInProgress
from ai_rpg_world.game_world.domain.world_progress import Weather, WorldStage
from tests.game_world.domain.whereabouts._builders import path, spot
from tests.game_world.support.world_in_memory import WorldInMemory
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_WORLD = WorldId("island")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_SQUARE = spot("square")
_WELL_SIDE = spot("well_side")
_LANE = path("lane", "square", "well_side", ticks=2)
_PEAR = ItemSpecDeclaration(
    item_spec_id=ItemSpecId("pear"),
    name=DisplayName("梨"),
    description=DescriptionText("黄色い梨"),
    state_keys=(),
    lights_up=NotALightSource(),
)
_APPLE = ItemSpecDeclaration(
    item_spec_id=ItemSpecId("apple"),
    name=DisplayName("りんご"),
    description=DescriptionText("赤いりんご"),
    state_keys=(),
    lights_up=NotALightSource(),
)
_BUCKETS = ObjectStateKeyDeclaration(
    object_id=ObjectId("well"), key=StateKeyId("buckets"), kind=CountStateKind(), initial=CountValue(Count(2))
)
_WELL = ObjectDeclaration(
    object_id=ObjectId("well"),
    spot_id=SpotId("square"),
    name=DisplayName("井戸"),
    description=DescriptionText("古い井戸"),
    appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=False),
    state_keys=(_BUCKETS,),
)
_VILLAGERS = GroupDeclaration(
    group_id=GroupId("villagers"),
    grouping=GroupingDeclaration(
        grouping_id=GroupingId("side"), name=DisplayName("陣営"), visibility=MembershipVisibility.NOBODY, changes=True
    ),
    name=DisplayName("村人"),
    members_know_each_other=False,
    shared_description=NoSharedDescription(),
)
_EXILE_VOTE = GroupDecisionDeclaration(
    decision_id=GroupDecisionId("exile_vote"),
    name=DisplayName("追放の投票"),
    abstain_allowed=True,
    reveals_ballots=False,
)


def _stage(stage_id: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(stage_id),
        name=DisplayName(stage_id),
        description=DescriptionText(f"{stage_id}の段階"),
        allowed_actions=AllActionsAllowed(),
    )


_DEATH = DeathRule(grace=Ticks(2))
_HUNGER = HungerRule(
    per_tick=HungerAmount(1),
    limit=HungerAmount(10),
    starvation_damage=NoStarvationDamage(),
    levels=(HungerLevel(starts_at=HungerAmount(0), name=HungerLevelName("満腹")),),
)
_FATIGUE = FatigueRule(
    per_exertion=FatigueAmount(3),
    limit=FatigueAmount(10),
    levels=(FatigueLevel(starts_at=FatigueAmount(0), name=FatigueLevelName("元気")),),
)
_DAY = _stage("day")
_NIGHT = _stage("night")


def _world(
    *,
    items: tuple[Item, ...] = (),
    object_states: tuple[ObjectState, ...] = (),
    world_stage: WorldStage | NoWorldStages = NoWorldStages(),
    stage_declarations: tuple[WorldStageDeclaration, ...] = (),
    day_night: DayNightDeclaration | NoDayNight = NoDayNight(),
    weather: Weather | NoWeather = NoWeather(),
    fractions: tuple[float, ...] = (),
) -> WorldInMemory:
    return WorldInMemory(
        world=_WORLD,
        people=(_ALICE, _BOB),
        spots=(_SQUARE, _WELL_SIDE),
        passages=(_LANE,),
        vitals=(
            PersonVitals.start(_ALICE, HitPoints(current=5, maximum=5)),
            PersonVitals.start(_BOB, HitPoints(current=5, maximum=5)),
        ),
        inventories=(PersonInventory(_ALICE, Capacity(5)),),
        items=items,
        object_states=object_states,
        world_stage=world_stage,
        stage_declarations=stage_declarations,
        day_night=day_night,
        weather=weather,
        fractions=fractions,
    )


class TestFactsSeeWhatAggregatesChanged:
    """WorldInMemory の aggregates で集約を書き換えると、同じ世界の facts の読む型がその変化を読むことを保証する。"""

    def test_teleport_is_seen_as_the_new_spot(self) -> None:
        """広場にいる alice を井戸端へテレポートすると、facts の whereabouts は alice が井戸端にいると答える。"""
        world = _world()
        world.aggregates().whereabouts().place(PersonBody(_ALICE), _SQUARE)

        world.aggregates().whereabouts().teleport(PersonBody(_ALICE), _WELL_SIDE)

        assert world.facts().whereabouts().location_of(PersonBody(_ALICE)) == AtSpot(
            spot=_WELL_SIDE.spot_id, section=OpenArea()
        )

    def test_travel_is_seen_as_travel_in_progress(self) -> None:
        """広場から 2 tick かかる小道で井戸端へ歩き出した alice は、facts の whereabouts で移動中と読める。"""
        world = _world()
        world.aggregates().whereabouts().place(PersonBody(_ALICE), _SQUARE)

        world.aggregates().whereabouts().start_travel(
            PersonBody(_ALICE), Route(start=_SQUARE.spot_id, passages=(_LANE,))
        )

        assert isinstance(world.facts().whereabouts().location_of(PersonBody(_ALICE)), TravelInProgress)

    def test_damage_is_seen_as_the_new_life_state(self) -> None:
        """HP 5 の alice に 5 の痛手を与えると、facts の vitals は倒れた状態を答える。"""
        world = _world()
        assert world.facts().vitals(_ALICE).life_state() == Alive()

        world.aggregates().vitals(_ALICE).take_damage(Damage(5), WorldTick(0), StruckByPerson(_BOB))

        assert world.facts().vitals(_ALICE).life_state() == Down(fell_at=WorldTick(0), cause=StruckByPerson(_BOB))

    def test_hunger_and_fatigue_are_seen(self) -> None:
        """alice の空腹を 2 tick 進め、1 回 3 疲れる体の使い方をすると、facts の vitals は空腹 2、疲れ 3 を答える。"""
        world = _world()

        world.aggregates().vitals(_ALICE).pass_time(WorldTick(1), _DEATH, _HUNGER)
        world.aggregates().vitals(_ALICE).pass_time(WorldTick(2), _DEATH, _HUNGER)
        world.aggregates().vitals(_ALICE).exert(_FATIGUE)

        assert world.facts().vitals(_ALICE).hunger() == HungerAmount(2)
        assert world.facts().vitals(_ALICE).fatigue() == FatigueAmount(3)

    def test_earned_gold_is_seen(self) -> None:
        """alice が 7 ゴールド得ると、facts の inventory は 7 ゴールドを答える。"""
        world = _world()

        world.aggregates().inventory(_ALICE).earn(Gold(7))

        assert world.facts().inventory(_ALICE).available_gold() == Gold(7)

    def test_received_items_are_counted_by_spec(self) -> None:
        """alice がりんご 2 つと梨 1 つを受け取ると、facts の inventory はりんごを 2 つと数える。"""
        world = _world()
        inventory = world.aggregates().inventory(_ALICE)
        for spec in (_APPLE, _APPLE, _PEAR):
            item = world.aggregates().bring_item_into_world(spec, WorldTick(0))
            inventory.receive(item, spec.item_spec_id)

        assert world.facts().inventory(_ALICE).count_of(_APPLE.item_spec_id) == Count(2)

    def test_held_item_is_seen(self) -> None:
        """alice が梨を手に持つと、facts の inventory の手の物は梨だけになる。"""
        pear = Item.come_into_world(ItemInstanceId("pear-1"), _PEAR, WorldTick(0))
        world = _world(items=(pear,))
        world.aggregates().inventory(_ALICE).receive(pear.item_id, pear.spec_id)

        world.aggregates().inventory(_ALICE).hold(pear.item_id, HandsNeeded(1))

        assert world.facts().inventory(_ALICE).held_items() == (pear.item_id,)

    def test_decided_outcome_is_seen(self) -> None:
        """alice の結末だけを死に決めると、facts の outcomes は alice に死、bob に Undecided を答え、全員は決まっていない。"""
        world = _world()

        world.aggregates().outcomes().decide(_ALICE, Died())

        assert world.facts().outcomes().outcome_of(_ALICE) == Died()
        assert world.facts().outcomes().outcome_of(_BOB) == Undecided()
        assert not world.facts().outcomes().all_decided()

    def test_joined_group_is_seen(self) -> None:
        """alice が村人に入ると、facts の membership は alice に真を、入っていない bob に偽を答える。"""
        world = _world()

        world.aggregates().membership().join(_ALICE, _VILLAGERS)

        assert world.facts().membership().is_member(_ALICE, _VILLAGERS)
        assert not world.facts().membership().is_member(_BOB, _VILLAGERS)

    def test_changed_object_count_is_seen(self) -> None:
        """井戸の桶の数 2 に 3 を足すと、facts の object_state は 5 を答える。"""
        world = _world(object_states=(ObjectState.from_declaration(_WELL, WorldTick(0)),))

        world.aggregates().object_state(_WELL.object_id).add_to_count(_BUCKETS, Count(3))

        assert world.facts().object_state(_WELL.object_id).value_of(_BUCKETS, WorldTick(0)) == CountValue(Count(5))

    def test_entered_world_stage_is_seen(self) -> None:
        """昼で始まった世界が tick 2 に夜へ入ると、facts の world_stage は夜と、入った tick 2 を答える。"""
        world = _world(
            world_stage=WorldStage.from_initial_stage(_WORLD, _DAY, WorldTick(0)), stage_declarations=(_DAY, _NIGHT)
        )
        for _ in range(2):
            world.clock().advance(NoDayNight())

        world.aggregates().world_stage().enter(_NIGHT, world.facts().now())

        stage = world.facts().world_stage()
        assert not isinstance(stage, NoWorldStages)
        assert stage.current() == _NIGHT.stage_id
        assert stage.entered_at() == WorldTick(2)

    def test_changed_weather_is_seen(self) -> None:
        """晴れの世界で天候を雨に変えると、facts の weather は雨を答える。"""
        world = _world(weather=Weather(_WORLD, WeatherState(WeatherType.CLEAR)))

        world.aggregates().weather().change(WeatherState(WeatherType.RAIN))

        weather = world.facts().weather()
        assert not isinstance(weather, NoWeather)
        assert weather.current() == WeatherState(WeatherType.RAIN)

    def test_recorded_search_is_counted(self) -> None:
        """alice が広場を 1 回探すと、facts の search_progress は alice の広場に 1、井戸端と、bob の広場に 0 を答える。"""
        world = _world()

        world.aggregates().search_progress(_SQUARE.spot_id).record_search(_ALICE)

        assert world.facts().search_progress(_SQUARE.spot_id).search_count(_ALICE) == Count(1)
        assert world.facts().search_progress(_WELL_SIDE.spot_id).search_count(_ALICE) == Count(0)
        assert world.facts().search_progress(_SQUARE.spot_id).search_count(_BOB) == Count(0)

    def test_placed_ground_item_is_seen(self) -> None:
        """広場の地面にりんごを置くと、facts の ground_items は広場にりんごがあると答える。"""
        world = _world()

        world.aggregates().ground_items(_SQUARE.spot_id).place(ItemInstanceId("apple-1"))

        assert world.facts().ground_items(_SQUARE.spot_id).contains(ItemInstanceId("apple-1"))

    def test_opened_group_decision_is_seen(self) -> None:
        """追放の投票を始めると、facts の group_decision は開いていると答える。"""
        world = _world()

        world.aggregates().group_decision(_EXILE_VOTE).start(frozenset({_ALICE, _BOB}), frozenset({_ALICE, _BOB}))

        assert world.facts().group_decision(_EXILE_VOTE).is_open()


class TestItemsComingIntoAndLeavingTheWorld:
    """bring_item_into_world と take_item_out_of_world が、品物を作って登録し、登録から外すことを保証する。"""

    def test_each_brought_item_gets_its_own_id(self) -> None:
        """りんごを 2 回世界に出すと、別々の ID の品物になり、どちらも facts の item でりんごとして引ける。"""
        world = _world()

        first = world.aggregates().bring_item_into_world(_APPLE, WorldTick(0))
        second = world.aggregates().bring_item_into_world(_APPLE, WorldTick(0))

        assert first != second
        assert world.facts().item(first).spec_id == _APPLE.item_spec_id
        assert world.facts().item(second).spec_id == _APPLE.item_spec_id

    def test_brought_item_ages_from_when_it_came(self) -> None:
        """tick 2 に世界に出した梨は、tick 5 に 3 tick 経っている。"""
        world = _world()

        pear = world.aggregates().bring_item_into_world(_PEAR, WorldTick(2))

        assert world.facts().item(pear).age(WorldTick(5)) == Ticks(3)

    def test_item_taken_out_can_no_longer_be_found(self) -> None:
        """世界に出したりんごを世界から消すと、facts の item で引くと LookupError を投げる。"""
        world = _world()
        apple = world.aggregates().bring_item_into_world(_APPLE, WorldTick(0))

        world.aggregates().take_item_out_of_world(apple)

        with pytest.raises(LookupError):
            world.facts().item(apple)


class TestAggregatesAreTheSameInstances:
    """aggregates が同じ鍵に対して毎回同じ集約を返し、変化が消えないことを保証する。"""

    def test_passages_and_atmospheres_are_the_same_each_time(self) -> None:
        """通路の状態と場所の雰囲気は、何度取り出しても同じ集約。"""
        world = _world()

        assert world.aggregates().passages() is world.aggregates().passages()
        assert world.aggregates().atmospheres() is world.aggregates().atmospheres()

    def test_flags_are_the_same_aggregate_facts_read(self) -> None:
        """旗は、aggregates から何度取り出しても同じ集約で、facts の flags もその集約を読む。"""
        world = _world()

        assert world.aggregates().flags() is world.aggregates().flags()
        assert world.facts().flags() is world.aggregates().flags()

    def test_scenario_progress_and_latest_actions_are_kept_by_the_world(self) -> None:
        """出来事の帳簿と最後の行為は、世界が 1 つずつ持ち、facts は何度読んでも同じ集約を返す。"""
        world = _world()

        assert world.facts().scenario_progress() is world.facts().scenario_progress()
        assert world.facts().latest_actions() is world.facts().latest_actions()

    def test_item_is_the_one_given_to_the_world(self) -> None:
        """世界に渡したりんごは、item で取り出すと同じ集約。"""
        apple = Item.come_into_world(ItemInstanceId("apple-1"), _APPLE, WorldTick(0))
        world = _world(items=(apple,))

        assert world.aggregates().item(apple.item_id) is apple


class TestWorldWithoutOptionalDeclarations:
    """段階・昼夜・天候を宣言しない世界で、facts がそれぞれ「無い」を答えることを保証する。"""

    def test_no_world_stages(self) -> None:
        """段階を宣言しない世界の world_stage は NoWorldStages。"""
        assert _world().facts().world_stage() == NoWorldStages()

    def test_world_stage_aggregate_without_stages_fails_loudly(self) -> None:
        """段階を宣言しない世界で aggregates の world_stage を取り出すと LookupError を投げる。"""
        with pytest.raises(LookupError):
            _world().aggregates().world_stage()

    def test_weather_aggregate_without_weather_fails_loudly(self) -> None:
        """天候を宣言しない世界で aggregates の weather を取り出すと LookupError を投げる。"""
        with pytest.raises(LookupError):
            _world().aggregates().weather()

    def test_no_day_night(self) -> None:
        """昼夜を宣言しない世界の day_night は NoDayNight。"""
        assert _world().facts().day_night() == NoDayNight()

    def test_no_weather(self) -> None:
        """天候を宣言しない世界の weather は NoWeather。"""
        assert _world().facts().weather() == NoWeather()


class TestClockPeopleAndNouns:
    """facts が世界の時計・昼夜の宣言・世界の人・名詞の宣言を読むことを保証する。"""

    def test_now_follows_the_clock(self) -> None:
        """時計を 2 回進めると、now と clock の now は tick 2。"""
        world = _world()

        world.clock().advance(NoDayNight())
        world.clock().advance(NoDayNight())

        assert world.facts().now() == WorldTick(2)
        assert world.facts().clock().now() == WorldTick(2)

    def test_time_of_day_follows_the_declared_day(self) -> None:
        """1 日 24 tick で 6 時から始まる世界で時計を 1 回進めると、facts の day_night はその宣言で、clock の time_of_day は 7。"""
        day_night = DayNightDeclaration(
            ticks_per_day=Ticks(24),
            starts_at=TimeOfDay(6),
            phases=(
                DayPhaseDeclaration(
                    name=DayPhaseName("昼"), begins_at=TimeOfDay(6), dark=False, announcement=NoAnnouncement()
                ),
            ),
        )
        world = _world(day_night=day_night)

        world.clock().advance(day_night)

        assert world.facts().day_night() == day_night
        assert world.facts().clock().time_of_day(day_night) == TimeOfDay(7)

    def test_rules_are_the_given_world_rules(self) -> None:
        """渡した世界の規則を、facts の rules がそのまま答える。"""
        rules = world_rules_for_tests()
        world = WorldInMemory(world=_WORLD, rules=rules)

        assert world.facts().rules() is rules

    def test_people_are_everyone_in_the_world(self) -> None:
        """alice と bob の世界の people は、渡した順の 2 人。"""
        assert _world().facts().people() == (_ALICE, _BOB)

    def test_nouns_know_the_declared_spots(self) -> None:
        """広場と井戸端を宣言した世界の nouns は、広場の名前から広場の宣言を引ける。"""
        at = DesignLocation("test_world", "nouns", "spot")

        assert _world().facts().nouns().spot("square", at) == _SQUARE


class TestRandom:
    """facts.random が、テストが並べた値を引いた順に返すことを保証する。"""

    def test_returns_the_given_fractions_in_order(self) -> None:
        """0.25、0.9 を並べると、1 回目に 0.25、2 回目に 0.9 を返す。"""
        world = _world(fractions=(0.25, 0.9))

        assert world.facts().random().next_fraction() == 0.25
        assert world.facts().random().next_fraction() == 0.9

    def test_drawing_past_the_given_fractions_fails_loudly(self) -> None:
        """並べた値を引き尽くしたあとに引くと、適当な値を返さず LookupError を投げる。"""
        world = _world(fractions=(0.5,))
        world.facts().random().next_fraction()

        with pytest.raises(LookupError):
            world.facts().random().next_fraction()
