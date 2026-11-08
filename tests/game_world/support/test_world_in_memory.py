from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import pytest

from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.condition.chance_occasion import ChanceOccasion
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
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
from ai_rpg_world.game_world.domain.effect.effect_path import EffectPath
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
from ai_rpg_world.game_world.domain.whereabouts import PersonBody, Route, TravelInProgress
from ai_rpg_world.game_world.domain.world_progress import Weather, WorldStage
from tests.game_world.domain.whereabouts._builders import path, spot
from tests.game_world.support.world_in_memory import WorldInMemory

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
    rolls: Mapping[ChanceOccasion, float] = MappingProxyType({}),
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
        rolls=rolls,
    )


class TestFactsSeeWhatAggregatesChanged:
    """WorldInMemory の aggregates で集約を書き換えると、同じ世界の facts がその変化を読むことを保証する。"""

    def test_teleport_is_seen_as_the_new_spot(self) -> None:
        """広場にいる alice を井戸端へテレポートすると、facts の spot_of は井戸端を答える。"""
        world = _world()
        world.aggregates().whereabouts().place(PersonBody(_ALICE), _SQUARE)

        world.aggregates().whereabouts().teleport(PersonBody(_ALICE), _WELL_SIDE)

        assert world.facts().spot_of(PersonBody(_ALICE)) == _WELL_SIDE.spot_id

    def test_travel_is_seen_as_travel_in_progress(self) -> None:
        """広場から 2 tick かかる小道で井戸端へ歩き出した alice は、spot_of が場所でなく移動中を答える。"""
        world = _world()
        world.aggregates().whereabouts().place(PersonBody(_ALICE), _SQUARE)

        world.aggregates().whereabouts().start_travel(
            PersonBody(_ALICE), Route(start=_SQUARE.spot_id, passages=(_LANE,))
        )

        assert isinstance(world.facts().spot_of(PersonBody(_ALICE)), TravelInProgress)

    def test_life_state_starts_alive(self) -> None:
        """何もしていない alice の life_state は Alive。"""
        assert _world().facts().life_state(_ALICE) == Alive()

    def test_damage_is_seen_as_the_new_life_state(self) -> None:
        """HP 5 の alice に 5 の痛手を与えると、facts の life_state は倒れた状態を答える。"""
        world = _world()

        world.aggregates().vitals(_ALICE).take_damage(Damage(5), WorldTick(0), StruckByPerson(_BOB))

        assert world.facts().life_state(_ALICE) == Down(fell_at=WorldTick(0), cause=StruckByPerson(_BOB))

    def test_hunger_is_seen_apart_from_fatigue(self) -> None:
        """alice の空腹だけを 2 tick 進めると、hunger_of は 2、fatigue_of は 0 を答える。"""
        world = _world()

        world.aggregates().vitals(_ALICE).pass_time(WorldTick(1), _DEATH, _HUNGER)
        world.aggregates().vitals(_ALICE).pass_time(WorldTick(2), _DEATH, _HUNGER)

        assert world.facts().hunger_of(_ALICE) == HungerAmount(2)
        assert world.facts().fatigue_of(_ALICE) == FatigueAmount(0)

    def test_fatigue_is_seen_apart_from_hunger(self) -> None:
        """alice が 1 回 3 疲れる体の使い方をすると、fatigue_of は 3、hunger_of は 0 を答える。"""
        world = _world()

        world.aggregates().vitals(_ALICE).exert(_FATIGUE)

        assert world.facts().fatigue_of(_ALICE) == FatigueAmount(3)
        assert world.facts().hunger_of(_ALICE) == HungerAmount(0)

    def test_earned_gold_is_seen(self) -> None:
        """alice が 7 ゴールド得ると、facts の gold_of は 7 を答える。"""
        world = _world()

        world.aggregates().inventory(_ALICE).earn(Gold(7))

        assert world.facts().gold_of(_ALICE) == Gold(7)

    def test_decided_outcome_is_seen(self) -> None:
        """alice の結末を死に決めると、facts の outcome_of は alice に死を答える。"""
        world = _world()

        world.aggregates().outcomes().decide(_ALICE, Died())

        assert world.facts().outcome_of(_ALICE) == Died()

    def test_others_stay_undecided_until_everyone_is_decided(self) -> None:
        """alice の結末だけを決めると、bob は Undecided のままで、all_outcomes_decided は偽。"""
        world = _world()

        world.aggregates().outcomes().decide(_ALICE, Died())

        assert world.facts().outcome_of(_BOB) == Undecided()
        assert not world.facts().all_outcomes_decided()

    def test_all_outcomes_decided_when_everyone_is_decided(self) -> None:
        """alice と bob の結末を両方決めると、all_outcomes_decided は真。"""
        world = _world()

        world.aggregates().outcomes().decide(_ALICE, Died())
        world.aggregates().outcomes().decide(_BOB, Died())

        assert world.facts().all_outcomes_decided()

    def test_joined_group_is_seen(self) -> None:
        """alice が村人に入ると、facts の is_member は alice に真を、入っていない bob に偽を答える。"""
        world = _world()

        world.aggregates().membership().join(_ALICE, _VILLAGERS)

        assert world.facts().is_member(_ALICE, _VILLAGERS)
        assert not world.facts().is_member(_BOB, _VILLAGERS)

    def test_changed_object_count_is_seen(self) -> None:
        """井戸の桶の数 2 に 3 を足すと、facts の object_value は 5 を答える。"""
        world = _world(object_states=(ObjectState.open(_WELL, WorldTick(0)),))

        world.aggregates().object_state(_WELL.object_id).add_to_count(_BUCKETS, Count(3))

        assert world.facts().object_value(_BUCKETS) == CountValue(Count(5))

    def test_received_items_are_counted_by_spec(self) -> None:
        """alice がりんご 2 つと梨 1 つを受け取ると、りんごの item_count は 2。"""
        first = Item.come_into_world(ItemInstanceId("apple-1"), _APPLE, WorldTick(0))
        second = Item.come_into_world(ItemInstanceId("apple-2"), _APPLE, WorldTick(0))
        pear = Item.come_into_world(ItemInstanceId("pear-1"), _PEAR, WorldTick(0))
        world = _world(items=(first, second, pear))
        inventory = world.aggregates().inventory(_ALICE)

        inventory.receive(first.item_id, first.spec_id)
        inventory.receive(second.item_id, second.spec_id)
        inventory.receive(pear.item_id, pear.spec_id)

        assert world.facts().item_count(_ALICE, _APPLE) == Count(2)

    def test_held_item_is_seen_by_spec(self) -> None:
        """alice が梨を手に持ち、りんごを荷に入れると、is_holding は梨に真、りんごに偽を答える。"""
        apple = Item.come_into_world(ItemInstanceId("apple-1"), _APPLE, WorldTick(0))
        pear = Item.come_into_world(ItemInstanceId("pear-1"), _PEAR, WorldTick(0))
        world = _world(items=(apple, pear))
        inventory = world.aggregates().inventory(_ALICE)
        inventory.receive(apple.item_id, apple.spec_id)
        inventory.receive(pear.item_id, pear.spec_id)

        inventory.hold(pear.item_id, HandsNeeded(1))

        assert world.facts().is_holding(_ALICE, _PEAR)
        assert not world.facts().is_holding(_ALICE, _APPLE)

    def test_packed_item_is_not_held(self) -> None:
        """りんごを荷に入れただけでは、is_holding は偽を答える。"""
        apple = Item.come_into_world(ItemInstanceId("apple-1"), _APPLE, WorldTick(0))
        world = _world(items=(apple,))

        world.aggregates().inventory(_ALICE).receive(apple.item_id, apple.spec_id)

        assert not world.facts().is_holding(_ALICE, _APPLE)

    def test_entered_world_stage_is_seen_with_ticks_spent(self) -> None:
        """昼で始まった世界が tick 2 に夜へ入り tick 5 まで進むと、world_stage は夜、ticks_in_world_stage は 3 を答える。"""
        world = _world(world_stage=WorldStage.open(_WORLD, _DAY, WorldTick(0)), stage_declarations=(_DAY, _NIGHT))
        for _ in range(2):
            world.clock().advance(NoDayNight())

        world.aggregates().world_stage().enter(_NIGHT, world.facts().now())
        for _ in range(3):
            world.clock().advance(NoDayNight())

        assert world.facts().world_stage() == _NIGHT
        assert world.facts().ticks_in_world_stage() == Ticks(3)

    def test_changed_weather_is_seen(self) -> None:
        """晴れの世界で天候を雨に変えると、facts の weather は雨を答える。"""
        world = _world(weather=Weather(_WORLD, WeatherState(WeatherType.CLEAR)))

        world.aggregates().weather().change(WeatherState(WeatherType.RAIN))

        assert world.facts().weather() == WeatherState(WeatherType.RAIN)

    def test_recorded_search_is_counted(self) -> None:
        """alice が広場を 1 回探すと、alice の広場の search_count は 1、井戸端と、bob の広場は 0 を答える。"""
        world = _world()

        world.search_progress(_SQUARE.spot_id).record_search(_ALICE)

        assert world.facts().search_count(_ALICE, _SQUARE.spot_id) == Count(1)
        assert world.facts().search_count(_ALICE, _WELL_SIDE.spot_id) == Count(0)
        assert world.facts().search_count(_BOB, _SQUARE.spot_id) == Count(0)


class TestAggregatesAreTheSameInstances:
    """aggregates が同じ鍵に対して毎回同じ集約を返し、変化が消えないことを保証する。"""

    def test_ground_items_of_a_spot_keep_placed_items(self) -> None:
        """広場の地面にりんごを置くと、次に広場の地面を取り出してもりんごがある。"""
        world = _world()

        world.aggregates().ground_items(_SQUARE.spot_id).place(ItemInstanceId("apple-1"))

        assert world.aggregates().ground_items(_SQUARE.spot_id).contains(ItemInstanceId("apple-1"))

    def test_passages_and_atmospheres_are_the_same_each_time(self) -> None:
        """通路の状態と場所の雰囲気は、何度取り出しても同じ集約。"""
        world = _world()

        assert world.aggregates().passages() is world.aggregates().passages()
        assert world.aggregates().atmospheres() is world.aggregates().atmospheres()

    def test_item_is_the_one_given_to_the_world(self) -> None:
        """世界に渡したりんごは、item で取り出すと同じ集約。"""
        apple = Item.come_into_world(ItemInstanceId("apple-1"), _APPLE, WorldTick(0))
        world = _world(items=(apple,))

        assert world.aggregates().item(apple.item_id) is apple

    def test_group_decision_keeps_its_opened_state(self) -> None:
        """追放の投票を始めると、次に同じ投票を取り出しても開いている。"""
        world = _world()

        world.aggregates().group_decision(_EXILE_VOTE).start(frozenset({_ALICE, _BOB}), frozenset({_ALICE, _BOB}))

        assert world.aggregates().group_decision(_EXILE_VOTE).is_open()


class TestWorldWithoutOptionalDeclarations:
    """段階・昼夜・天候を宣言しない世界で、facts がそれぞれ「無い」を答えることを保証する。"""

    def test_no_world_stages(self) -> None:
        """段階を宣言しない世界の world_stage は NoWorldStages。"""
        assert _world().facts().world_stage() == NoWorldStages()

    def test_ticks_in_world_stage_without_stages_fails_loudly(self) -> None:
        """段階を宣言しない世界で ticks_in_world_stage を尋ねると LookupError を投げる。"""
        with pytest.raises(LookupError):
            _world().facts().ticks_in_world_stage()

    def test_world_stage_aggregate_without_stages_fails_loudly(self) -> None:
        """段階を宣言しない世界で aggregates の world_stage を取り出すと LookupError を投げる。"""
        with pytest.raises(LookupError):
            _world().aggregates().world_stage()

    def test_weather_aggregate_without_weather_fails_loudly(self) -> None:
        """天候を宣言しない世界で aggregates の weather を取り出すと LookupError を投げる。"""
        with pytest.raises(LookupError):
            _world().aggregates().weather()

    def test_no_day_night(self) -> None:
        """昼夜を宣言しない世界の time_of_day は NoDayNight。"""
        assert _world().facts().time_of_day() == NoDayNight()

    def test_no_weather(self) -> None:
        """天候を宣言しない世界の weather は NoWeather。"""
        assert _world().facts().weather() == NoWeather()


class TestClockAndPeople:
    """facts が世界の時計と世界の人を読むことを保証する。"""

    def test_now_follows_the_clock(self) -> None:
        """時計を 2 回進めると、now は tick 2。"""
        world = _world()

        world.clock().advance(NoDayNight())
        world.clock().advance(NoDayNight())

        assert world.facts().now() == WorldTick(2)

    def test_time_of_day_follows_the_declared_day(self) -> None:
        """1 日 24 tick で 6 時から始まる世界で時計を 1 回進めると、time_of_day は 7。"""
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

        assert world.facts().time_of_day() == TimeOfDay(7)

    def test_people_are_everyone_in_the_world(self) -> None:
        """alice と bob の世界の people は、渡した順の 2 人。"""
        assert _world().facts().people() == (_ALICE, _BOB)


class TestRoll:
    """facts.roll が、テストが渡した出目だけを返すことを保証する。"""

    def test_returns_the_roll_given_for_the_occasion(self) -> None:
        """tick 3 の時間の経過で根の条件に 0.25 を渡しておくと、その機会の roll は 0.25。"""
        occasion = ChanceOccasion(WorldTimePassing(WorldTick(3)), WorldTick(3), ConditionPath.root())
        world = _world(rolls={occasion: 0.25})

        assert world.facts().roll(occasion) == 0.25

    def test_rolls_for_different_positions_are_separate(self) -> None:
        """同じきっかけでも、条件の根と効果の根には別々の出目を渡せる。"""
        trigger = WorldTimePassing(WorldTick(3))
        on_condition = ChanceOccasion(trigger, WorldTick(3), ConditionPath.root())
        on_effect = ChanceOccasion(trigger, WorldTick(3), EffectPath.root())
        world = _world(rolls={on_condition: 0.1, on_effect: 0.9})

        assert world.facts().roll(on_condition) == 0.1
        assert world.facts().roll(on_effect) == 0.9

    def test_occasion_without_a_given_roll_fails_loudly(self) -> None:
        """出目を渡していない機会の roll は、適当な値を返さず LookupError を投げる。"""
        occasion = ChanceOccasion(WorldTimePassing(WorldTick(3)), WorldTick(3), ConditionPath.root())

        with pytest.raises(LookupError):
            _world().facts().roll(occasion)
