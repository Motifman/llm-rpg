from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses, perceivers_in_world
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    LastsIndefinitely,
    LitWhen,
)
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseDeclaration,
    NoWeather,
    TimeOfDay,
    WeatherDeclaration,
    WeatherState,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather.changes_every import NoChange
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_name import DayPhaseName
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.objects_and_items import Item, ItemInstanceId, PersonInventory
from ai_rpg_world.game_world.domain.people import NoVisibleName, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import DeadPerceiver, DepartedPerceiver, LivingPerceiver
from ai_rpg_world.game_world.domain.perception.perceiver import PersonWhoLeftTheWorld
from ai_rpg_world.game_world.domain.person import Alive, DeclaredOutcome, Down, PersonVitals
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.sound import Loudness, NotReached, SoundLevel
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Damage,
    DescriptionText,
    DisplayName,
    HitPoints,
    ItemSpecId,
    OutcomeId,
    PersonId,
    StateKeyId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.hands_needed import HandsNeeded
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, DepartedPerson, OpenArea, PersonBody
from ai_rpg_world.game_world.domain.world_progress import Weather
from tests.game_world.domain.whereabouts._builders import door, path
from tests.game_world.support.world_design_for_tests import character, spot
from tests.game_world.support.world_in_memory import world_in_memory
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_WORLD = WorldId("perception_world")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_SQUARE = spot("square")
_HALL = spot("hall")
_CELLAR = spot("cellar")

_WICK = ItemStateKeyDeclaration(
    item_spec_id=ItemSpecId("lantern"),
    key=StateKeyId("wick"),
    kind=ChoiceStateKind(choices=(ChoiceName("unlit"), ChoiceName("lit"))),
    initial=ChoiceValue(ChoiceName("lit")),
)
_LIT_LANTERN = ItemSpecDeclaration(
    item_spec_id=ItemSpecId("lantern"),
    name=DisplayName("カンテラ"),
    description=DescriptionText("灯った手提げの明かり"),
    state_keys=(_WICK,),
    lights_up=LitWhen(_WICK.key, ChoiceValue(ChoiceName("lit"))),
    hands_needed=HandsNeeded(1),
    lasts=LastsIndefinitely(),
)

_NIGHT_FROM_THE_START = DayNightDeclaration(
    ticks_per_day=Ticks(4),
    starts_at=TimeOfDay(0),
    phases=(
        DayPhaseDeclaration(
            name=DayPhaseName("夜"),
            display_name=DisplayName("夜"),
            begins_at=TimeOfDay(0),
            dark=True,
            announcement=NoAnnouncement(),
            audience=EveryoneAwake(),
        ),
    ),
)


def _lit_as(lighting: Lighting, *, outdoor: bool = False) -> SpotDeclaration:
    return replace(_SQUARE, atmosphere=replace(_SQUARE.atmosphere, lighting=lighting, outdoor=outdoor))


def _vitals(person: PersonId) -> PersonVitals:
    return PersonVitals.start(person, HitPoints(current=10, maximum=10))


def _placed(world: WorldSession, person: PersonId, at: SpotDeclaration) -> WorldSession:
    world.aggregates().whereabouts().place(PersonBody(person), at)
    return world


def _with_lantern(where_kept: str) -> WorldSession:
    lantern = Item.come_into_world(ItemInstanceId("lantern-1"), _LIT_LANTERN, WorldTick(0))
    world = world_in_memory(
        world=_WORLD,
        people=(_ALICE,),
        spots=(_lit_as(Lighting.PITCH_DARK), _CELLAR),
        item_specs=(_LIT_LANTERN,),
        vitals=(_vitals(_ALICE),),
        inventories=(PersonInventory.start(_ALICE, Capacity(5)),),
        items=(lantern,),
    )
    _placed(world, _ALICE, _lit_as(Lighting.PITCH_DARK))
    inventory = world.aggregates().inventory(_ALICE)
    inventory.receive(lantern.item_id, lantern.spec_id)
    if where_kept == "hand":
        inventory.hold(lantern.item_id, HandsNeeded(1))
    return world


class TestLightingAt:
    """WorldPerceptionSenses.lighting_at が、その場所の明るさの材料から決まる明るさを返すことを保証する。"""

    def test_lighting_at_follows_the_lighting_conditions_of_the_spot(self) -> None:
        """真っ暗な広場でも、そこにいる人が灯ったカンテラを手に持っていれば、広場の明るさは薄暗い。"""
        world = _with_lantern("hand")

        lighting = WorldPerceptionSenses(world.facts()).lighting_at(_SQUARE.spot_id)

        assert lighting is Lighting.DUSKY


class TestReachOf:
    """WorldPerceptionSenses.reach_of が、今の通路の状態と世界の聞こえ方の値で、音の届き方を決めることを保証する。"""

    def test_sound_reaches_the_next_spot_weakened_by_one_passage(self) -> None:
        """広場のとても大きい音 (90) は、開いた道の先の広間に、通路 1 本ぶん (15) 弱まって 75 で届く。"""
        world = world_in_memory(world=_WORLD, spots=(_SQUARE, _HALL), passages=(path("square_hall", "square", "hall"),))

        reach = WorldPerceptionSenses(world.facts()).reach_of(_SQUARE.spot_id, Loudness.VERY_LOUD)

        assert reach.level_at(_HALL.spot_id) == SoundLevel(75)

    def test_closed_door_weakens_the_sound_further(self) -> None:
        """閉じた扉 (減衰 20) の先の広間には、とても大きい音が 90 - 15 - 20 = 55 で届く。"""
        world = world_in_memory(world=_WORLD, spots=(_SQUARE, _HALL), passages=(door("hall_door", "square", "hall"),))

        reach = WorldPerceptionSenses(world.facts()).reach_of(_SQUARE.spot_id, Loudness.VERY_LOUD)

        assert reach.level_at(_HALL.spot_id) == SoundLevel(55)

    def test_sound_does_not_pass_a_removed_passage(self) -> None:
        """無くなった道の先の広間には、とても大きい音も届かない。"""
        tunnel = path("square_hall", "square", "hall")
        world = world_in_memory(world=_WORLD, spots=(_SQUARE, _HALL), passages=(tunnel,))
        world.aggregates().passages().remove(tunnel)

        reach = WorldPerceptionSenses(world.facts()).reach_of(_SQUARE.spot_id, Loudness.VERY_LOUD)

        assert reach.level_at(_HALL.spot_id) == NotReached()

    def test_sound_does_not_pass_a_passage_not_yet_revealed(self) -> None:
        """現れる前の道の先の広間には、とても大きい音も届かない。"""
        secret = path("square_hall", "square", "hall", hidden_until_revealed=True)
        world = world_in_memory(world=_WORLD, spots=(_SQUARE, _HALL), passages=(secret,))

        reach = WorldPerceptionSenses(world.facts()).reach_of(_SQUARE.spot_id, Loudness.VERY_LOUD)

        assert reach.level_at(_HALL.spot_id) == NotReached()


class TestViewFor:
    """WorldPerceptionSenses.view_for が、見る人が最初から知っている相手にだけ名前を見せることを保証する。"""

    def test_only_people_known_at_start_are_shown_by_name(self) -> None:
        """alice が bob を最初から知っているとき、alice から見た bob は名前つき、bob から見た alice は見た目だけになる。"""
        alice = replace(character("alice", "square"), knows_at_start=(_BOB,))
        world = world_in_memory(world=_WORLD, spots=(_SQUARE,), characters=(alice, character("bob", "square")))
        world.people_register().name(_BOB, DisplayName("ボブ"))
        senses = WorldPerceptionSenses(world.facts())

        assert senses.view_for(_ALICE).ref_of(_BOB).visible_name == DisplayName("ボブ")
        assert senses.view_for(_BOB).ref_of(_ALICE).visible_name == NoVisibleName()


class TestPerceiversInWorld:
    """perceivers_in_world が、世界の人それぞれを、生死と居場所に合った知覚する人にすることを保証する。"""

    def test_living_person_perceives_where_the_body_is(self) -> None:
        """生きている人は、体のいる場所で、耳を澄ましていない LivingPerceiver になる。"""
        world = _placed(
            world_in_memory(world=_WORLD, people=(_ALICE,), spots=(_SQUARE,), vitals=(_vitals(_ALICE),)),
            _ALICE,
            _SQUARE,
        )

        perceivers = perceivers_in_world(world.facts())

        assert perceivers == (
            LivingPerceiver(
                person=_ALICE, life=Alive(), location=AtSpot(spot=_SQUARE.spot_id, section=OpenArea()), attentive=False
            ),
        )

    def test_dead_person_perceives_where_the_departed_person_is(self) -> None:
        """去った人として動く世界で死んだ人は、体ではなく去った人のいる場所で DepartedPerceiver になる。"""
        world = _with_dead_alice(departed_persons_act=True)
        world.aggregates().whereabouts().place(DepartedPerson(_ALICE), _CELLAR)

        perceivers = perceivers_in_world(world.facts())

        assert perceivers == (
            DepartedPerceiver(person=_ALICE, location=AtSpot(spot=_CELLAR.spot_id, section=OpenArea())),
        )

    def test_dead_person_perceives_nothing_when_departed_persons_do_not_act(self) -> None:
        """去った人として動かない世界で死んだ人は、何も知覚しない DeadPerceiver になる。"""
        world = _with_dead_alice(departed_persons_act=False)

        assert perceivers_in_world(world.facts()) == (DeadPerceiver(person=_ALICE),)

    def test_person_who_left_the_world_by_an_outcome_perceives_without_a_place(self) -> None:
        """結末が「救出」に決まって体が世界から外れた人は、居場所を引かずに PersonWhoLeftTheWorld になる。"""
        world = _placed(
            world_in_memory(world=_WORLD, people=(_ALICE,), spots=(_SQUARE,), vitals=(_vitals(_ALICE),)),
            _ALICE,
            _SQUARE,
        )
        _leave_by_rescue(world, _ALICE)

        assert perceivers_in_world(world.facts()) == (PersonWhoLeftTheWorld(person=_ALICE, life=Alive()),)

    def test_person_who_fainted_and_left_the_world_perceives_as_fainted(self) -> None:
        """気を失ったまま結末が決まって外れた人は、倒れたままの PersonWhoLeftTheWorld になる。"""
        fainted = _vitals(_ALICE)
        fainted.take_damage(Damage(10), WorldTick(0), WorldHappening())
        world = _placed(
            world_in_memory(world=_WORLD, people=(_ALICE,), spots=(_SQUARE,), vitals=(fainted,)), _ALICE, _SQUARE
        )
        _leave_by_rescue(world, _ALICE)

        [perceiver] = perceivers_in_world(world.facts())

        assert isinstance(perceiver, PersonWhoLeftTheWorld)
        assert isinstance(perceiver.life, Down)


def _leave_by_rescue(world: WorldSession, person: PersonId) -> None:
    rescued = OutcomeDeclaration(
        outcome_id=OutcomeId("rescued"),
        name=DisplayName("救出"),
        announcement=TextWithUnassignedPeople("{each_person}は昇降機で外へ出た。"),
    )
    world.aggregates().outcomes().decide(person, DeclaredOutcome(rescued), WorldTick(1))
    world.aggregates().whereabouts().remove(PersonBody(person))


def _with_dead_alice(departed_persons_act: bool) -> WorldSession:
    dead = _vitals(_ALICE)
    dead.take_damage(Damage(10), WorldTick(0), WorldHappening())
    dead.pass_time(WorldTick(31), world_rules_for_tests().death, world_rules_for_tests().hunger)
    world = world_in_memory(
        world=_WORLD,
        rules=replace(world_rules_for_tests(), departed_persons_act=departed_persons_act),
        people=(_ALICE,),
        spots=(_SQUARE, _CELLAR),
        vitals=(dead,),
    )
    return _placed(world, _ALICE, _SQUARE)
