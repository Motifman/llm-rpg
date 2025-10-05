from typing import List, Tuple, Dict
from src.domain.item.aggregate.item_aggregate import ItemAggregate
from src.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from src.domain.item.value_object.merge_plan import (
    MergePlan, UpdateOperation, CreateOperation, DeleteOperation,
    CraftingConsumptionPlan, ConsumedItem
)
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.exception import InsufficientIngredientsException


class ItemStackingDomainService:
    """アイテムスタッキングドメインサービス"""


    @staticmethod
    def calculate_max_stack_quantity(
        base_item: ItemAggregate,
        additional_items: List[ItemAggregate]
    ) -> Tuple[int, List[ItemAggregate]]:
        """スタック可能なアイテムから最大スタック数量を計算

        Args:
            base_item: 基準となるアイテム
            additional_items: 追加候補のアイテムリスト

        Returns:
            Tuple[int, List[ItemAggregate]]: (スタック後の総数量, スタック可能なアイテムリスト)
        """
        total_quantity = base_item.quantity
        stackable_items = []

        # スタック可能なアイテムをフィルタリング
        for item in additional_items:
            if base_item.can_stack_with(item):
                stackable_items.append(item)
                total_quantity += item.quantity

        return total_quantity, stackable_items

    @staticmethod
    def plan_merge(items: List[ItemAggregate]) -> MergePlan:
        """アイテムマージ計画を作成

        Args:
            items: マージ対象のアイテムリスト

        Returns:
            MergePlan: マージ計画
        """
        if not items:
            return MergePlan(
                update_operations=[],
                create_operations=[],
                delete_operations=[]
            )

        update_operations = []
        create_operations = []
        delete_operations = []

        # スタック可能なアイテムのみをスペックごとにグループ化
        spec_groups = {}
        for item in items:
            # 耐久度付きアイテムはスタック不可なのでマージ対象外
            if item.item_spec.durability_max is not None:
                continue

            spec_id = item.item_spec.item_spec_id.value
            if spec_id not in spec_groups:
                spec_groups[spec_id] = []
            spec_groups[spec_id].append(item)

        for spec_items in spec_groups.values():
            if len(spec_items) == 1:
                # 単一アイテムの場合は何もしない
                continue

            # 同じスペックのアイテムをマージ
            plan = ItemStackingDomainService._plan_merge_same_spec_items(spec_items)
            update_operations.extend(plan.update_operations)
            create_operations.extend(plan.create_operations)
            delete_operations.extend(plan.delete_operations)

        return MergePlan(
            update_operations=update_operations,
            create_operations=create_operations,
            delete_operations=delete_operations
        )

    @staticmethod
    def plan_crafting_consumption(
        recipe: RecipeAggregate,
        available_items: List[ItemAggregate]
    ) -> CraftingConsumptionPlan:
        """クラフト材料消費計画を作成

        レシピの材料を消費するための計画を生成する。
        利用可能なアイテムから必要な数量を消費し、
        0個になったアイテムは削除、部分的に消費されたアイテムは更新する。

        Args:
            recipe: クラフト対象のレシピ
            available_items: 利用可能なアイテムリスト

        Returns:
            CraftingConsumptionPlan: 消費計画

        Raises:
            InsufficientIngredientsException: 材料が不足している場合
        """
        # スペックIDごとにアイテムをグループ化
        items_by_spec = {}
        for item in available_items:
            spec_id = item.item_spec.item_spec_id
            if spec_id not in items_by_spec:
                items_by_spec[spec_id] = []
            items_by_spec[spec_id].append(item)

        consumed_items = []
        update_operations = []
        delete_operations = []

        # 各材料について消費計画を作成
        for ingredient in recipe.ingredients:
            required_quantity = ingredient.quantity
            spec_id = ingredient.item_spec_id

            # このスペックのアイテムが存在するかチェック
            if spec_id not in items_by_spec:
                raise InsufficientIngredientsException(
                    recipe_id=recipe.recipe_id.value,
                    missing_ingredients={spec_id: required_quantity}
                )

            # このスペックのアイテムリストを取得
            spec_items = items_by_spec[spec_id]
            total_available = sum(item.quantity for item in spec_items)

            if total_available < required_quantity:
                missing_quantity = required_quantity - total_available
                raise InsufficientIngredientsException(
                    recipe_id=recipe.recipe_id.value,
                    missing_ingredients={spec_id: missing_quantity}
                )

            # アイテムを消費していく
            remaining_to_consume = required_quantity
            for item in spec_items:
                if remaining_to_consume <= 0:
                    break

                consume_quantity = min(remaining_to_consume, item.quantity)
                new_quantity = item.quantity - consume_quantity
                remaining_to_consume -= consume_quantity

                # 消費情報を記録
                consumed_items.append(ConsumedItem(
                    item_instance_id=item.item_instance_id,
                    consumed_quantity=consume_quantity,
                    remaining_quantity=new_quantity
                ))

                # 操作計画を作成
                if new_quantity == 0:
                    # 完全に消費された場合は削除
                    delete_operations.append(DeleteOperation(
                        item_instance_id=item.item_instance_id
                    ))
                else:
                    # 部分的に消費された場合は更新
                    update_operations.append(UpdateOperation(
                        item_instance_id=item.item_instance_id,
                        new_quantity=new_quantity
                    ))

        return CraftingConsumptionPlan(
            consumed_items=consumed_items,
            update_operations=update_operations,
            delete_operations=delete_operations
        )

    @staticmethod
    def _plan_merge_same_spec_items(items: List[ItemAggregate]) -> MergePlan:
        """同じスペックのアイテムをマージする計画を作成"""
        if not items:
            return MergePlan(
                update_operations=[],
                create_operations=[],
                delete_operations=[]
            )

        update_operations = []
        create_operations = []
        delete_operations = []

        # 最初のアイテムを基準に
        base_item = items[0]
        total_quantity = sum(item.quantity for item in items)
        max_stack = base_item.item_spec.max_stack_size.value

        # base_itemを更新（最初のスタック分）
        first_stack_quantity = min(total_quantity, max_stack)
        update_operations.append(UpdateOperation(
            item_instance_id=base_item.item_instance_id,
            new_quantity=first_stack_quantity
        ))

        # 残りのアイテムは削除
        for item in items[1:]:
            delete_operations.append(DeleteOperation(
                item_instance_id=item.item_instance_id
            ))

        # 追加で作成する必要があるアイテム
        remaining_quantity = total_quantity - first_stack_quantity
        while remaining_quantity > 0:
            quantity = min(remaining_quantity, max_stack)
            create_operations.append(CreateOperation(
                item_spec=base_item.item_spec,
                quantity=quantity,
                durability=base_item.durability
            ))
            remaining_quantity -= quantity

        return MergePlan(
            update_operations=update_operations,
            create_operations=create_operations,
            delete_operations=delete_operations
        )