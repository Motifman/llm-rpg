"""FoodSpoilageStageService の挙動検証 (Phase D-2)。

acquired_at_tick の遅延初期化、閾値到達での spoiled フラグ、callback の二重発火
防止、None spec (腐らない設定) を扱わないことなどを確認する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.food_spoilage_stage_service import (
    STATE_KEY_ACQUIRED_AT_TICK,
    STATE_KEY_SPOILED,
    FoodSpoilageStageService,
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
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 8},
        )

        stage.run(WorldTick(3))

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_ACQUIRED_AT_TICK] == 3
        assert reloaded.state.get(STATE_KEY_SPOILED) is not True

    def test_acquired_tick(self, repo_with_raw_fish) -> None:
        """既に acquired at tick があれば上書きしない。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 10})
        repo.save(inst)
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 8},
        )

        stage.run(WorldTick(11))

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_ACQUIRED_AT_TICK] == 10


class TestSpoiledFlag:
    """spoils_after_ticks 経過時に spoiled が立つ挙動。"""

    def test_value_spoiled_2(self, repo_with_raw_fish) -> None:
        """閾値未到達なら spoiled は立たない。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 8},
        )

        stage.run(WorldTick(7))

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state.get(STATE_KEY_SPOILED) is not True

    def test_value_spoiled(self, repo_with_raw_fish) -> None:
        """閾値到達ちょうどで spoiled が立つ。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 8},
        )

        stage.run(WorldTick(8))

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_SPOILED] is True

    def test_value_exceeds_spoiled(self, repo_with_raw_fish) -> None:
        """閾値超過でも spoiled が立つ。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 8},
        )

        stage.run(WorldTick(20))

        reloaded = repo.find_by_id(inst.item_instance_id)
        assert reloaded.state[STATE_KEY_SPOILED] is True


class TestCallback:
    """spoiled_callback の呼び出し挙動。"""

    def test_calls_when_spoiled_callback(self, repo_with_raw_fish) -> None:
        """腐ったとき callbackが呼ばれる。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        calls: list[tuple] = []
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 8},
            spec_name_lookup=lambda sid: "生の魚",
            spoiled_callback=lambda iid, sid, name: calls.append((iid.value, sid.value, name)),
        )

        stage.run(WorldTick(8))

        assert calls == [(7001, 101, "生の魚")]

    def test_callback_does_not_trigger(self, repo_with_raw_fish) -> None:
        """callbackは二重発火しない。"""
        repo, inst = repo_with_raw_fish
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        calls: list[tuple] = []
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 8},
            spoiled_callback=lambda iid, sid, name: calls.append((iid.value,)),
        )

        stage.run(WorldTick(8))
        stage.run(WorldTick(9))
        stage.run(WorldTick(50))

        assert len(calls) == 1


class TestSpoiledBatchCallback:
    """#343 対策: 同 tick の複数 instance を 1 件に集約する batch callback。"""

    def test_calls_tick_multiple_instance_one_batch(self) -> None:
        """同 tick の複数 instance は 1batch で呼ばれる。"""
        data_store = InMemoryDataStore()
        repo = InMemoryItemRepository(data_store)
        spec = _spec(RAW_FISH_SPEC_ID, "生の魚", spoils_after_ticks=4)
        for iid in (7001, 7002, 7003):
            inst = ItemAggregate.create(
                item_instance_id=ItemInstanceId(iid),
                item_spec=spec,
                quantity=1,
            )
            inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
            repo.save(inst)

        batches: list = []
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 4},
            spec_name_lookup=lambda sid: "生の魚",
            spoiled_batch_callback=lambda items: batches.append(items),
        )

        stage.run(WorldTick(4))

        # 1 回の callback で 3 instance を受け取る
        assert len(batches) == 1
        assert len(batches[0]) == 3
        assert {iid.value for iid, _, _ in batches[0]} == {7001, 7002, 7003}

    def test_does_not_call_tick_batch_callback(
        self,
    ) -> None:
        """この tick で何も腐っていなければ batchcallback は呼ばれない。"""
        data_store = InMemoryDataStore()
        repo = InMemoryItemRepository(data_store)
        spec = _spec(RAW_FISH_SPEC_ID, "生の魚", spoils_after_ticks=10)
        inst = ItemAggregate.create(
            item_instance_id=ItemInstanceId(7001),
            item_spec=spec,
            quantity=1,
        )
        inst.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repo.save(inst)
        batches: list = []
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={RAW_FISH_SPEC_ID: 10},
            spoiled_batch_callback=lambda items: batches.append(items),
        )

        stage.run(WorldTick(3))  # 閾値未到達

        assert batches == []


class TestEmptySpoilableSpecs:
    """空 dict のときは no-op になる (シナリオに腐る食料が無いとき)。"""

    def test_no_spoilable_items_leaves_state_unchanged(self, repo_with_raw_fish) -> None:
        """腐るアイテムが無ければ何もしない。"""
        repo, inst = repo_with_raw_fish
        stage = FoodSpoilageStageService(
            item_repository=repo,
            spoilable_specs={},
        )

        stage.run(WorldTick(100))

        reloaded = repo.find_by_id(inst.item_instance_id)
        # 何も書き込まれない (acquired_at_tick すら入らない)
        assert STATE_KEY_ACQUIRED_AT_TICK not in reloaded.state
