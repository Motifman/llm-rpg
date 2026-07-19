"""Phase 9-2b の 3 codec (inventory / growth / state_dict) 単体テスト。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    PlayerGrowthSubsystemCodec,
    PlayerInventorySubsystemCodec,
    PlayerStateDictSubsystemCodec,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import (
    ItemInstanceId,
)
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.enum.equipment_slot_type import (
    EquipmentSlotType,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
    StatGrowthFactor,
)


def _make_inventory_repo_stub(inv: PlayerInventoryAggregate):
    repo_store: dict[PlayerId, PlayerInventoryAggregate] = {inv.player_id: inv}
    return SimpleNamespace(
        find_by_id=lambda pid: repo_store.get(pid),
        save=lambda new_inv: repo_store.update({new_inv.player_id: new_inv}),
        _store=repo_store,  # test 用 introspection
    )


class TestPlayerInventoryCodec:
    """inventory / equipment / reserved の往復。"""

    def test_capture_restore_round_trip(self) -> None:
        src_inv = PlayerInventoryAggregate.restore_from_data(
            player_id=PlayerId(1),
            max_slots=5,
            inventory_slots={
                SlotId(0): ItemInstanceId(100),
                SlotId(1): None,
                SlotId(2): ItemInstanceId(200),
                SlotId(3): None,
                SlotId(4): None,
            },
            equipment_slots={
                EquipmentSlotType.WEAPON: ItemInstanceId(300),
                EquipmentSlotType.HELMET: None,
                EquipmentSlotType.ARMOR: None,
                EquipmentSlotType.SHIELD: None,
                EquipmentSlotType.ACCESSORY: None,
                EquipmentSlotType.BOOTS: None,
            },
            reserved_item_ids={ItemInstanceId(400)},
        )
        src_runtime = SimpleNamespace(
            _player_inventory_repo=_make_inventory_repo_stub(src_inv),
            get_player_ids=lambda: [PlayerId(1)],
        )
        captured = PlayerInventorySubsystemCodec().capture(src_runtime)
        entry = captured["entries"][0]
        assert entry["max_slots"] == 5
        assert {s["slot_id"]: s["item_instance_id"] for s in entry["inventory_slots"]} == {
            0: 100,
            1: None,
            2: 200,
            3: None,
            4: None,
        }
        assert entry["reserved_item_ids"] == [400]

        # 別 stub に restore
        dst_inv = PlayerInventoryAggregate.create_new_inventory(
            player_id=PlayerId(1), max_slots=5
        )
        dst_stub = _make_inventory_repo_stub(dst_inv)
        dst_runtime = SimpleNamespace(
            _player_inventory_repo=dst_stub,
            get_player_ids=lambda: [PlayerId(1)],
        )
        PlayerInventorySubsystemCodec().restore(dst_runtime, captured)

        restored = dst_stub._store[PlayerId(1)]
        assert restored._inventory_slots[SlotId(0)] == ItemInstanceId(100)
        assert restored._inventory_slots[SlotId(2)] == ItemInstanceId(200)
        assert restored._equipment_slots[EquipmentSlotType.WEAPON] == ItemInstanceId(300)
        assert restored._reserved_item_ids == {ItemInstanceId(400)}


class TestPlayerGrowthCodec:
    """growth + base_stats + growth_factor + exp_table の往復。"""

    def _make_status_stub(
        self,
        *,
        level: int = 1,
        total_exp: int = 0,
        max_hp: int = 100,
    ) -> Any:
        agg = SimpleNamespace()
        agg._base_stats = BaseStats(
            max_hp=max_hp,
            max_mp=50,
            attack=10,
            defense=8,
            speed=12,
            critical_rate=0.05,
            evasion_rate=0.03,
        )
        agg._stat_growth_factor = StatGrowthFactor(
            hp_factor=1.1,
            mp_factor=1.05,
            attack_factor=1.08,
            defense_factor=1.07,
            speed_factor=1.06,
            critical_rate_factor=1.01,
            evasion_rate_factor=1.01,
        )
        agg._exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        agg._growth = Growth(
            level=level, total_exp=total_exp, exp_table=agg._exp_table
        )
        agg._events = []
        return agg

    def test_capture_restore_round_trip_2(self) -> None:
        src_agg = self._make_status_stub(level=5, total_exp=1234, max_hp=150)
        src_repo: dict[PlayerId, Any] = {PlayerId(1): src_agg}
        src_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: src_repo.get(pid),
                save=lambda a: src_repo.update({PlayerId(1): a}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        captured = PlayerGrowthSubsystemCodec().capture(src_runtime)
        assert captured["entries"][0]["growth"]["level"] == 5
        assert captured["entries"][0]["growth"]["total_exp"] == 1234
        assert captured["entries"][0]["base_stats"]["max_hp"] == 150

        dst_agg = self._make_status_stub(level=1, total_exp=0, max_hp=100)
        dst_repo: dict[PlayerId, Any] = {PlayerId(1): dst_agg}
        dst_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: dst_repo.get(pid),
                save=lambda a: dst_repo.update({PlayerId(1): a}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        PlayerGrowthSubsystemCodec().restore(dst_runtime, captured)
        restored = dst_repo[PlayerId(1)]
        assert restored._growth.level == 5
        assert restored._growth.total_exp == 1234
        assert restored._base_stats.max_hp == 150


class TestPlayerStateDictCodec:
    """``_state`` dict の往復。"""

    def test_capture_restore_round_trip_3(self) -> None:
        agg = SimpleNamespace()
        agg._state = {"disguise_active": True, "scenario_flag_x": 42}
        agg._events = []
        src_repo: dict[PlayerId, Any] = {PlayerId(1): agg}
        src_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: src_repo.get(pid),
                save=lambda a: src_repo.update({PlayerId(1): a}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        captured = PlayerStateDictSubsystemCodec().capture(src_runtime)
        assert captured["entries"][0]["state"] == {
            "disguise_active": True,
            "scenario_flag_x": 42,
        }

        dst_agg = SimpleNamespace()
        dst_agg._state = {}
        dst_agg._events = []
        dst_repo: dict[PlayerId, Any] = {PlayerId(1): dst_agg}
        dst_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: dst_repo.get(pid),
                save=lambda a: dst_repo.update({PlayerId(1): a}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        PlayerStateDictSubsystemCodec().restore(dst_runtime, captured)
        assert dst_repo[PlayerId(1)]._state == {
            "disguise_active": True,
            "scenario_flag_x": 42,
        }

    def test_empty_state_works(self) -> None:
        """空 state でも 動く。"""
        agg = SimpleNamespace()
        agg._state = {}
        agg._events = []
        repo: dict[PlayerId, Any] = {PlayerId(1): agg}
        runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: repo.get(pid),
                save=lambda a: repo.update({PlayerId(1): a}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        captured = PlayerStateDictSubsystemCodec().capture(runtime)
        assert captured["entries"][0]["state"] == {}


class TestUnsupportedSchemaVersion:
    """3 codec すべて未サポート version で例外。"""

    @pytest.mark.parametrize(
        "codec_cls",
        [
            PlayerInventorySubsystemCodec,
            PlayerGrowthSubsystemCodec,
            PlayerStateDictSubsystemCodec,
        ],
    )
    def test_unsupported_schema_version_raises_exception(self, codec_cls) -> None:
        """未サポート schemaversion は例外。"""
        codec = codec_cls()
        with pytest.raises(ValueError, match="schema_version"):
            codec.restore(SimpleNamespace(), {"schema_version": 999, "entries": []})
