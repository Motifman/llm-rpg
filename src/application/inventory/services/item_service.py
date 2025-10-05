from typing import List, TYPE_CHECKING
from src.domain.item.value_object.merge_plan import MergePlan, UpdateOperation, CreateOperation, DeleteOperation
from src.domain.item.aggregate.item_aggregate import ItemAggregate
from src.domain.item.value_object.item_instance_id import ItemInstanceId

if TYPE_CHECKING:
    from src.domain.item.repository.item_instance_repository import ItemInstanceRepository


class ItemStackingApplicationService:
    """アイテムスタッキングアプリケーションサービス"""

    def __init__(self, item_instance_repository: "ItemInstanceRepository"):
        self._item_instance_repository = item_instance_repository

    def execute_merge_plan(self, merge_plan: MergePlan) -> List[ItemAggregate]:
        """マージ計画を実行する

        Args:
            merge_plan: 実行するマージ計画

        Returns:
            List[ItemAggregate]: マージ実行後のアイテムリスト
        """
        updated_items = []

        # 1. 更新操作を実行
        for update_op in merge_plan.update_operations:
            item_instance = self._item_instance_repository.find_by_id(update_op.item_instance_id)
            if item_instance is None:
                continue  # アイテムが存在しない場合はスキップ

            # 数量を設定
            item_instance.set_quantity(update_op.new_quantity)

            # 保存
            saved_instance = self._item_instance_repository.save(item_instance)
            updated_items.append(ItemAggregate.create_from_instance(saved_instance))

        # 2. 削除操作を実行
        for delete_op in merge_plan.delete_operations:
            self._item_instance_repository.delete(delete_op.item_instance_id)

        # 3. 作成操作を実行
        for create_op in merge_plan.create_operations:
            # 新しいIDを生成
            new_instance_id = self._item_instance_repository.generate_item_instance_id()

            # 新しいアイテムを作成
            new_item = ItemAggregate.create(
                item_instance_id=new_instance_id,
                item_spec=create_op.item_spec,
                durability=create_op.durability,
                quantity=create_op.quantity
            )

            # 保存
            saved_instance = self._item_instance_repository.save(new_item.item_instance)
            updated_items.append(ItemAggregate.create_from_instance(saved_instance))

        return updated_items
