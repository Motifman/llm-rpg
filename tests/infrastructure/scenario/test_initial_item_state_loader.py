"""シナリオ JSON の `initial_items` に initial state を仕込めることのテスト。

Phase 4-D で `InitialItemSpec` を導入し、loader が以下 2 形式を受け付ける:

- `"spec_string_id"` (文字列): state なし。Phase 4-A 以前と完全互換
- `{"spec": "spec_string_id", "state": {...}}`: per-instance state を仕込む

どちらも `InitialItemSpec(spec_id, state)` に正規化される。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_initial_items_to_inventory,
)
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_initial_items(initial_items_raw) -> dict:
    """1 player + 任意の initial_items を持つ最小シナリオ。"""
    return {
        "scenario_format_version": "1.0",
        "metadata": {
            "id": "x", "title": "x", "description": "x",
            "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
            "author": "x", "tags": [],
        },
        "item_specs": [
            {"id": "torch", "name": "松明", "description": "d", "category": "MATERIAL"},
            {"id": "match", "name": "マッチ", "description": "d", "category": "MATERIAL"},
        ],
        "environment": {
            "weather": {"enabled": False, "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                        "update_interval_ticks": 100, "announce_changes": False},
        },
        "spots": [{
            "id": "s", "name": "S", "description": "d", "category": "OTHER",
            "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
            "interior": {"objects": []},
        }],
        "connections": [],
        "players": [{
            "id": "p", "name": "P", "spawn_spot": "s",
            "initial_items": initial_items_raw,
        }],
        "game_end_conditions": {"win": [], "lose": []},
    }


class TestInitialItemSpecParsing:
    """`initial_items` の各形式が `InitialItemSpec` に正しく正規化される。"""

    def test_string_form_has_empty_state(self) -> None:
        """文字列形式は state を空 dict として正規化される (旧シナリオと互換)。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_initial_items(["torch"])
        )
        spawn = result.player_spawns[0]
        assert len(spawn.initial_items) == 1
        item = spawn.initial_items[0]
        assert item.spec_id.value == result.id_mapper.get_int("item_spec", "torch")
        assert item.state == {}

    def test_dict_form_with_state(self) -> None:
        """dict 形式は spec + state を正しく分離する。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_initial_items([
                {"spec": "torch", "state": {"lit": False, "fuel": 100}},
            ])
        )
        item = result.player_spawns[0].initial_items[0]
        assert item.spec_id.value == result.id_mapper.get_int("item_spec", "torch")
        assert item.state == {"lit": False, "fuel": 100}

    def test_dict_form_without_state_key_defaults_to_empty(self) -> None:
        """dict 形式でも state キーが無ければ空 dict (state なしの dict 表記も許容)。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_initial_items([{"spec": "torch"}])
        )
        item = result.player_spawns[0].initial_items[0]
        assert item.state == {}

    def test_mixed_string_and_dict_forms(self) -> None:
        """同じ players entry 内で文字列形式と dict 形式の混在を許容する。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_initial_items([
                "torch",
                {"spec": "match", "state": {"used": False}},
            ])
        )
        items = result.player_spawns[0].initial_items
        assert len(items) == 2
        assert items[0].state == {}  # 文字列形式
        assert items[1].state == {"used": False}  # dict 形式


class TestInitialItemSpecValidation:
    """`initial_items` の不正な形式は `ScenarioLoadError` で拒否される。"""

    def test_dict_without_spec_rejected(self) -> None:
        """dict 形式で `spec` キーが無いと拒否。"""
        with pytest.raises(ScenarioLoadError, match="spec is required"):
            ScenarioLoader().load_from_dict(
                _scenario_with_initial_items([{"state": {"lit": True}}])
            )

    def test_state_not_dict_rejected(self) -> None:
        """`state` が dict 以外なら拒否。"""
        with pytest.raises(ScenarioLoadError, match="state must be an object"):
            ScenarioLoader().load_from_dict(
                _scenario_with_initial_items([
                    {"spec": "torch", "state": "lit=true"},
                ])
            )

    def test_non_string_non_dict_rejected(self) -> None:
        """文字列でも dict でもない要素 (null, int 等) は拒否。"""
        with pytest.raises(ScenarioLoadError, match="must be a string or object"):
            ScenarioLoader().load_from_dict(
                _scenario_with_initial_items([42])
            )


class TestGrantInitialItemsToInventory:
    """`grant_initial_items_to_inventory` が initial state 付きで instance を生成する。"""

    def _build_repos(self, loaded):
        data_store = InMemoryDataStore()
        item_repo = InMemoryItemRepository(data_store)
        item_spec_repo = InMemoryItemSpecRepository()
        for item_def in loaded.item_spec_definitions:
            item_spec_repo.save(
                ItemSpecReadModel(
                    item_spec_id=item_def.spec_id,
                    name=item_def.name,
                    item_type=ItemType.MATERIAL,
                    rarity=Rarity.COMMON,
                    description=item_def.description,
                    max_stack_size=MaxStackSize(99),
                )
            )
        inventory_repo = InMemoryPlayerInventoryRepository(data_store)
        return item_repo, item_spec_repo, inventory_repo

    def _state_of_first_instance(self, inv_repo, item_repo, player_id: PlayerId) -> dict:
        inv = inv_repo.find_by_id(player_id)
        for i in range(inv.max_slots):
            iid = inv.get_item_instance_id_by_slot(SlotId(i))
            if iid is None:
                continue
            agg = item_repo.find_by_id(iid)
            return dict(agg.state) if agg else {}
        return {}

    def test_state_is_persisted_on_generated_instance(self) -> None:
        """JSON の initial_items に state を仕込むと、その state を持つ instance が生成される。"""
        loaded = ScenarioLoader().load_from_dict(
            _scenario_with_initial_items([
                {"spec": "torch", "state": {"lit": False, "fuel": 100}},
            ])
        )
        item_repo, item_spec_repo, inv_repo = self._build_repos(loaded)
        pid = PlayerId(loaded.player_spawns[0].player_id)
        inv_repo.save(PlayerInventoryAggregate(player_id=pid))

        grant_initial_items_to_inventory(
            pid, loaded.player_spawns[0].initial_items,
            item_repo, item_spec_repo, inv_repo,
        )
        # instance が state を持って生成されている
        assert self._state_of_first_instance(inv_repo, item_repo, pid) == {
            "lit": False, "fuel": 100,
        }

    def test_string_form_yields_empty_state_instance(self) -> None:
        """文字列形式 (state なし) では instance.state は空 dict になる。"""
        loaded = ScenarioLoader().load_from_dict(
            _scenario_with_initial_items(["torch"])
        )
        item_repo, item_spec_repo, inv_repo = self._build_repos(loaded)
        pid = PlayerId(loaded.player_spawns[0].player_id)
        inv_repo.save(PlayerInventoryAggregate(player_id=pid))

        grant_initial_items_to_inventory(
            pid, loaded.player_spawns[0].initial_items,
            item_repo, item_spec_repo, inv_repo,
        )
        assert self._state_of_first_instance(inv_repo, item_repo, pid) == {}
