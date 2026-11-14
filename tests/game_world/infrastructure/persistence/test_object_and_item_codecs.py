"""物と品物の集約 (Item・ItemSerialCounter・ObjectState・PersonInventory・GroundItems・SpotSearchProgress) の memento が JSON を行き来し、知らない形の行を止めることを保証する。"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
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
    ItemStateKind,
    LastsIndefinitely,
    NoRefill,
    NotALightSource,
    NothingWritten,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateKind,
    StateValue,
    StockStateKind,
    StockValue,
    TextBody,
    WrittenText,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration, Finding
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.objects_and_items import (
    DiscoverableFinder,
    GroundItems,
    GroundItemsMemento,
    Item,
    ItemInstanceId,
    ItemMemento,
    ItemSerialCounter,
    ItemSerialCounterMemento,
    ItemStateKeyValue,
    ObjectState,
    ObjectStateKeyValue,
    ObjectStateMemento,
    ObjectStockLevel,
    PersonInventory,
    PersonInventoryMemento,
    PersonSearchCount,
    SpotSearchProgress,
    SpotSearchProgressMemento,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Count,
    DescriptionText,
    DisplayName,
    Gold,
    HandsNeeded,
    ItemSpecId,
    ObjectId,
    PersonId,
    SpotId,
    StateKeyId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS, StoredMemento
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    StoredMementoUnreadableException,
)
from tests.game_world.support.world_design_for_tests import item_spec

_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAVE = SpotId("cave")
_LANTERN = ItemSpecId("lantern")
_ROPE = ItemSpecId("rope")
_WELL = ObjectId("well")


def _item_key(key: str, kind: ItemStateKind, initial: StateValue) -> ItemStateKeyDeclaration:
    return ItemStateKeyDeclaration(item_spec_id=_LANTERN, key=StateKeyId(key), kind=kind, initial=initial)


_WICK = _item_key(
    "wick", ChoiceStateKind(choices=(ChoiceName("unlit"), ChoiceName("lit"))), ChoiceValue(ChoiceName("unlit"))
)
_OIL = _item_key("oil", CountStateKind(), CountValue(Count(3)))
_CRACKED = _item_key("cracked", FlagStateKind(), FlagValue(raised=False))


def _item() -> ItemMemento:
    spec = ItemSpecDeclaration(
        item_spec_id=_LANTERN,
        name=DisplayName("カンテラ"),
        description=DescriptionText("油で灯る手提げの明かり"),
        state_keys=(_WICK, _OIL, _CRACKED),
        lights_up=NotALightSource(),
        hands_needed=HandsNeeded(1),
        lasts=LastsIndefinitely(),
    )
    item = Item.come_into_world(ItemInstanceId("lantern#1"), spec, WorldTick(2))
    item.set(_WICK, ChoiceValue(ChoiceName("lit")))
    item.set(_OIL, CountValue(Count(1)))
    item.set(_CRACKED, FlagValue(raised=True))
    item.leave_world()
    return item.memento()


def _object_key(key: str, kind: StateKind, initial: StateValue) -> ObjectStateKeyDeclaration:
    return ObjectStateKeyDeclaration(object_id=_WELL, key=StateKeyId(key), kind=kind, initial=initial)


_COVERED = _object_key("covered", FlagStateKind(), FlagValue(raised=True))
_BUCKETS = _object_key("buckets", CountStateKind(), CountValue(Count(2)))
_ROPE_STATE = _object_key(
    "rope", ChoiceStateKind(choices=(ChoiceName("up"), ChoiceName("down"))), ChoiceValue(ChoiceName("up"))
)
_NOTE = _object_key("note", WrittenTextStateKind(), NothingWritten())
_SIGN = _object_key("sign", WrittenTextStateKind(), NothingWritten())
_WATER = _object_key("water", StockStateKind(capacity=Count(5), refills_every=Ticks(3)), StockValue(Count(4)))
_SALT = _object_key("salt", StockStateKind(capacity=Count(2), refills_every=NoRefill()), StockValue(Count(2)))


def _object_state() -> ObjectStateMemento:
    declaration = ObjectDeclaration(
        object_id=_WELL,
        spot_id=_CAVE,
        name=DisplayName("井戸"),
        description=DescriptionText("石を積んだ古い井戸"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=True),
        state_keys=(_COVERED, _BUCKETS, _ROPE_STATE, _NOTE, _SIGN, _WATER, _SALT),
    )
    state = ObjectState.from_declaration(declaration, WorldTick(0))
    state.set(_COVERED, FlagValue(raised=False), WorldTick(1))
    state.add_to_count(_BUCKETS, Count(3))
    state.set(_ROPE_STATE, ChoiceValue(ChoiceName("down")), WorldTick(1))
    state.write_text(_SIGN, TextBody("水は汲みすぎないこと"), _ALICE, WorldTick(4))
    state.take_from_stock(_WATER, Count(3), WorldTick(1))
    state.take_from_stock(_SALT, Count(1), WorldTick(1))
    state.reveal()
    return state.memento()


def _inventory() -> PersonInventoryMemento:
    inventory = PersonInventory.start(_ALICE, Capacity(6))
    for name in ("knife", "apple", "rope", "map"):
        inventory.receive(ItemInstanceId(name), _ROPE)
    inventory.receive(ItemInstanceId("lantern#1"), _LANTERN)
    inventory.hold(ItemInstanceId("rope"), HandsNeeded(1))
    inventory.hold(ItemInstanceId("knife"), HandsNeeded(1))
    inventory.earn(Gold(7))
    return inventory.memento()


def _ground_items() -> GroundItemsMemento:
    ground = GroundItems.start(_CAVE)
    for name in ("stone", "bone", "shell", "coin"):
        ground.place(ItemInstanceId(name))
    ground.take(ItemInstanceId("shell"))
    return ground.memento()


def _discoverable(name: str, finding: Finding) -> DiscoverableDeclaration:
    return DiscoverableDeclaration(
        discoverable_id=DiscoverableId(name),
        spot_id=_CAVE,
        found_text=TextWithUnassignedPeople("岩の隙間に何か光る物がある"),
        condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
        when_found=NoEffect(),
        finding=finding,
    )


def _search_progress() -> SpotSearchProgressMemento:
    progress = SpotSearchProgress.start(_CAVE)
    progress.record_search(_BOB)
    progress.record_search(_ALICE)
    progress.record_search(_BOB)
    carving = _discoverable("wall_carving", Finding.ONCE_PER_PERSON)
    progress.mark_found(carving, _BOB)
    progress.mark_found(carving, _ALICE)
    progress.mark_found(_discoverable("old_chest", Finding.ONCE_IN_WORLD), _ALICE)
    return progress.memento()


def _item_serial_counter() -> ItemSerialCounterMemento:
    counter = ItemSerialCounter.start(WorldId("island"))
    counter.bring_item_into_world(item_spec("rope"), WorldTick(1))
    counter.bring_item_into_world(item_spec("rope"), WorldTick(2))
    return counter.memento()


_ITEM = _item()
_OBJECT_STATE = _object_state()
_INVENTORY = _inventory()
_GROUND_ITEMS = _ground_items()
_SEARCH_PROGRESS = _search_progress()

_MEMENTOS: dict[str, object] = {
    "item": _ITEM,
    "item_serial_counter": _item_serial_counter(),
    "object_state": _OBJECT_STATE,
    "person_inventory": _INVENTORY,
    "ground_items": _GROUND_ITEMS,
    "spot_search_progress": _SEARCH_PROGRESS,
}


def _round_trip(memento: object) -> object:
    return GAME_WORLD_CODECS.memento(GAME_WORLD_CODECS.stored(memento), type(memento))


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
        "value",
        [
            FlagValue(raised=True),
            CountValue(Count(4)),
            ChoiceValue(ChoiceName("down")),
            StockValue(Count(2)),
            WrittenText(body=TextBody("ここに鍵"), author=_BOB, written_at=WorldTick(6)),
            NothingWritten(),
        ],
    )
    def test_every_state_value_survives_a_round_trip(self, value: StateValue) -> None:
        """旗・数・選択・在庫・書いた文・何も書いていない、のどの値も、物の値として読み戻すと同じ値になる。"""
        memento = replace(_OBJECT_STATE, values=frozenset({ObjectStateKeyValue(StateKeyId("k"), value)}))

        assert _round_trip(memento) == memento

    def test_state_values_are_written_under_their_tags(self) -> None:
        """物の値は、値の種類の印の中に、その種類のフィールドを持つ。"""
        state = json.loads(GAME_WORLD_CODECS.stored(_OBJECT_STATE).state)

        assert {entry["key"]: entry["value"] for entry in state["values"]} == {
            "buckets": {"count_value": {"count": 5}},
            "covered": {"flag_value": {"raised": False}},
            "note": {"nothing_written": {}},
            "rope": {"choice_value": {"choice": "down"}},
            "sign": {"written_text": {"body": "水は汲みすぎないこと", "author": "alice", "written_at": 4}},
        }
        assert state["stock_levels"] == [
            {"key": "salt", "amount": 1, "counted_from": 0},
            {"key": "water", "amount": 1, "counted_from": 0},
        ]

    def test_inventory_keeps_the_order_of_held_and_packed_items(self) -> None:
        """持ち物は、手に持った順 (rope, knife) としまった順 (apple, map, lantern#1) のまま書いて読む。"""
        restored = _round_trip(_INVENTORY)

        assert isinstance(restored, PersonInventoryMemento)
        assert [held.item.value for held in restored.held] == ["rope", "knife"]
        assert [packed.item.value for packed in restored.packed] == ["apple", "map", "lantern#1"]

    def test_ground_items_keep_the_order_they_were_placed_in(self) -> None:
        """地面の品物は、置いた順 (stone, bone, coin) のまま書いて読む。"""
        state = json.loads(GAME_WORLD_CODECS.stored(_GROUND_ITEMS).state)

        assert state["items"] == ["stone", "bone", "coin"]

    @pytest.mark.parametrize(
        ("memento", "listed", "sort_key"),
        [
            (
                replace(
                    _ITEM,
                    values=frozenset(ItemStateKeyValue(StateKeyId(f"key_{n}"), CountValue(Count(n))) for n in range(8)),
                ),
                "values",
                ("key",),
            ),
            (
                replace(
                    _OBJECT_STATE,
                    values=frozenset(
                        ObjectStateKeyValue(StateKeyId(f"key_{n}"), FlagValue(raised=True)) for n in range(8)
                    ),
                ),
                "values",
                ("key",),
            ),
            (
                replace(
                    _OBJECT_STATE,
                    stock_levels=frozenset(
                        ObjectStockLevel(StateKeyId(f"key_{n}"), Count(n), WorldTick(0)) for n in range(8)
                    ),
                ),
                "stock_levels",
                ("key",),
            ),
            (
                replace(
                    _SEARCH_PROGRESS,
                    search_counts=frozenset(PersonSearchCount(PersonId(f"p{n}"), Count(n + 1)) for n in range(8)),
                ),
                "search_counts",
                ("person",),
            ),
            (
                replace(
                    _SEARCH_PROGRESS,
                    finders=frozenset(
                        DiscoverableFinder(DiscoverableId(name), PersonId(f"p{n}"))
                        for n in range(4)
                        for name in ("old_chest", "wall_carving")
                    ),
                ),
                "finders",
                ("discoverable", "finder"),
            ),
        ],
        ids=["item_values", "object_values", "stock_levels", "search_counts", "finders"],
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

    def test_unknown_state_value_is_refused(self) -> None:
        """知らない印の物の値は、その印を添えて止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_ITEM), {"values": [{"key": "wick", "value": {"color_value": {}}}]}
        )

        with pytest.raises(StoredMementoUnreadableException, match="color_value"):
            GAME_WORLD_CODECS.memento(stored, ItemMemento)

    def test_item_lying_twice_on_the_ground_is_refused(self) -> None:
        """同じ品物が地面に 2 回ある行は、memento の決まりで止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_GROUND_ITEMS), {"items": ["stone", "stone"]})

        with pytest.raises(StoredMementoUnreadableException, match="ground_items"):
            GAME_WORLD_CODECS.memento(stored, GroundItemsMemento)

    def test_item_carried_twice_is_refused(self) -> None:
        """手に持った品物と同じ品物がしまった側にもある行は、memento の決まりで止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_INVENTORY),
            {"packed": [{"item": "rope", "spec": "rope"}]},
        )

        with pytest.raises(StoredMementoUnreadableException, match="person_inventory"):
            GAME_WORLD_CODECS.memento(stored, PersonInventoryMemento)
