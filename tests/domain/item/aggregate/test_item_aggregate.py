import pytest
from src.domain.item.aggregate.item_aggregate import ItemAggregate
from src.domain.item.entity.item_instance import ItemInstance
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.value_object.durability import Durability
from src.domain.item.event.item_event import ItemUsedEvent, ItemBrokenEvent, ItemCraftedEvent, ItemRepairedEvent
from src.domain.item.enum.item_enum import ItemType, Rarity
from src.domain.item.exception import ItemSpecValidationException, DurabilityValidationException, QuantityValidationException, InsufficientQuantityException


class TestItemAggregate:
    """ItemAggregate集約のテスト"""

    @pytest.fixture
    def sample_item_spec_no_durability(self):
        """耐久度なしのアイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(1),
            name="Test Item",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="A test item without durability",
            max_stack_size=MaxStackSize(64)
        )

    @pytest.fixture
    def sample_item_spec_with_durability(self):
        """耐久度ありのアイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(2),
            name="Durable Item",
            item_type=ItemType.WEAPON,
            rarity=Rarity.UNCOMMON,
            description="A test item with durability",
            max_stack_size=MaxStackSize(1),
            durability_max=100
        )

    @pytest.fixture
    def sample_durability_full(self):
        """満タン耐久度を作成"""
        return Durability(current=100, max_value=100)

    @pytest.fixture
    def sample_durability_partial(self):
        """部分耐久度を作成"""
        return Durability(current=50, max_value=100)

    @pytest.fixture
    def sample_durability_broken(self):
        """破損耐久度を作成"""
        return Durability(current=0, max_value=100)

    def test_create_basic_item_aggregate(self, sample_item_spec_no_durability):
        """基本的なアイテム集約作成のテスト"""
        item_id = ItemInstanceId(1)

        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_no_durability,
            quantity=5
        )

        assert aggregate.item_instance_id == item_id
        assert aggregate.item_spec == sample_item_spec_no_durability
        assert aggregate.quantity == 5
        assert aggregate.durability is None
        assert not aggregate.is_broken
        assert len(aggregate.get_events()) == 0  # イベントなし

    def test_create_item_with_durability(self, sample_item_spec_with_durability, sample_durability_full):
        """耐久度付きアイテム集約作成のテスト"""
        item_id = ItemInstanceId(2)

        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_full,
            quantity=1
        )

        assert aggregate.item_instance_id == item_id
        assert aggregate.item_spec == sample_item_spec_with_durability
        assert aggregate.quantity == 1
        assert aggregate.durability == sample_durability_full
        assert not aggregate.is_broken

    def test_create_item_with_partial_durability(self, sample_item_spec_with_durability, sample_durability_partial):
        """部分耐久度付きアイテム集約作成のテスト"""
        item_id = ItemInstanceId(3)

        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_partial,
            quantity=1
        )

        assert aggregate.durability == sample_durability_partial
        assert not aggregate.is_broken

    def test_create_item_with_broken_durability(self, sample_item_spec_with_durability, sample_durability_broken):
        """破損耐久度付きアイテム集約作成のテスト"""
        item_id = ItemInstanceId(4)

        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_broken,
            quantity=1
        )

        assert aggregate.durability == sample_durability_broken
        assert aggregate.is_broken

    def test_create_by_crafting_emits_event(self, sample_item_spec_no_durability):
        """合成による作成時にItemCraftedEventを発行するテスト"""
        item_id = ItemInstanceId(5)

        aggregate = ItemAggregate.create_by_crafting(
            item_instance_id=item_id,
            item_spec=sample_item_spec_no_durability,
            quantity=3
        )

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, ItemCraftedEvent)
        assert event.aggregate_id == item_id
        assert event.aggregate_type == "ItemAggregate"
        assert event.item_instance_id == item_id
        assert event.item_spec_id == sample_item_spec_no_durability.item_spec_id
        assert event.quantity == 3

        # 耐久度なしアイテムの場合はdurabilityはNone
        assert aggregate.durability is None

    def test_create_by_crafting_with_durability_max(self, sample_item_spec_with_durability):
        """耐久度最大値を持つアイテムの合成作成テスト"""
        item_id = ItemInstanceId(6)

        aggregate = ItemAggregate.create_by_crafting(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            quantity=1
        )

        # 耐久度がアイテム仕様の最大値に設定されていることを確認
        assert aggregate.durability.current == sample_item_spec_with_durability.durability_max
        assert aggregate.durability.max_value == sample_item_spec_with_durability.durability_max

    def test_create_from_instance(self, sample_item_spec_no_durability):
        """既存のItemInstanceからの集約作成テスト"""
        item_instance = ItemInstance(
            item_instance_id=ItemInstanceId(7),
            item_spec=sample_item_spec_no_durability,
            quantity=10
        )

        aggregate = ItemAggregate.create_from_instance(item_instance)

        assert aggregate.item_instance_id == ItemInstanceId(7)
        assert aggregate.item_spec == sample_item_spec_no_durability
        assert aggregate.quantity == 10
        assert aggregate.durability is None

    def test_use_item_without_durability(self, sample_item_spec_no_durability):
        """耐久度なしアイテムの使用テスト"""
        item_id = ItemInstanceId(8)
        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_no_durability,
            quantity=5
        )

        # 使用前にイベントなし
        assert len(aggregate.get_events()) == 0

        # 使用
        aggregate.use()

        # 使用イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, ItemUsedEvent)
        assert event.aggregate_id == item_id
        assert event.aggregate_type == "ItemAggregate"
        assert event.item_instance_id == item_id
        assert event.item_spec_id == sample_item_spec_no_durability.item_spec_id
        assert event.remaining_quantity == 4  # 使用時に数量が1減少
        assert event.remaining_durability is None  # 耐久度なし

    def test_use_item_with_durability_not_broken(self, sample_item_spec_with_durability, sample_durability_partial):
        """耐久度付きアイテムの使用（破損なし）テスト"""
        item_id = ItemInstanceId(9)
        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_partial,
            quantity=1
        )

        aggregate.use()

        # 使用イベントのみ発行（破損イベントなし）
        events = aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, ItemUsedEvent)
        assert event.remaining_durability is not None
        assert event.remaining_durability.current < sample_durability_partial.current  # 耐久度減少

    def test_use_item_breaks_on_use(self, sample_item_spec_with_durability):
        """使用時にアイテムが破損するテスト"""
        item_id = ItemInstanceId(10)
        # 現在の耐久度が1のアイテム
        durability_one = Durability(current=1, max_value=100)

        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            durability=durability_one,
            quantity=1
        )

        aggregate.use()

        # 使用イベントと破損イベントの両方が発行
        events = aggregate.get_events()
        assert len(events) == 2

        # 最初のイベントは使用イベント
        used_event = events[0]
        assert isinstance(used_event, ItemUsedEvent)

        # 2番目のイベントは破損イベント
        broken_event = events[1]
        assert isinstance(broken_event, ItemBrokenEvent)
        assert broken_event.aggregate_id == item_id
        assert broken_event.aggregate_type == "ItemAggregate"
        assert broken_event.item_instance_id == item_id
        assert broken_event.item_spec_id == sample_item_spec_with_durability.item_spec_id

        # 破損状態になっていることを確認
        assert aggregate.is_broken

    def test_can_stack_with_same_spec_different_instances(self, sample_item_spec_no_durability):
        """同じ仕様の異なるインスタンスとのスタック可能テスト"""
        item1 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(11),
            item_spec=sample_item_spec_no_durability,
            quantity=5
        )
        item2 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(12),
            item_spec=sample_item_spec_no_durability,
            quantity=3
        )

        assert item1.can_stack_with(item2)
        assert item2.can_stack_with(item1)

    def test_can_stack_with_different_specs(self, sample_item_spec_no_durability, sample_item_spec_with_durability):
        """異なる仕様のアイテムとのスタック不可テスト"""
        item1 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(13),
            item_spec=sample_item_spec_no_durability,
            quantity=5
        )
        item2 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(14),
            item_spec=sample_item_spec_with_durability,
            quantity=1
        )

        assert not item1.can_stack_with(item2)
        assert not item2.can_stack_with(item1)

    def test_can_stack_with_same_spec_different_durability(self, sample_item_spec_with_durability):
        """同じ仕様でも耐久度が異なる場合はスタック不可"""
        durability1 = Durability(current=50, max_value=100)
        durability2 = Durability(current=30, max_value=100)

        item1 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(15),
            item_spec=sample_item_spec_with_durability,
            durability=durability1,
            quantity=1
        )
        item2 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(16),
            item_spec=sample_item_spec_with_durability,
            durability=durability2,
            quantity=1
        )

        # 耐久度が異なる場合はスタック不可
        assert not item1.can_stack_with(item2)

    def test_add_quantity(self, sample_item_spec_no_durability):
        """数量追加のテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(17),
            item_spec=sample_item_spec_no_durability,
            quantity=5
        )

        aggregate.add_quantity(3)

        assert aggregate.quantity == 8

    def test_remove_quantity(self, sample_item_spec_no_durability):
        """数量減算のテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(18),
            item_spec=sample_item_spec_no_durability,
            quantity=10
        )

        aggregate.remove_quantity(4)

        assert aggregate.quantity == 6

    def test_set_quantity(self, sample_item_spec_no_durability):
        """数量設定のテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(19),
            item_spec=sample_item_spec_no_durability,
            quantity=5
        )

        aggregate.set_quantity(15)

        assert aggregate.quantity == 15

    def test_repair_durability_emits_event(self, sample_item_spec_with_durability, sample_durability_partial):
        """耐久度回復時にイベントを発行するテスト"""
        item_id = ItemInstanceId(20)
        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_partial,
            quantity=1
        )

        # 修復前にイベントなし
        assert len(aggregate.get_events()) == 0

        aggregate.repair_durability(10)

        # 修復イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, ItemRepairedEvent)
        assert event.aggregate_id == item_id
        assert event.aggregate_type == "ItemAggregate"
        assert event.item_instance_id == item_id
        assert event.item_spec_id == sample_item_spec_with_durability.item_spec_id
        assert event.new_durability is not None
        assert event.new_durability.current == sample_durability_partial.current + 10

    def test_repair_durability_without_durability_no_effect(self, sample_item_spec_no_durability):
        """耐久度なしアイテムの修復は何も起こらないテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(21),
            item_spec=sample_item_spec_no_durability,
            quantity=1
        )

        # 修復前にイベントなし
        assert len(aggregate.get_events()) == 0

        # 耐久度なしアイテムの修復は何も起こらない
        aggregate.repair_durability(5)

        # イベントも発生しない
        assert len(aggregate.get_events()) == 0

    def test_repair_durability_over_max_clamps_to_max(self, sample_item_spec_with_durability):
        """最大値を超える修復は最大値にクランプされるテスト"""
        durability_low = Durability(current=95, max_value=100)
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(22),
            item_spec=sample_item_spec_with_durability,
            durability=durability_low,
            quantity=1
        )

        # 10回復しようとするが、最大値は100なので95+10=105→100にクランプ
        aggregate.repair_durability(10)

        assert aggregate.durability.current == 100

    def test_quantity_operations_with_invalid_values(self, sample_item_spec_no_durability):
        """無効な数量操作のテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(23),
            item_spec=sample_item_spec_no_durability,
            quantity=5
        )

        # 負の数量追加
        with pytest.raises(QuantityValidationException):
            aggregate.add_quantity(-1)

        # 現在の数量を超える減算
        with pytest.raises(InsufficientQuantityException):
            aggregate.remove_quantity(10)

        # 負の数量設定
        with pytest.raises(QuantityValidationException):
            aggregate.set_quantity(-1)

    def test_properties_access(self, sample_item_spec_with_durability, sample_durability_full):
        """プロパティアクセスのテスト"""
        item_id = ItemInstanceId(24)
        aggregate = ItemAggregate.create(
            item_instance_id=item_id,
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_full,
            quantity=7
        )

        assert aggregate.item_instance_id == item_id
        assert aggregate.item_spec == sample_item_spec_with_durability
        assert aggregate.durability == sample_durability_full
        assert aggregate.quantity == 7
        assert not aggregate.is_broken

    def test_is_broken_with_none_durability(self, sample_item_spec_no_durability):
        """耐久度なしアイテムは破損しないテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(25),
            item_spec=sample_item_spec_no_durability,
            quantity=1
        )

        assert not aggregate.is_broken

    def test_is_broken_with_full_durability(self, sample_item_spec_with_durability, sample_durability_full):
        """満タン耐久度は破損していないテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(26),
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_full,
            quantity=1
        )

        assert not aggregate.is_broken

    def test_is_broken_with_zero_durability(self, sample_item_spec_with_durability, sample_durability_broken):
        """ゼロ耐久度は破損しているテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(27),
            item_spec=sample_item_spec_with_durability,
            durability=sample_durability_broken,
            quantity=1
        )

        assert aggregate.is_broken

    def test_events_persist_after_getting(self, sample_item_spec_no_durability):
        """イベント取得後もイベントが保持されるテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(28),
            item_spec=sample_item_spec_no_durability,
            quantity=1
        )

        # イベントを発生させる
        aggregate.use()

        # イベントがあることを確認
        assert len(aggregate.get_events()) == 1

        # 2回目に取得してもイベントが保持されている
        assert len(aggregate.get_events()) == 1

    def test_multiple_uses_accumulate_events(self, sample_item_spec_no_durability):
        """複数回の使用でイベントが蓄積されるテスト"""
        aggregate = ItemAggregate.create(
            item_instance_id=ItemInstanceId(29),
            item_spec=sample_item_spec_no_durability,
            quantity=1
        )

        # 複数回使用
        aggregate.use()
        aggregate.use()

        # イベントが蓄積されていることを確認
        events = aggregate.get_events()
        assert len(events) == 2
        assert all(isinstance(event, ItemUsedEvent) for event in events)
