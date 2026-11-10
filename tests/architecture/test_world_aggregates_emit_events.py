"""世界を表す集約が、状態を変えたら必ずドメインイベントをためることを見張る (#2008)。

docs/environment_model/design/world_state.md の決まり:

- 世界を表す集約は、状態を変えたら必ずイベントを出す。帳簿の集約 (ScenarioProgress、MissedNotices) は出さない
- 状態が変わらない操作は、断らず、イベントも出さない
- 空腹と疲れは、段階が変わったときだけイベントにする

見張り方:

- 対象の集約は、ai_rpg_world.game_world.domain の下を走査して集めた AggregateRoot の子クラスから、帳簿の集約を名前で除いたもの
- 状態を変える操作は、公開メソッドのうち戻り値の注釈が None のもの (CLAUDE.md の「状態を変える操作は値を返さない」)
- 操作ごとに、状態が変わる呼び方を下の表に手で書く。見つけた操作が表に無ければ落ちる
- 状態が変わらない呼び方 (同じ値への set など) は表に書かない。そこでイベントが出ないのは正しい振る舞いのため
- 状態を変えずにイベントだけを出す操作 (断られた試みの記録) は、表に書いたうえで _EVENT_ONLY_OPERATIONS に挙げる
"""

from __future__ import annotations

import copy
import importlib
import inspect
import pkgutil
from collections.abc import Callable
from typing import Any

import pytest
from tests.game_world.domain.whereabouts._builders import CLOSED, OPEN, atmosphere, door, path, section, spot
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests

from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.action.common_rule_refusal import TooTired
from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.character import (
    CharacterDeclaration,
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import UsesWorldDefault
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    CountStateKind,
    CountValue,
    FlagStateKind,
    FlagValue,
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    Lasts,
    LastsIndefinitely,
    NotALightSource,
    NothingWritten,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StockStateKind,
    StockValue,
    TextBody,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.declaration.progress import (
    AllActionsAllowed,
    FlagDeclaration,
    GroupDecisionDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    NoChange,
    NoDayNight,
    WeatherDeclaration,
    WeatherState,
    WeatherType,
)
from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration, Finding
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.objects_and_items import (
    CarriedBy,
    GroundItems,
    Item,
    ItemInstanceId,
    ObjectState,
    PersonInventory,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.people import PeopleRegister, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import (
    Died,
    GroupMembership,
    PersonOutcomes,
    PersonVitals,
    StatusEffect,
    StatusEffectType,
    StruckByPerson,
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
    FlagId,
    Gold,
    GroupDecisionId,
    GroupId,
    GroupingId,
    HandsNeeded,
    HealAmount,
    HitPoints,
    HungerAmount,
    ItemSpecId,
    ObjectId,
    PersonId,
    Rate,
    StateKeyId,
    Ticks,
    WorldId,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from ai_rpg_world.game_world.domain.whereabouts import (
    PassageStates,
    PersonBody,
    Route,
    SpotAtmospheres,
    Whereabouts,
)
from ai_rpg_world.game_world.domain.world_progress import (
    GroupDecision,
    VoteFor,
    Weather,
    WorldClock,
    WorldEnding,
    WorldStage,
)
from ai_rpg_world.game_world.domain.world_records import LatestActions, WorldFlags

_DOMAIN_PACKAGE = "ai_rpg_world.game_world.domain"
_LEDGER_AGGREGATES = frozenset({"ScenarioProgress", "MissedNotices"})
# 断られた試みは最後に行った行為を変えないが、本人と周りに断られたことを届けるためにイベントだけを出す
_EVENT_ONLY_OPERATIONS = frozenset({"LatestActions.note_failed_attempt"})


def _is_watched(cls: type) -> bool:
    return issubclass(cls, AggregateRoot) and cls is not AggregateRoot and cls.__name__ not in _LEDGER_AGGREGATES


def _world_aggregates() -> list[type[AggregateRoot[Any]]]:
    package = importlib.import_module(_DOMAIN_PACKAGE)
    found: dict[str, type[AggregateRoot[Any]]] = {}
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{_DOMAIN_PACKAGE}."):
        module = importlib.import_module(module_info.name)
        for cls in vars(module).values():
            if inspect.isclass(cls) and cls.__module__ == module.__name__ and _is_watched(cls):
                found[f"{cls.__module__}.{cls.__qualname__}"] = cls
    return [found[name] for name in sorted(found)]


def _public_methods(cls: type) -> list[tuple[str, Callable[..., Any]]]:
    return [
        (name, member)
        for name, member in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_") and getattr(AggregateRoot, name, None) is not member
    ]


def _return_annotation(member: Callable[..., Any]) -> Any:
    # 引数の注釈は TYPE_CHECKING の下でだけ import した型を指すことがあり、評価すると NameError になるので、戻り値だけを
    # 評価せずに見る。from __future__ import annotations のモジュールでは "None" という文字列になる
    return inspect.signature(member).return_annotation


def _state_changing_operations(cls: type) -> list[str]:
    return [name for name, member in _public_methods(cls) if _return_annotation(member) in (None, "None")]


def _methods_without_return_annotation(cls: type) -> list[str]:
    return [name for name, member in _public_methods(cls) if _return_annotation(member) is inspect.Signature.empty]


def _discovered_operations() -> set[str]:
    return {f"{cls.__name__}.{name}" for cls in _world_aggregates() for name in _state_changing_operations(cls)}


def _state_of(aggregate: AggregateRoot[Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in vars(aggregate).items() if key != "_events"}


_PreparedCall = tuple[AggregateRoot[Any], Callable[[], None]]

_WORLD = WorldId("watched_world")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_ALICE_BODY = PersonBody(_ALICE)
_PLAZA = spot("plaza")
_WELL = spot("well")
_MINE = spot("mine")
_STREET = path("street", "plaza", "well", ticks=1)
_LANE = path("lane", "well", "mine", ticks=1)
_GATE = door("gate", "plaza", "well", initial=CLOSED)
_HIDDEN_PATH = path("hidden_path", "plaza", "mine", hidden_until_revealed=True)
_BENCH = section("bench", "plaza")
_LANTERN = ItemInstanceId("lantern#1")
_ROPE = ItemInstanceId("rope#1")
_NOW = WorldTick(0)


def _cleared(aggregate: AggregateRoot[Any]) -> None:
    aggregate.clear_events()


def _whereabouts(at: str = "plaza") -> Whereabouts:
    whereabouts = Whereabouts.start(_WORLD)
    whereabouts.place(_ALICE_BODY, spot(at))
    _cleared(whereabouts)
    return whereabouts


def _travelling() -> Whereabouts:
    whereabouts = _whereabouts()
    whereabouts.start_travel(_ALICE_BODY, Route(start=_PLAZA.spot_id, passages=(_STREET,)))
    _cleared(whereabouts)
    return whereabouts


def _on_bench() -> Whereabouts:
    whereabouts = _whereabouts()
    whereabouts.enter_section(_ALICE_BODY, _BENCH, frozenset())
    _cleared(whereabouts)
    return whereabouts


def _people_register() -> PeopleRegister:
    alice = CharacterDeclaration(
        person_id=_ALICE,
        appearance=DescriptionText("背の高い人"),
        spawn_spot=_PLAZA.spot_id,
        initial_items=(),
        initial_held=(),
        initial_groups=(),
        knows_at_start=(),
        max_hp=UsesWorldDefault(),
        pack_capacity=UsesWorldDefault(),
    )
    return PeopleRegister.from_characters(_WORLD, (alice,))


def _passages() -> PassageStates:
    return PassageStates.start(_WORLD, (_GATE, _HIDDEN_PATH, _LANE))


def _vitals(current: int = 10) -> PersonVitals:
    vitals = PersonVitals.start(_ALICE, HitPoints(current=current, maximum=10))
    _cleared(vitals)
    return vitals


def _fallen() -> PersonVitals:
    vitals = _vitals()
    vitals.take_damage(Damage(10), _NOW, StruckByPerson(_BOB))
    _cleared(vitals)
    return vitals


def _hunger_rule() -> HungerRule:
    return HungerRule(
        per_tick=HungerAmount(2),
        limit=HungerAmount(4),
        starvation_damage=NoStarvationDamage(),
        levels=(
            HungerLevel(starts_at=HungerAmount(0), name=HungerLevelName("満腹")),
            HungerLevel(starts_at=HungerAmount(2), name=HungerLevelName("空腹")),
        ),
    )


def _fatigue_rule() -> FatigueRule:
    return FatigueRule(
        per_exertion=FatigueAmount(2),
        limit=FatigueAmount(4),
        levels=(
            FatigueLevel(starts_at=FatigueAmount(0), name=FatigueLevelName("元気")),
            FatigueLevel(starts_at=FatigueAmount(2), name=FatigueLevelName("疲れた")),
        ),
    )


def _hungry() -> PersonVitals:
    vitals = _vitals()
    vitals.pass_time(_NOW, DeathRule(grace=Ticks(2)), _hunger_rule())
    _cleared(vitals)
    return vitals


def _tired() -> PersonVitals:
    vitals = _vitals()
    vitals.exert(_fatigue_rule())
    _cleared(vitals)
    return vitals


_BLEEDING = StatusEffectType("bleeding")


def _bleeding_until(tick: int) -> PersonVitals:
    vitals = _vitals()
    vitals.add_status_effect(StatusEffect(kind=_BLEEDING, expires_at=WorldTick(tick)))
    _cleared(vitals)
    return vitals


_TEAMS = GroupingDeclaration(
    grouping_id=GroupingId("teams"),
    name=DisplayName("teams"),
    visibility=MembershipVisibility.EVERYONE,
    changes=True,
)
_RED = GroupDeclaration(
    group_id=GroupId("red"),
    grouping=_TEAMS,
    name=DisplayName("red"),
    members_know_each_other=False,
    shared_description=NoSharedDescription(),
)

_LANTERN_SPEC = ItemSpecId("lantern")
_WICK = ItemStateKeyDeclaration(
    item_spec_id=_LANTERN_SPEC,
    key=StateKeyId("wick"),
    kind=ChoiceStateKind(choices=(ChoiceName("unlit"), ChoiceName("lit"))),
    initial=ChoiceValue(ChoiceName("unlit")),
)


def _item(lasts: Lasts | LastsIndefinitely = LastsIndefinitely()) -> Item:
    item = Item.come_into_world(
        _LANTERN,
        ItemSpecDeclaration(
            item_spec_id=_LANTERN_SPEC,
            name=DisplayName("カンテラ"),
            description=DescriptionText("油で灯る手提げの明かり"),
            state_keys=(_WICK,),
            lights_up=NotALightSource(),
            hands_needed=HandsNeeded(1),
            lasts=lasts,
        ),
        _NOW,
    )
    _cleared(item)
    return item


def _ground(*items: ItemInstanceId) -> GroundItems:
    ground = GroundItems(_PLAZA.spot_id)
    for item in items:
        ground.place(item)
    _cleared(ground)
    return ground


def _inventory(*items: ItemInstanceId, gold: int = 0) -> PersonInventory:
    inventory = PersonInventory(_ALICE, Capacity(5))
    for item in items:
        inventory.receive(item, _LANTERN_SPEC)
    inventory.earn(Gold(gold))
    _cleared(inventory)
    return inventory


def _holding(item: ItemInstanceId) -> PersonInventory:
    inventory = _inventory(item)
    inventory.hold(item, HandsNeeded(1))
    _cleared(inventory)
    return inventory


_WELL_OBJECT = ObjectId("well")


def _object_key(key: str, kind: Any, initial: Any) -> ObjectStateKeyDeclaration:
    return ObjectStateKeyDeclaration(object_id=_WELL_OBJECT, key=StateKeyId(key), kind=kind, initial=initial)


_COVERED = _object_key("covered", FlagStateKind(), FlagValue(raised=True))
_BUCKETS = _object_key("buckets", CountStateKind(), CountValue(Count(2)))
_WATER = _object_key("water", StockStateKind(capacity=Count(5), refills_every=Ticks(3)), StockValue(Count(5)))
_NOTE = _object_key("note", WrittenTextStateKind(), NothingWritten())


def _object_state(*, hidden: bool = False) -> ObjectState:
    state = ObjectState.from_declaration(
        ObjectDeclaration(
            object_id=_WELL_OBJECT,
            spot_id=_PLAZA.spot_id,
            name=DisplayName("井戸"),
            description=DescriptionText("石を積んだ古い井戸"),
            appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=hidden),
            state_keys=(_COVERED, _BUCKETS, _WATER, _NOTE),
        ),
        _NOW,
    )
    _cleared(state)
    return state


def _decision() -> GroupDecision:
    return GroupDecision.not_started(
        GroupDecisionDeclaration(
            decision_id=GroupDecisionId("exile_vote"),
            name=DisplayName("追放の投票"),
            abstain_allowed=True,
            reveals_ballots=False,
        )
    )


def _open_decision() -> GroupDecision:
    decision = _decision()
    decision.start(frozenset({_ALICE, _BOB}), frozenset({_ALICE, _BOB}))
    _cleared(decision)
    return decision


def _stage(stage_id: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(stage_id),
        name=DisplayName(stage_id),
        description=DescriptionText(f"{stage_id}の段階"),
        allowed_actions=AllActionsAllowed(),
    )


_FOUNTAIN_COIN = DiscoverableDeclaration(
    discoverable_id=DiscoverableId("fountain_coin"),
    spot_id=_PLAZA.spot_id,
    found_text=TextWithUnassignedPeople("噴水の底に銅貨が沈んでいる"),
    condition=TickAtLeastCondition(tick=_NOW, failure_text=NoText()),
    when_found=NoEffect(),
    finding=Finding.ONCE_IN_WORLD,
)
_BELL_RUNG = FlagDeclaration(flag_id=FlagId("bell_rung"), meaning=DescriptionText("鐘が鳴った"), initially_raised=False)
_GATE_SHUT = FlagDeclaration(
    flag_id=FlagId("gate_shut"), meaning=DescriptionText("門が閉じている"), initially_raised=True
)
_TICK_PASSING = WorldTimePassing(WorldTick(1))


def _with(aggregate: AggregateRoot[Any], call: Callable[[Any], None]) -> _PreparedCall:
    return aggregate, lambda: call(aggregate)


_STATE_CHANGING_CALLS: dict[str, Callable[[], _PreparedCall]] = {
    "Whereabouts.place": lambda: _with(Whereabouts.start(_WORLD), lambda w: w.place(_ALICE_BODY, _PLAZA)),
    "Whereabouts.remove": lambda: _with(_whereabouts(), lambda w: w.remove(_ALICE_BODY)),
    "Whereabouts.start_travel": lambda: _with(
        _whereabouts(), lambda w: w.start_travel(_ALICE_BODY, Route(start=_PLAZA.spot_id, passages=(_STREET,)))
    ),
    # 道の途中の進みはイベントにせず、着いたときと止められたときだけイベントにする。
    "Whereabouts.advance_travels": lambda: _with(_travelling(), lambda w: w.advance_travels(frozenset())),
    "Whereabouts.cancel_travel": lambda: _with(_travelling(), lambda w: w.cancel_travel(_ALICE_BODY)),
    "Whereabouts.teleport": lambda: _with(_whereabouts(), lambda w: w.teleport(_ALICE_BODY, _MINE)),
    "Whereabouts.enter_section": lambda: _with(
        _whereabouts(), lambda w: w.enter_section(_ALICE_BODY, _BENCH, frozenset())
    ),
    "Whereabouts.leave_section": lambda: _with(_on_bench(), lambda w: w.leave_section(_ALICE_BODY)),
    "PassageStates.change_state": lambda: _with(_passages(), lambda p: p.change_state(_GATE, OPEN)),
    "PassageStates.reveal": lambda: _with(_passages(), lambda p: p.reveal(_HIDDEN_PATH)),
    "PassageStates.remove": lambda: _with(_passages(), lambda p: p.remove(_LANE)),
    "SpotAtmospheres.change": lambda: _with(
        SpotAtmospheres.start(_WORLD, (_PLAZA,)), lambda s: s.change(_PLAZA, atmosphere(Lighting.DARK))
    ),
    "PersonVitals.take_damage": lambda: _with(
        _vitals(), lambda v: v.take_damage(Damage(3), _NOW, StruckByPerson(_BOB))
    ),
    "PersonVitals.heal": lambda: _with(_vitals(current=5), lambda v: v.heal(HealAmount(3))),
    "PersonVitals.revive": lambda: _with(_fallen(), lambda v: v.revive(Rate(0.5), WorldTick(1))),
    # 空腹と疲れは段階が変わったときだけイベントにする (world_state.md)。
    "PersonVitals.pass_time": lambda: _with(
        _vitals(), lambda v: v.pass_time(WorldTick(1), DeathRule(grace=Ticks(2)), _hunger_rule())
    ),
    "PersonVitals.add_status_effect": lambda: _with(
        _vitals(), lambda v: v.add_status_effect(StatusEffect(kind=_BLEEDING, expires_at=WorldTick(10)))
    ),
    "PersonVitals.remove_expired_status_effects": lambda: _with(
        _bleeding_until(3), lambda v: v.remove_expired_status_effects(WorldTick(3))
    ),
    "PersonVitals.satisfy_hunger": lambda: _with(
        _hungry(), lambda v: v.satisfy_hunger(HungerAmount(2), _hunger_rule())
    ),
    "PersonVitals.exert": lambda: _with(_vitals(), lambda v: v.exert(_fatigue_rule())),
    "PersonVitals.rest": lambda: _with(_tired(), lambda v: v.rest(FatigueAmount(2), _fatigue_rule())),
    "PersonVitals.start_action": lambda: _with(_vitals(), lambda v: v.start_action(WorldTick(3))),
    "PeopleRegister.name": lambda: _with(_people_register(), lambda r: r.name(_ALICE, DisplayName("ミナ"))),
    "PersonOutcomes.decide": lambda: _with(PersonOutcomes.start(_WORLD, (_ALICE,)), lambda o: o.decide(_ALICE, Died())),
    "GroupMembership.join": lambda: _with(GroupMembership.start(_WORLD, {}), lambda g: g.join(_ALICE, _RED)),
    "GroupMembership.leave": lambda: _with(
        GroupMembership.start(_WORLD, {_ALICE: (_RED,)}), lambda g: g.leave(_ALICE, _RED)
    ),
    "Item.set": lambda: _with(_item(), lambda i: i.set(_WICK, ChoiceValue(ChoiceName("lit")))),
    "Item.leave_world": lambda: _with(_item(), lambda i: i.leave_world()),
    "Item.run_out": lambda: _with(
        _item(Lasts(ticks=Ticks(1), ended_text=DescriptionText("灯が燃え尽きた。"))),
        lambda i: i.run_out(_NOW + Ticks(1), CarriedBy(_ALICE)),
    ),
    "GroundItems.place": lambda: _with(_ground(), lambda g: g.place(_LANTERN)),
    "GroundItems.take": lambda: _with(_ground(_LANTERN), lambda g: g.take(_LANTERN)),
    "SpotSearchProgress.record_search": lambda: _with(
        SpotSearchProgress(_PLAZA.spot_id), lambda s: s.record_search(_ALICE)
    ),
    "SpotSearchProgress.mark_found": lambda: _with(
        SpotSearchProgress(_PLAZA.spot_id), lambda s: s.mark_found(_FOUNTAIN_COIN, _ALICE)
    ),
    "PersonInventory.receive": lambda: _with(_inventory(), lambda i: i.receive(_LANTERN, _LANTERN_SPEC)),
    "PersonInventory.give_up": lambda: _with(_inventory(_LANTERN), lambda i: i.give_up(_LANTERN)),
    "PersonInventory.give_up_held": lambda: _with(_holding(_ROPE), lambda i: i.give_up_held(_ROPE)),
    "PersonInventory.give_up_packed": lambda: _with(_inventory(_LANTERN), lambda i: i.give_up_packed(_LANTERN)),
    "PersonInventory.hold": lambda: _with(_inventory(_LANTERN), lambda i: i.hold(_LANTERN, HandsNeeded(1))),
    "PersonInventory.put_away": lambda: _with(_holding(_ROPE), lambda i: i.put_away(_ROPE)),
    "PersonInventory.earn": lambda: _with(_inventory(), lambda i: i.earn(Gold(5))),
    "PersonInventory.pay": lambda: _with(_inventory(gold=5), lambda i: i.pay(Gold(3))),
    "ObjectState.set": lambda: _with(_object_state(), lambda o: o.set(_COVERED, FlagValue(raised=False), _NOW)),
    "ObjectState.add_to_count": lambda: _with(_object_state(), lambda o: o.add_to_count(_BUCKETS, Count(1))),
    "ObjectState.subtract_from_count": lambda: _with(
        _object_state(), lambda o: o.subtract_from_count(_BUCKETS, Count(1))
    ),
    "ObjectState.take_from_stock": lambda: _with(_object_state(), lambda o: o.take_from_stock(_WATER, Count(2), _NOW)),
    "ObjectState.write_text": lambda: _with(
        _object_state(), lambda o: o.write_text(_NOTE, TextBody("ここに水あり"), _ALICE, _NOW)
    ),
    "ObjectState.reveal": lambda: _with(_object_state(hidden=True), lambda o: o.reveal()),
    "GroupDecision.start": lambda: _with(
        _decision(), lambda d: d.start(frozenset({_ALICE, _BOB}), frozenset({_ALICE, _BOB}))
    ),
    "GroupDecision.cast": lambda: _with(_open_decision(), lambda d: d.cast(_ALICE, VoteFor(_BOB))),
    "GroupDecision.withdraw_voter": lambda: _with(_open_decision(), lambda d: d.withdraw_voter(_BOB)),
    "GroupDecision.withdraw_choice": lambda: _with(_open_decision(), lambda d: d.withdraw_choice(_BOB)),
    "GroupDecision.close": lambda: _with(_open_decision(), lambda d: d.close()),
    "Weather.change": lambda: _with(
        Weather.from_declaration(
            _WORLD,
            WeatherDeclaration(
                initial=WeatherType.CLEAR, changes=NoChange(), announce_changes=True, obscuring=frozenset()
            ),
        ),
        lambda w: w.change(WeatherState(WeatherType.RAIN)),
    ),
    "WorldClock.advance": lambda: _with(WorldClock(_WORLD), lambda c: c.advance(NoDayNight())),
    "WorldStage.enter": lambda: _with(
        WorldStage.from_initial_stage(_WORLD, _stage("before_dawn"), _NOW),
        lambda s: s.enter(_stage("dawn"), WorldTick(1)),
    ),
    "WorldFlags.raise_flag": lambda: _with(WorldFlags(_WORLD), lambda f: f.raise_flag(_BELL_RUNG, _TICK_PASSING)),
    "WorldFlags.lower_flag": lambda: _with(WorldFlags(_WORLD), lambda f: f.lower_flag(_GATE_SHUT, _TICK_PASSING)),
    "LatestActions.note": lambda: _with(
        LatestActions(_WORLD), lambda a: a.note(ActionAttemptForTests(actor_id=_ALICE), _NOW)
    ),
    "LatestActions.note_failed_attempt": lambda: _with(
        LatestActions(_WORLD),
        lambda a: a.note_failed_attempt(
            ActionRefusal(
                attempt=ActionAttemptForTests(actor_id=_ALICE),
                reason=TooTired(),
                text=TextWithUnassignedPeople("{actor}は疲れている").about({"actor": _ALICE}),
            ),
            _NOW,
        ),
    ),
    "WorldEnding.end": lambda: _with(WorldEnding(_WORLD), lambda e: e.end(WorldTick(1))),
}


class TestEveryStateChangingOperationIsWatched:
    """走査で見つけた世界の集約の状態を変える操作と、状態が変わる呼び方の表が、過不足なく対応することを保証する。"""

    def test_every_discovered_operation_has_a_state_changing_call(self) -> None:
        """世界の集約に戻り値 None の公開メソッドを足して表に呼び方を書かないと、その操作の名前を挙げて落ちる。"""
        missing = sorted(_discovered_operations() - _STATE_CHANGING_CALLS.keys())

        assert not missing, f"状態が変わる呼び方を _STATE_CHANGING_CALLS に足してください: {missing}"

    def test_every_state_changing_call_names_a_discovered_operation(self) -> None:
        """表に書いた呼び方は、どれも走査で見つけた操作を指す。操作を消したり改名したりして表に残ると落ちる。"""
        stale = sorted(_STATE_CHANGING_CALLS.keys() - _discovered_operations())

        assert not stale, f"走査で見つからない操作が _STATE_CHANGING_CALLS に残っています: {stale}"


class TestStateChangingCallRecordsEvents:
    """表に書いた呼び方が実際に集約の状態を変え、そのときドメインイベントを 1 つ以上ためることを保証する。"""

    @pytest.mark.parametrize("operation", sorted(_STATE_CHANGING_CALLS.keys() - _EVENT_ONLY_OPERATIONS))
    def test_call_changes_the_aggregate_state(self, operation: str) -> None:
        """表の呼び方は、呼ぶ前と後で集約の中身 (_events を除く属性) を変える。状態の変わらない呼び方を書いた表は落ちる。"""
        aggregate, call = _STATE_CHANGING_CALLS[operation]()
        before = _state_of(aggregate)

        call()

        assert _state_of(aggregate) != before

    @pytest.mark.parametrize("operation", sorted(_EVENT_ONLY_OPERATIONS))
    def test_event_only_call_leaves_the_aggregate_state(self, operation: str) -> None:
        """_EVENT_ONLY_OPERATIONS に挙げた呼び方は、集約の中身を変えない。状態を変えるようになったら挙げたままにせず落ちる。"""
        aggregate, call = _STATE_CHANGING_CALLS[operation]()
        before = _state_of(aggregate)

        call()

        assert _state_of(aggregate) == before

    @pytest.mark.parametrize("operation", sorted(_STATE_CHANGING_CALLS))
    def test_call_records_at_least_one_event(self, operation: str) -> None:
        """事前のイベントを空にした集約で表の呼び方をすると、ドメインイベントが 1 つ以上たまる。"""
        aggregate, call = _STATE_CHANGING_CALLS[operation]()
        assert aggregate.get_events() == []

        call()

        assert aggregate.get_events()


class TestWatchedAggregates:
    """見張りの対象になる集約の選び方を保証する。"""

    def test_ledger_aggregates_are_not_watched(self) -> None:
        """帳簿の集約 (ScenarioProgress、MissedNotices) の名前を持つ AggregateRoot の子クラスは、見張りの対象にならない。"""

        class ScenarioProgress(AggregateRoot[Any]):
            pass

        class MissedNotices(AggregateRoot[Any]):
            pass

        assert not _is_watched(ScenarioProgress)
        assert not _is_watched(MissedNotices)

    def test_other_aggregates_are_watched(self) -> None:
        """帳簿の名前でない AggregateRoot の子クラスは、見張りの対象になる。AggregateRoot そのものと集約でないクラスはならない。"""

        class Lighthouse(AggregateRoot[Any]):
            pass

        assert _is_watched(Lighthouse)
        assert not _is_watched(AggregateRoot)
        assert not _is_watched(WorldTick)

    def test_world_aggregates_are_found_under_the_game_world_domain(self) -> None:
        """ai_rpg_world.game_world.domain の下を走査すると、各まとまりの集約が見つかり、帳簿の名前の集約は含まれない。"""
        names = {cls.__name__ for cls in _world_aggregates()}

        assert {"Whereabouts", "PersonVitals", "ObjectState", "WorldClock"} <= names
        assert not names & _LEDGER_AGGREGATES


class TestStateChangingOperationDiscovery:
    """集約のメソッドから、状態を変える操作 (戻り値の注釈が None の公開メソッド) を選ぶ規則を保証する。"""

    def test_public_methods_returning_none_are_state_changing_operations(self) -> None:
        """戻り値 None の公開メソッドだけを拾い、値を返す問い合わせ・非公開のメソッド・クラスメソッド・プロパティ・AggregateRoot の add_event や clear_events は拾わない。"""

        class Lighthouse(AggregateRoot[Any]):
            def light(self) -> None:
                pass

            def is_lit(self) -> bool:
                return False

            def _trim_wick(self) -> None:
                pass

            @classmethod
            def build(cls) -> None:
                pass

            @property
            def keeper(self) -> None:
                return None

        assert _state_changing_operations(Lighthouse) == ["light"]

    def test_public_method_without_return_annotation_is_reported(self) -> None:
        """戻り値の注釈が無い公開メソッドは、状態を変える操作か問い合わせか見分けられないので、見分けられないものとして挙がる。"""

        class Lighthouse(AggregateRoot[Any]):
            def light(self):  # type: ignore[no-untyped-def]
                pass

            def dim(self) -> None:
                pass

        assert _methods_without_return_annotation(Lighthouse) == ["light"]

    def test_every_public_method_of_world_aggregates_has_a_return_annotation(self) -> None:
        """世界の集約の公開メソッドは、どれも戻り値の注釈を持つ。注釈を書き忘れると、見張りから黙って外れないよう落ちる。"""
        unannotated = sorted(
            f"{cls.__name__}.{name}" for cls in _world_aggregates() for name in _methods_without_return_annotation(cls)
        )

        assert not unannotated, f"戻り値の注釈を書いてください: {unannotated}"

    def test_world_aggregate_names_are_distinct(self) -> None:
        """世界の集約のクラス名は重ならない。表のキーをクラス名で引くため、同じ名前の集約が別のモジュールにあると落ちる。"""
        names = [cls.__name__ for cls in _world_aggregates()]

        assert len(names) == len(set(names))
