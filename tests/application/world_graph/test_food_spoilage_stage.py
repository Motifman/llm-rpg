"""FoodSpoilageStageService の腐敗規則を指定repository上で検証する。"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.application.world_graph.food_spoilage_stage_service import (
    FoodSpoilageStageService,
)
from ai_rpg_world.domain.item.value_object.spoilage import (
    STATE_KEY_ACQUIRED_AT_TICK,
    STATE_KEY_SPOILED,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)


RAW_FISH_SPEC_ID = ItemSpecId.create(101)
COCONUT_SPEC_ID = ItemSpecId.create(102)


def _spec(spec_id: ItemSpecId, name: str, *, spoils_after_ticks=None) -> ItemSpec:
    return ItemSpec(
        item_spec_id=spec_id,
        name=name,
        item_type=ItemType.QUEST,
        rarity=Rarity.COMMON,
        description=name,
        max_stack_size=MaxStackSize(1),
        spoils_after_ticks=spoils_after_ticks,
    )


@pytest.fixture
def repo_with_raw_fish():
    data_store = InMemoryDataStore()
    repo = InMemoryItemRepository(data_store)
    spec = _spec(RAW_FISH_SPEC_ID, "生の魚", spoils_after_ticks=8)
    inst = ItemAggregate.create(
        item_instance_id=ItemInstanceId(7001),
        item_spec=spec,
        quantity=1,
    )
    repo.save(inst)
    return repo, inst


class TestAcquiredAtTickLazyInit:
    """acquired_at_tick の遅延初期化挙動。"""

    def test_run_acquired_tick_recorded(self, repo_with_raw_fish) -> None:
        """最初の run で acquired at tick が記録される。"""
        repo, inst = repo_with_raw_fish
        stage = FoodSpoilageStageService(spoilable_specs={RAW_FISH_SPEC_ID: 8})

        stage._run_with_repository(WorldTick(3), repo)

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_ACQUIRED_AT_TICK] == 3
        assert reloaded.state.get(STATE_KEY_SPOILED) is not True

    def test_acquired_tick(self, repo_with_raw_fish) -> None:
        """既に acquired at tick があれば上書きしない。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 10})
        repo.save(inst)
        stage = FoodSpoilageStageService(spoilable_specs={RAW_FISH_SPEC_ID: 8})

        stage._run_with_repository(WorldTick(11), repo)

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_ACQUIRED_AT_TICK] == 10


class TestSpoiledFlag:
    """spoils_after_ticks 経過時に spoiled が立つ挙動。"""

    def test_value_spoiled_2(self, repo_with_raw_fish) -> None:
        """閾値未到達なら spoiled は立たない。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        stage = FoodSpoilageStageService(spoilable_specs={RAW_FISH_SPEC_ID: 8})

        stage._run_with_repository(WorldTick(7), repo)

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state.get(STATE_KEY_SPOILED) is not True

    def test_value_spoiled(self, repo_with_raw_fish) -> None:
        """閾値到達ちょうどで spoiled が立つ。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        stage = FoodSpoilageStageService(spoilable_specs={RAW_FISH_SPEC_ID: 8})

        stage._run_with_repository(WorldTick(8), repo)

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_SPOILED] is True

    def test_value_exceeds_spoiled(self, repo_with_raw_fish) -> None:
        """閾値超過でも spoiled が立つ。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        stage = FoodSpoilageStageService(spoilable_specs={RAW_FISH_SPEC_ID: 8})

        stage._run_with_repository(WorldTick(20), repo)

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_SPOILED] is True


class TestEmptySpoilableSpecs:
    """空 dict のときは no-op になる (シナリオに腐る食料が無いとき)。"""

    def test_no_spoilable_items_leaves_state_unchanged(self, repo_with_raw_fish) -> None:
        """腐るアイテムが無ければ何もしない。"""
        repo, inst = repo_with_raw_fish
        stage = FoodSpoilageStageService(spoilable_specs={})

        stage.run(WorldTick(100))

        reloaded = repo.find_by_id(inst.item_instance_id)
        # 何も書き込まれない (acquired_at_tick すら入らない)
        assert STATE_KEY_ACQUIRED_AT_TICK not in reloaded.state


class TestInvalidAcquiredAtTick:
    """不正 acquired_at_tick の warning と spoiled 非更新。"""

    def test_invalid_acquired_at_tick_logs_warning_and_skips_spoilage(
        self, repo_with_raw_fish, caplog
    ) -> None:
        """acquired_at_tick が int 以外なら warning を出し spoiled は立たない。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: "bad"})
        repo.save(inst)
        stage = FoodSpoilageStageService(spoilable_specs={RAW_FISH_SPEC_ID: 8})

        with caplog.at_level(logging.WARNING):
            stage._run_with_repository(WorldTick(100), repo)

        assert "non-int acquired_at_tick" in caplog.text
        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_ACQUIRED_AT_TICK] == "bad"
        assert reloaded.state.get(STATE_KEY_SPOILED) is not True
