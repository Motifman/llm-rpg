"""_use_item の腐敗食ダメージ経路 (Phase F)。

腐敗 instance を食べたら ConsumableUsedEvent を発行せず、直接 apply_damage が
呼ばれることを確認する。新鮮 instance では従来通り event 発行に到達する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.domain.item.value_object.spoiled_consumption import (
    SPOILED_FOOD_DAMAGE_HP,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    HealEffect,
    SatisfyNeedEffect,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    AvailableSlotLookup,
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.inventory_item_appearance import (
    InventoryItemAppearance,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.slot_id import SlotId


SPEC_ID = ItemSpecId.create(101)


def _fish_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=SPEC_ID,
        name="生の魚",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description="魚",
        max_stack_size=MaxStackSize(1),
        consume_effect=CompositeItemEffect(
            (
                HealEffect(amount=5),
                SatisfyNeedEffect(need_type_name="HUNGER", amount=35),
            )
        ),
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

    # インベントリにスロット 1 つ。aggregate 公開 API
    # `find_available_slot_by_item_spec_id_and_spoilage` を mock する。
    # is_spoiled を見て返す fake にし、腐敗 / 新鮮の撃ち分けをテスト側でも
    # 保証する (経済統合 Phase 2 で、予約を避けて探す API へ移行した)。
    inv = MagicMock(spec=PlayerInventoryAggregate)
    inv.iter_occupied_slots.return_value = [(SlotId(0), ItemInstanceId(7001))]

    def find_slot_by_spoilage(
        item_spec_id: ItemSpecId,
        is_spoiled: bool,
        appearances: dict[ItemInstanceId, InventoryItemAppearance],
    ):
        assert item_spec_id == SPEC_ID
        expected = InventoryItemAppearance(
            item_spec_id=SPEC_ID,
            is_spoiled=bool(state.get("spoiled")),
        )
        assert appearances.get(ItemInstanceId(7001)) == expected
        if bool(is_spoiled) != bool(state.get("spoiled")):
            return AvailableSlotLookup()
        return AvailableSlotLookup(
            slot_id=SlotId(0), item_instance_id=ItemInstanceId(7001)
        )

    inv.find_available_slot_by_item_spec_id_and_spoilage.side_effect = (
        find_slot_by_spoilage
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

    def test_calls_spoiled_food_apply_damage_and_partial_hunger_recovery(self) -> None:
        """腐敗食は10ダメージを受けるが、空腹回復だけは通常効果の半分が入る。"""
        executor, status, _ = _build_executor_with_item({"spoiled": True})

        result = executor._use_item(player_id=1, args={"item_spec_id": 101, "is_spoiled": True})

        assert result.success is True
        status.apply_damage.assert_called_once_with(SPOILED_FOOD_DAMAGE_HP)
        status.satisfy_need.assert_called_once_with(NeedType.HUNGER, 17)

    def test_spoiled_food_does_not_apply_heal_hp_effect(self) -> None:
        """腐敗食では consume_effect の heal_hp は適用せず、空腹の一部回復だけを直接適用する。"""
        executor, status, _ = _build_executor_with_item({"spoiled": True})

        executor._use_item(player_id=1, args={"item_spec_id": 101, "is_spoiled": True})

        status.heal_hp.assert_not_called()

    def test_consumable_used_event_not_published(self) -> None:
        """腐敗食では ConsumableUsedEvent は発行されない。"""
        executor, _, event_publisher = _build_executor_with_item({"spoiled": True})

        executor._use_item(player_id=1, args={"item_spec_id": 101, "is_spoiled": True})

        # 通常パスでは publish が呼ばれるが、腐敗パスでは ConsumableUsedEvent
        # は出さない (回復効果を捨てるため)
        event_publisher.publish.assert_not_called()

    def test_hp_zero_status_events_publish_all_included(self) -> None:
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

        executor._use_item(player_id=1, args={"item_spec_id": 101, "is_spoiled": True})

        # publish_all で status events が流れる (実 callable 引数は list で来る)。
        # 別途 ItemUsedEvent も publish_all で流れるため、複数回呼ばれる可能性が
        # あるので「いずれかの呼び出しに downed が含まれる」を確認する。
        status.clear_events.assert_called_once()
        publish_all_calls = event_publisher.publish_all.call_args_list
        assert publish_all_calls, "publish_all が呼ばれていない"
        all_published = [evt for call in publish_all_calls for evt in call.args[0]]
        assert downed in all_published

    def test_message_included(self) -> None:
        """腐敗食の messageにダメージ表記が含まれる。"""
        executor, _, _ = _build_executor_with_item({"spoiled": True})

        result = executor._use_item(player_id=1, args={"item_spec_id": 101, "is_spoiled": True})

        assert "腐っていた" in result.message
        assert f"{SPOILED_FOOD_DAMAGE_HP}" in result.message
        assert "少し空腹" in result.message


class TestFreshFoodPath:
    """新鮮食の通常経路 (Phase F の damage 追加で壊れていないことを確認)。"""

    def test_does_not_call_fresh_food_apply_damage(self) -> None:
        """新鮮食では apply damage は呼ばれない。"""
        executor, status, _ = _build_executor_with_item({})

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        status.apply_damage.assert_not_called()
        status.satisfy_need.assert_not_called()

    def test_consumable_used_event_published(self) -> None:
        """新鮮食では ConsumableUsedEvent が発行される。"""
        executor, _, event_publisher = _build_executor_with_item({})

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        # 通常パスでは publish が呼ばれて handler 側で heal が走る
        event_publisher.publish.assert_called_once()


class TestUseItemSilentFailures:
    """use_item の silent failure 回帰テスト。"""

    def test_item_used_event_publish_all_via_event_publisher(self) -> None:
        """ItemAggregate.use() が積んだ ItemUsedEvent を drain して publish する。

        守っているのは「観測が届くこと」ではない (この event を受け取る
        handler は存在しない)。**集約が event を抱えたまま save されないこと**
        である。抱えたまま保存すると、次に同じ instance を find して
        get_events() したときに陳腐化した event が別の文脈で流れる
        (Phase G #3 と同じ罠)。

        publish 先が無くても drain だけすれば足りるが、「積んだら drain して
        publish」を例外なく守るほうが、消費者の有無で扱いを変えるより
        壊れにくい。
        """
        from ai_rpg_world.domain.item.event.item_event import ItemUsedEvent
        executor, _, event_publisher = _build_executor_with_item({})

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        all_published = [
            evt
            for call in event_publisher.publish_all.call_args_list
            for evt in call.args[0]
        ]
        assert any(isinstance(e, ItemUsedEvent) for e in all_published), (
            f"ItemUsedEvent が publish_all に流れていない: {all_published!r}"
        )

    def test_aggregate_does_not_keep_the_event_after_use(self) -> None:
        """use() 後の集約に event が残らない。

        publish のテストだけだと clear_events を消しても通ってしまう。
        陳腐化 event の再放出を防いでいるのは publish ではなく clear のほう
        なので、そちらを直接固定する。
        """
        executor, _, _ = _build_executor_with_item({})
        item = executor._item_repository.find_by_id(ItemInstanceId(7001))

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        assert tuple(item.get_events()) == (), (
            f"use() 後も集約が event を抱えている: {item.get_events()!r}"
        )

    def test_calls_quantity_zero_inventory_save_item_delete(self) -> None:
        """非アトミック削除の順序回帰: item_repository.delete を先にすると、
        delete 成功・inv save 失敗時に「slot に存在しない instance_id が残り続け
        以降の lookup が全部 None」となる silent failure を生む。順序を逆転
        させるとこのテストが落ちて気付ける。
        """
        executor, _, _ = _build_executor_with_item({})
        # item_repo / inv_repo は MagicMock なので各操作の順序を call_order で追える
        item_repo = executor._item_repository
        inv_repo = executor._player_inventory_repository

        # 親 Mock に各子を attach して call_order を統一する
        parent = MagicMock()
        parent.attach_mock(item_repo.delete, "item_delete")
        parent.attach_mock(inv_repo.save, "inv_save")

        executor._use_item(player_id=1, args={"item_spec_id": 101})

        call_names = [c[0] for c in parent.mock_calls]
        assert "inv_save" in call_names and "item_delete" in call_names, (
            f"両方呼ばれていない: {call_names}"
        )
        assert call_names.index("inv_save") < call_names.index("item_delete"), (
            f"inv_save は item_delete より先でなければならない: {call_names}"
        )
