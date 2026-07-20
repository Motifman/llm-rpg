"""Phase 9-3b codec の単体テスト (spot_interior / item_instance, 戦略 C)。

戦略 C = 動的部分のみ capture。restore は scenario loader が初期化した
SpotInterior / ItemAggregate に **上書き merge** する semantics。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    ItemInstanceSubsystemCodec,
    SpotInteriorSubsystemCodec,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.value_object.item_instance_id import (
    ItemInstanceId,
)
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import (
    DiscoverableItem,
)
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.domain.world_graph.value_object.puzzle_state import (
    PuzzleState,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
    SpotObjectId,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
    SpotObjectTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import (
    SubLocationId,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)


def _spot_obj(
    object_id: int = 1,
    *,
    state: dict | None = None,
    is_visible: bool = True,
    puzzle: PuzzleState | None = None,
    detail_read_by: frozenset[int] = frozenset(),
) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId(object_id),
        name="door",
        description="a door",
        object_type=SpotObjectTypeEnum.DOOR,
        state=state or {},
        interactions=(),
        is_visible=is_visible,
        puzzle=puzzle,
        detail_read_by=detail_read_by,
    )


def _sub_loc(sub_id: int = 1, is_hidden: bool = False) -> SubLocation:
    return SubLocation(
        sub_location_id=SubLocationId(sub_id),
        name="alcove",
        description="dark corner",
        accessible_object_ids=(),
        is_hidden=is_hidden,
    )


def _disc(spec_id: int = 100, is_discovered: bool = False) -> DiscoverableItem:
    from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import (
        DiscoveryConditionTypeEnum,
    )
    from ai_rpg_world.domain.world_graph.value_object.discovery_condition import (
        DiscoveryCondition,
    )

    return DiscoverableItem(
        item_spec_id=ItemSpecId(spec_id),
        discovery_condition=DiscoveryCondition(
            condition_type=DiscoveryConditionTypeEnum.ALWAYS
        ),
        is_discovered=is_discovered,
    )


class TestSpotInteriorCodec:
    """SpotInterior の dynamic 部分のみ往復することを担保。"""

    def test_object_state_visible_round_trips(self) -> None:
        """object の state と isvisible を往復。"""
        # source: object.state = {"door_open": True}, is_visible = False
        src_obj = _spot_obj(
            object_id=1,
            state={"door_open": True},
            is_visible=False,
            detail_read_by=frozenset({2, 5}),
        )
        src_interior = SpotInterior(
            sub_locations=(),
            objects=(src_obj,),
            ground_items=(),
            discoverable_items=(),
        )
        src_repo = InMemorySpotInteriorRepository(
            {SpotId(1): src_interior}
        )
        src_runtime = SimpleNamespace(_spot_interior_repo=src_repo)
        captured = SpotInteriorSubsystemCodec().capture(src_runtime)

        # dst: scenario が初期状態の (state 空 / is_visible=True) の同 object_id を持つ
        dst_obj = _spot_obj(object_id=1, state={}, is_visible=True)
        dst_interior = SpotInterior(
            sub_locations=(),
            objects=(dst_obj,),
            ground_items=(),
            discoverable_items=(),
        )
        dst_repo = InMemorySpotInteriorRepository(
            {SpotId(1): dst_interior}
        )
        dst_runtime = SimpleNamespace(_spot_interior_repo=dst_repo)
        SpotInteriorSubsystemCodec().restore(dst_runtime, captured)

        # restored interior: state / is_visible / detail_read_by が src と一致
        restored = dst_repo.find_by_spot_id(SpotId(1))
        assert restored is not None
        restored_obj = restored.objects[0]
        assert restored_obj.state == {"door_open": True}
        assert restored_obj.is_visible is False
        assert restored_obj.detail_read_by == frozenset({2, 5})
        # 静的 metadata (name 等) は dst 側のまま
        assert restored_obj.name == "door"

    def test_ground_items_replace_existing_items(self) -> None:
        """grounditems は完全置換。"""
        src_interior = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(
                GroundItem(
                    item_instance_id=ItemInstanceId(7),
                    item_spec_id=ItemSpecId(70),
                ),
            ),
            discoverable_items=(),
        )
        src_repo = InMemorySpotInteriorRepository(
            {SpotId(1): src_interior}
        )
        captured = SpotInteriorSubsystemCodec().capture(
            SimpleNamespace(_spot_interior_repo=src_repo)
        )

        # dst: 空 ground_items
        dst_interior = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(),
            discoverable_items=(),
        )
        dst_repo = InMemorySpotInteriorRepository(
            {SpotId(1): dst_interior}
        )
        SpotInteriorSubsystemCodec().restore(
            SimpleNamespace(_spot_interior_repo=dst_repo), captured
        )
        restored = dst_repo.find_by_spot_id(SpotId(1))
        assert restored is not None
        assert len(restored.ground_items) == 1
        assert restored.ground_items[0].item_instance_id == ItemInstanceId(7)

    def test_discoverable_item_discovered_round_trips(self) -> None:
        """discoverable item is discovered 往復。"""
        src = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(),
            discoverable_items=(_disc(spec_id=100, is_discovered=True),),
        )
        src_repo = InMemorySpotInteriorRepository({SpotId(1): src})
        captured = SpotInteriorSubsystemCodec().capture(
            SimpleNamespace(_spot_interior_repo=src_repo)
        )
        dst = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(),
            discoverable_items=(_disc(spec_id=100, is_discovered=False),),
        )
        dst_repo = InMemorySpotInteriorRepository({SpotId(1): dst})
        SpotInteriorSubsystemCodec().restore(
            SimpleNamespace(_spot_interior_repo=dst_repo), captured
        )
        restored = dst_repo.find_by_spot_id(SpotId(1))
        assert restored is not None
        assert restored.discoverable_items[0].is_discovered is True

    def test_sub_location_hidden_round_trips(self) -> None:
        """sub location is hidden 往復。"""
        src = SpotInterior(
            sub_locations=(_sub_loc(sub_id=1, is_hidden=False),),
            objects=(),
            ground_items=(),
            discoverable_items=(),
        )
        captured = SpotInteriorSubsystemCodec().capture(
            SimpleNamespace(
                _spot_interior_repo=InMemorySpotInteriorRepository(
                    {SpotId(1): src}
                )
            )
        )
        dst = SpotInterior(
            sub_locations=(_sub_loc(sub_id=1, is_hidden=True),),
            objects=(),
            ground_items=(),
            discoverable_items=(),
        )
        dst_repo = InMemorySpotInteriorRepository({SpotId(1): dst})
        SpotInteriorSubsystemCodec().restore(
            SimpleNamespace(_spot_interior_repo=dst_repo), captured
        )
        restored = dst_repo.find_by_spot_id(SpotId(1))
        assert restored is not None
        assert restored.sub_locations[0].is_hidden is False

    def test_puzzle_state_round_trips(self) -> None:
        """puzzle state 往復。"""
        src_puzzle = PuzzleState(
            puzzle_type="combination_lock",
            solution=("1", "2", "3"),
            current_input=("1", "2"),
            is_solved=False,
            attempts=2,
        )
        src_obj = _spot_obj(object_id=1, puzzle=src_puzzle)
        src_interior = SpotInterior(
            sub_locations=(),
            objects=(src_obj,),
            ground_items=(),
            discoverable_items=(),
        )
        captured = SpotInteriorSubsystemCodec().capture(
            SimpleNamespace(
                _spot_interior_repo=InMemorySpotInteriorRepository(
                    {SpotId(1): src_interior}
                )
            )
        )
        # dst: 初期 puzzle (current_input 空)
        dst_puzzle = PuzzleState(
            puzzle_type="combination_lock", solution=("1", "2", "3")
        )
        dst_obj = _spot_obj(object_id=1, puzzle=dst_puzzle)
        dst_interior = SpotInterior(
            sub_locations=(),
            objects=(dst_obj,),
            ground_items=(),
            discoverable_items=(),
        )
        dst_repo = InMemorySpotInteriorRepository({SpotId(1): dst_interior})
        SpotInteriorSubsystemCodec().restore(
            SimpleNamespace(_spot_interior_repo=dst_repo), captured
        )
        restored_puzzle = dst_repo.find_by_spot_id(SpotId(1)).objects[0].puzzle
        assert restored_puzzle is not None
        assert restored_puzzle.current_input == ("1", "2")
        assert restored_puzzle.attempts == 2

    def test_snapshot_spot_skip(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """snapshot に SpotId(99) のデータがあるが dst には spot がない → skip。"""
        src = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(),
            discoverable_items=(),
        )
        captured = SpotInteriorSubsystemCodec().capture(
            SimpleNamespace(
                _spot_interior_repo=InMemorySpotInteriorRepository(
                    {SpotId(99): src}
                )
            )
        )
        # dst: 空 (SpotId(99) 自体がない)
        dst_repo = InMemorySpotInteriorRepository()
        with caplog.at_level("INFO"):
            SpotInteriorSubsystemCodec().restore(
                SimpleNamespace(_spot_interior_repo=dst_repo), captured
            )
        assert any("spot_id=99" in r.message for r in caplog.records)


class TestItemInstanceCodec:
    """ItemInstance の動的部分往復。"""

    def _make_spec(
        self, spec_id: int = 1, max_stack: int = 99, durability_max: int = None
    ) -> ItemSpec:
        return ItemSpec(
            item_spec_id=ItemSpecId(spec_id),
            name="potion",
            description="heals 10",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            max_stack_size=MaxStackSize(max_stack),
            durability_max=durability_max,
        )

    def test_quantity_state_round_trips(self) -> None:
        """数量と instance ごとの state を保存すると、別 aggregate に同じ値で復元される。"""
        spec = self._make_spec(spec_id=1, max_stack=99)
        src_inst = ItemInstance(
            item_instance_id=ItemInstanceId(10),
            item_spec=spec,
            quantity=5,
            state={"opened": True, "remaining": 3},
        )
        src_agg = ItemAggregate(src_inst)
        # repo stub with find_all + find_by_id + save
        repo_store: dict[ItemInstanceId, ItemAggregate] = {
            ItemInstanceId(10): src_agg
        }
        src_repo = SimpleNamespace(
            find_all=lambda: list(repo_store.values()),
            find_by_id=lambda iid: repo_store.get(iid),
            save=lambda agg: repo_store.update({agg.item_instance_id: agg}),
        )
        captured = ItemInstanceSubsystemCodec().capture(
            SimpleNamespace(_item_repo=src_repo)
        )
        assert captured["schema_version"] == 2
        assert captured["entries"][0]["item_spec_id"] == 1

        # dst: 初期状態の同 ID (quantity=1, state 空)
        dst_inst = ItemInstance(
            item_instance_id=ItemInstanceId(10),
            item_spec=spec,
            quantity=1,
        )
        dst_agg = ItemAggregate(dst_inst)
        dst_store: dict[ItemInstanceId, ItemAggregate] = {
            ItemInstanceId(10): dst_agg
        }
        dst_repo = SimpleNamespace(
            find_all=lambda: list(dst_store.values()),
            find_by_id=lambda iid: dst_store.get(iid),
            save=lambda agg: dst_store.update({agg.item_instance_id: agg}),
        )
        ItemInstanceSubsystemCodec().restore(
            SimpleNamespace(_item_repo=dst_repo), captured
        )
        restored = dst_store[ItemInstanceId(10)].item_instance
        assert restored.quantity == 5
        assert restored.state == {"opened": True, "remaining": 3}

    def test_legacy_schema_without_item_spec_id_restores_existing_instance(self) -> None:
        """旧 schema の payload は、復元先に同じ instance があれば動的部分だけ復元する。"""
        spec = self._make_spec(spec_id=1, max_stack=99)
        captured = {
            "schema_version": 1,
            "entries": [
                {
                    "item_instance_id": 10,
                    "quantity": 5,
                    "durability_current": None,
                    "state": {"legacy": True},
                }
            ],
        }
        dst_store = {
            ItemInstanceId(10): ItemAggregate(
                ItemInstance(
                    item_instance_id=ItemInstanceId(10),
                    item_spec=spec,
                    quantity=1,
                )
            )
        }

        ItemInstanceSubsystemCodec().restore(
            SimpleNamespace(
                _item_repo=SimpleNamespace(
                    find_by_id=lambda iid: dst_store.get(iid),
                    save=lambda agg: dst_store.update({agg.item_instance_id: agg}),
                )
            ),
            captured,
        )

        restored = dst_store[ItemInstanceId(10)].item_instance
        assert restored.quantity == 5
        assert restored.state == {"legacy": True}

    def test_restore_recreates_dynamic_item_instance_from_item_spec_repo(self) -> None:
        """復元先に ``ItemInstance`` が無くても、同じ ``ItemSpec`` があれば再生成する。

        実行中に収穫などで作られた ``ItemInstance`` は、新 runtime には初期配置
        されていない。ここを飛ばすと inventory だけが復元され、item 本体が欠ける
        ため、実験再開後に参照不能になる。
        """
        spec = self._make_spec(spec_id=3, max_stack=99)
        src_inst = ItemInstance(
            item_instance_id=ItemInstanceId(30),
            item_spec=spec,
            quantity=4,
            state={"fresh": True},
        )
        captured = ItemInstanceSubsystemCodec().capture(
            SimpleNamespace(
                _item_repo=SimpleNamespace(find_all=lambda: [ItemAggregate(src_inst)])
            )
        )

        dst_store: dict[ItemInstanceId, ItemAggregate] = {}
        dst_repo = SimpleNamespace(
            find_all=lambda: list(dst_store.values()),
            find_by_id=lambda iid: dst_store.get(iid),
            save=lambda agg: dst_store.update({agg.item_instance_id: agg}),
        )
        dst_spec_repo = SimpleNamespace(
            find_by_id=lambda spec_id: SimpleNamespace(
                to_item_spec=lambda: spec if spec_id == spec.item_spec_id else None
            )
        )

        ItemInstanceSubsystemCodec().restore(
            SimpleNamespace(_item_repo=dst_repo, _item_spec_repo=dst_spec_repo),
            captured,
        )

        restored = dst_store[ItemInstanceId(30)].item_instance
        assert restored.item_spec.item_spec_id == ItemSpecId(3)
        assert restored.quantity == 4
        assert restored.state == {"fresh": True}

    def test_missing_dynamic_item_without_item_spec_id_fails_fast(self) -> None:
        """旧 schema に再生成用の ``item_spec_id`` が無い場合は復元を止める。"""
        captured = {
            "schema_version": 1,
            "entries": [
                {
                    "item_instance_id": 30,
                    "quantity": 1,
                    "durability_current": None,
                    "state": {},
                }
            ],
        }

        with pytest.raises(RuntimeError, match="cannot be resolved"):
            ItemInstanceSubsystemCodec().restore(
                SimpleNamespace(
                    _item_repo=SimpleNamespace(
                        find_by_id=lambda iid: None,
                        save=lambda agg: None,
                    )
                ),
                captured,
            )

    def test_existing_instance_spec_mismatch_fails_fast(self) -> None:
        """同じ instance ID が別 ``ItemSpec`` を指していれば復元を止める。"""
        snapshot_spec = self._make_spec(spec_id=5, max_stack=99)
        current_spec = self._make_spec(spec_id=6, max_stack=99)
        captured = ItemInstanceSubsystemCodec().capture(
            SimpleNamespace(
                _item_repo=SimpleNamespace(
                    find_all=lambda: [
                        ItemAggregate(
                            ItemInstance(
                                item_instance_id=ItemInstanceId(50),
                                item_spec=snapshot_spec,
                                quantity=2,
                            )
                        )
                    ]
                )
            )
        )
        dst_store = {
            ItemInstanceId(50): ItemAggregate(
                ItemInstance(
                    item_instance_id=ItemInstanceId(50),
                    item_spec=current_spec,
                    quantity=1,
                )
            )
        }

        with pytest.raises(RuntimeError, match="spec mismatch"):
            ItemInstanceSubsystemCodec().restore(
                SimpleNamespace(
                    _item_repo=SimpleNamespace(
                        find_by_id=lambda iid: dst_store.get(iid),
                        save=lambda agg: dst_store.update({agg.item_instance_id: agg}),
                    )
                ),
                captured,
            )

    def test_quantity_incompatible_with_current_spec_fails_fast(self) -> None:
        """現 ``ItemSpec`` の最大スタック数に合わない数量なら復元を止める。"""
        src_spec = self._make_spec(spec_id=7, max_stack=99)
        current_spec = self._make_spec(spec_id=7, max_stack=1)
        captured = ItemInstanceSubsystemCodec().capture(
            SimpleNamespace(
                _item_repo=SimpleNamespace(
                    find_all=lambda: [
                        ItemAggregate(
                            ItemInstance(
                                item_instance_id=ItemInstanceId(70),
                                item_spec=src_spec,
                                quantity=5,
                            )
                        )
                    ]
                )
            )
        )
        dst_store = {
            ItemInstanceId(70): ItemAggregate(
                ItemInstance(
                    item_instance_id=ItemInstanceId(70),
                    item_spec=current_spec,
                    quantity=1,
                )
            )
        }

        with pytest.raises(RuntimeError, match="snapshot does not match"):
            ItemInstanceSubsystemCodec().restore(
                SimpleNamespace(
                    _item_repo=SimpleNamespace(
                        find_by_id=lambda iid: dst_store.get(iid),
                        save=lambda agg: dst_store.update({agg.item_instance_id: agg}),
                    )
                ),
                captured,
            )

    def test_quantity_zero_round_trips(self) -> None:
        """``quantity=0`` もスナップショット上の状態として復元する。

        通常操作用の ``set_quantity`` は 0 を拒否するが、snapshot restore は
        保存済み状態の再現なので、使用済みなどで 0 になった instance を
        1 のまま残してはいけない。
        """
        spec = self._make_spec(spec_id=4, max_stack=99)
        src_inst = ItemInstance(
            item_instance_id=ItemInstanceId(40),
            item_spec=spec,
            quantity=0,
        )
        captured = ItemInstanceSubsystemCodec().capture(
            SimpleNamespace(
                _item_repo=SimpleNamespace(find_all=lambda: [ItemAggregate(src_inst)])
            )
        )
        dst_inst = ItemInstance(
            item_instance_id=ItemInstanceId(40),
            item_spec=spec,
            quantity=1,
        )
        dst_store = {ItemInstanceId(40): ItemAggregate(dst_inst)}

        ItemInstanceSubsystemCodec().restore(
            SimpleNamespace(
                _item_repo=SimpleNamespace(
                    find_by_id=lambda iid: dst_store.get(iid),
                    save=lambda agg: dst_store.update({agg.item_instance_id: agg}),
                )
            ),
            captured,
        )

        assert dst_store[ItemInstanceId(40)].item_instance.quantity == 0

    def test_durability_round_trips(self) -> None:
        """耐久度の現在値を保存すると、別 aggregate に同じ値で復元される。"""
        spec = self._make_spec(spec_id=2, max_stack=1, durability_max=100)
        src_inst = ItemInstance(
            item_instance_id=ItemInstanceId(20),
            item_spec=spec,
            durability=Durability(max_value=100, current=42),
            quantity=1,
        )
        src_agg = ItemAggregate(src_inst)
        store = {ItemInstanceId(20): src_agg}
        captured = ItemInstanceSubsystemCodec().capture(
            SimpleNamespace(
                _item_repo=SimpleNamespace(
                    find_all=lambda: list(store.values()),
                    find_by_id=lambda i: store.get(i),
                    save=lambda a: store.update({a.item_instance_id: a}),
                )
            )
        )
        # dst: 同 ID で初期 durability 100
        dst_inst = ItemInstance(
            item_instance_id=ItemInstanceId(20),
            item_spec=spec,
            durability=Durability(max_value=100, current=100),
            quantity=1,
        )
        dst_agg = ItemAggregate(dst_inst)
        dst_store = {ItemInstanceId(20): dst_agg}
        ItemInstanceSubsystemCodec().restore(
            SimpleNamespace(
                _item_repo=SimpleNamespace(
                    find_all=lambda: list(dst_store.values()),
                    find_by_id=lambda i: dst_store.get(i),
                    save=lambda a: dst_store.update({a.item_instance_id: a}),
                )
            ),
            captured,
        )
        assert dst_store[ItemInstanceId(20)].item_instance.durability.current == 42

    def test_missing_item_spec_for_dynamic_instance_fails_fast(self) -> None:
        """復元先に instance も ``ItemSpec`` も無ければ孤児参照防止のため復元を止める。"""
        captured = {
            "schema_version": 2,
            "entries": [
                {
                    "item_instance_id": 999,
                    "item_spec_id": 999,
                    "quantity": 1,
                    "durability_current": None,
                    "state": {},
                }
            ],
        }

        with pytest.raises(RuntimeError, match="cannot be resolved"):
            ItemInstanceSubsystemCodec().restore(
                SimpleNamespace(
                    _item_repo=SimpleNamespace(
                        find_all=lambda: [],
                        find_by_id=lambda i: None,
                        save=lambda a: None,
                    ),
                    _item_spec_repo=SimpleNamespace(find_by_id=lambda i: None),
                ),
                captured,
            )


class TestUnsupportedSchemaVersion:
    @pytest.mark.parametrize(
        "codec_cls",
        [SpotInteriorSubsystemCodec, ItemInstanceSubsystemCodec],
    )
    def test_unsupported_schema_version_raises_exception(self, codec_cls) -> None:
        """未サポート schemaversion は例外。"""
        codec = codec_cls()
        with pytest.raises(ValueError, match="schema_version"):
            codec.restore(SimpleNamespace(), {"schema_version": 999})
