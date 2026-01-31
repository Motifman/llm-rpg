from typing import List, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.inventory.contracts.dtos import ItemSpecDto, ErrorResponseDto
from ai_rpg_world.application.inventory.exceptions.item_info_query_application_exception import ItemInfoQueryApplicationException
from ai_rpg_world.application.common.exceptions import SystemErrorException


class ItemSpecQueryService:
    """ItemSpec検索サービス"""

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

    def _convert_to_item_spec_dto(self, read_model) -> ItemSpecDto:
        """ItemSpecReadModelをItemSpecDtoに変換"""
        return ItemSpecDto(
            item_spec_id=read_model.item_spec_id.value,
            name=read_model.name,
            item_type=read_model.item_type,
            rarity=read_model.rarity,
            description=read_model.description,
            max_stack_size=read_model.max_stack_size.value,
            durability_max=read_model.durability_max,
            equipment_type=read_model.equipment_type
        )

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

        return self._convert_to_item_spec_dto(item_spec)

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
        return [self._convert_to_item_spec_dto(spec) for spec in item_specs]

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
        return [self._convert_to_item_spec_dto(spec) for spec in item_specs]

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
        return [self._convert_to_item_spec_dto(spec) for spec in item_specs]

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

        return self._convert_to_item_spec_dto(item_spec)
