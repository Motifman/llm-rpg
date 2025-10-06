from typing import List, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from src.domain.item.repository.item_spec_repository import ItemSpecRepository
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.enum.item_enum import ItemType, Rarity
from src.domain.common.exception import DomainException
from src.application.inventory.contracts.dtos import ItemSpecDto, ErrorResponseDto
from src.application.inventory.exceptions.item_info_query_application_exception import ItemInfoQueryApplicationException
from src.application.common.exceptions import SystemErrorException


class ItemInfoQueryService:
    """アイテム情報検索サービス"""

    def __init__(self, item_spec_repository: "ItemSpecRepository"):
        self._item_spec_repository = item_spec_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation, context: dict):
        """共通の例外処理を実行"""
        try:
            return operation()
        except ItemInfoQueryApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise ItemInfoQueryApplicationException.from_domain_error(e)
        except Exception as e:
            # 不明な例外はシステムエラーとしてログ出力し、SystemErrorExceptionをスロー
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra={'error_details': context})
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def get_item_spec(self, item_spec_id: int) -> ItemSpecDto:
        """アイテムスペックを取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_item_spec_impl(item_spec_id),
            context={
                "action": "get_item_spec",
                "item_spec_id": item_spec_id
            }
        )

    def _get_item_spec_impl(self, item_spec_id: int) -> ItemSpecDto:
        """アイテムスペック取得の実装"""
        item_spec = self._item_spec_repository.find_by_id(ItemSpecId(item_spec_id))
        if item_spec is None:
            raise ItemInfoQueryApplicationException.item_spec_not_found(item_spec_id)

        return ItemSpecDto(
            item_spec_id=item_spec.item_spec_id.value,
            name=item_spec.name,
            item_type=item_spec.item_type,
            rarity=item_spec.rarity,
            description=item_spec.description,
            max_stack_size=item_spec.max_stack_size.value,
            durability_max=item_spec.durability_max
        )

    def search_items_by_type(self, item_type: ItemType) -> List[ItemSpecDto]:
        """アイテムタイプで検索"""
        return self._execute_with_error_handling(
            operation=lambda: self._search_items_by_type_impl(item_type),
            context={
                "action": "search_items_by_type",
                "item_type": item_type.value
            }
        )

    def _search_items_by_type_impl(self, item_type: ItemType) -> List[ItemSpecDto]:
        """アイテムタイプ検索の実装"""
        item_specs = self._item_spec_repository.find_by_type(item_type)
        return [
            ItemSpecDto(
                item_spec_id=spec.item_spec_id.value,
                name=spec.name,
                item_type=spec.item_type,
                rarity=spec.rarity,
                description=spec.description,
                max_stack_size=spec.max_stack_size.value,
                durability_max=spec.durability_max
            )
            for spec in item_specs
        ]

    def search_items_by_rarity(self, rarity: Rarity) -> List[ItemSpecDto]:
        """レアリティで検索"""
        return self._execute_with_error_handling(
            operation=lambda: self._search_items_by_rarity_impl(rarity),
            context={
                "action": "search_items_by_rarity",
                "rarity": rarity.value
            }
        )

    def _search_items_by_rarity_impl(self, rarity: Rarity) -> List[ItemSpecDto]:
        """レアリティ検索の実装"""
        item_specs = self._item_spec_repository.find_by_rarity(rarity)
        return [
            ItemSpecDto(
                item_spec_id=spec.item_spec_id.value,
                name=spec.name,
                item_type=spec.item_type,
                rarity=spec.rarity,
                description=spec.description,
                max_stack_size=spec.max_stack_size.value,
                durability_max=spec.durability_max
            )
            for spec in item_specs
        ]

    def find_tradeable_items(self) -> List[ItemSpecDto]:
        """取引可能なアイテムを取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._find_tradeable_items_impl(),
            context={
                "action": "find_tradeable_items"
            }
        )

    def _find_tradeable_items_impl(self) -> List[ItemSpecDto]:
        """取引可能アイテム取得の実装"""
        item_specs = self._item_spec_repository.find_tradeable_items()
        return [
            ItemSpecDto(
                item_spec_id=spec.item_spec_id.value,
                name=spec.name,
                item_type=spec.item_type,
                rarity=spec.rarity,
                description=spec.description,
                max_stack_size=spec.max_stack_size.value,
                durability_max=spec.durability_max
            )
            for spec in item_specs
        ]

    def find_item_by_name(self, name: str) -> Optional[ItemSpecDto]:
        """名前で検索"""
        return self._execute_with_error_handling(
            operation=lambda: self._find_item_by_name_impl(name),
            context={
                "action": "find_item_by_name",
                "name": name
            }
        )

    def _find_item_by_name_impl(self, name: str) -> Optional[ItemSpecDto]:
        """名前検索の実装"""
        item_spec = self._item_spec_repository.find_by_name(name)
        if item_spec is None:
            return None

        return ItemSpecDto(
            item_spec_id=item_spec.item_spec_id.value,
            name=item_spec.name,
            item_type=item_spec.item_type,
            rarity=item_spec.rarity,
            description=item_spec.description,
            max_stack_size=item_spec.max_stack_size.value,
            durability_max=item_spec.durability_max
        )
