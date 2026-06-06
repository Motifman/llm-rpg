"""_use_item の腐敗食ダメージ経路 (Phase F)。

腐敗 instance を食べたら ConsumableUsedEvent を発行せず、直接 apply_damage が
呼ばれることを確認する。新鮮 instance では従来通り event 発行に到達する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SPOILED_FOOD_DAMAGE_HP,
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_effect import HealEffect
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize


SPEC_ID = ItemSpecId.create(101)


def _fish_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=SPEC_ID,
        name="生の魚",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description="魚",
        max_stack_size=MaxStackSize(1),
        consume_effect=HealEffect(amount=5),
    )


def _build_executor_with_item(state: dict) -> tuple[SpotGraphToolExecutor, MagicMock, MagicMock]:
    """生の魚 1 個を所持した状態の executor を組む。

    Returns:
        (executor, status_mock, event_publisher_mock)
    """
    services = SpotGraphWorldServices(
        interaction=MagicMock(),
        exploration=MagicMock(),
        world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
        game_end_evaluator=MagicMock(),
        exploration_progress=MagicMock(),
        movement=MagicMock(),
        simulation=None,
    )

    # ItemAggregate を 1 つ作って item_repository が返すように仕込む
    item = ItemAggregate.create(
        item_instance_id=ItemInstanceId(7001),
        item_spec=_fish_spec(),
        quantity=1,
        state=state,
    )

    item_repo = MagicMock()
    item_repo.find_by_id.return_value = item

    # インベントリにスロット 1 つ。aggregate 公開 API `find_slot_by_item_spec_id`
    # を mock する (実コードは executor でこの API を呼んで item_instance を探す)。
    from ai_rpg_world.domain.player.value_object.slot_id import SlotId
    inv = MagicMock()
    inv.find_slot_by_item_spec_id = MagicMock(
        return_value=(SlotId(0), ItemInstanceId(7001))
    )
    inv_repo = MagicMock()
    inv_repo.find_by_id.return_value = inv

    status = MagicMock()
    status_repo = MagicMock()
    status_repo.find_by_id.return_value = status

    event_publisher = MagicMock()

    executor = SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=inv_repo,
        item_repository=item_repo,
        player_status_repository=status_repo,
        event_publisher=event_publisher,
    )
    return executor, status, event_publisher


class TestSpoiledFoodDamage:
    """腐敗食を食べた時の挙動。"""

    def test_腐敗食を食べると_apply_damage_が呼ばれる(self) -> None:
        executor, status, _ = _build_executor_with_item({"spoiled": True})

        result = executor._use_item(player_id=1, args={"item_spec_id": 101})

        assert result.success is True
        status.apply_damage.assert_called_once_with(SPOILED_FOOD_DAMAGE_HP)

    def test_腐敗食では_ConsumableUsedEvent_は発行されない(self) -> None:
        executor, _, event_publisher = _build_executor_with_item({"spoiled": True})

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        # 通常パスでは publish が呼ばれるが、腐敗パスでは ConsumableUsedEvent
        # は出さない (回復効果を捨てるため)
        event_publisher.publish.assert_not_called()

    def test_腐敗食で_HP_0_になったら_status_events_が_publish_all_に乗る(self) -> None:
        """silent failure fix: spoiled パスで apply_damage が PlayerDownedEvent
        を積んだとき、それが publish_all に流れて DEAD outcome 連鎖が起きる
        ことを保証する。修正前は status events が捨てられていた。
        """
        from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        executor, status, event_publisher = _build_executor_with_item({"spoiled": True})
        # status mock が PlayerDownedEvent を積んだフリをする
        downed = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )
        status.get_events.return_value = [downed]

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        # publish_all で status events が流れる (実 callable 引数は list で来る)
        status.clear_events.assert_called_once()
        publish_all_calls = event_publisher.publish_all.call_args_list
        assert publish_all_calls, "publish_all が呼ばれていない"
        published = publish_all_calls[0].args[0]
        assert downed in published

    def test_腐敗食の_messageにダメージ表記が含まれる(self) -> None:
        executor, _, _ = _build_executor_with_item({"spoiled": True})

        result = executor._use_item(player_id=1, args={"item_spec_id": 101})

        assert "腐っていた" in result.message
        assert f"{SPOILED_FOOD_DAMAGE_HP}" in result.message


class TestFreshFoodPath:
    """新鮮食の通常経路 (Phase F の damage 追加で壊れていないことを確認)。"""

    def test_新鮮食では_apply_damage_は呼ばれない(self) -> None:
        executor, status, _ = _build_executor_with_item({})

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        status.apply_damage.assert_not_called()

    def test_新鮮食では_ConsumableUsedEvent_が発行される(self) -> None:
        executor, _, event_publisher = _build_executor_with_item({})

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        # 通常パスでは publish が呼ばれて handler 側で heal が走る
        event_publisher.publish.assert_called_once()
