"""
アイテム情報検索関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.inventory.exceptions.base_exception import ApplicationException


class ItemInfoQueryException(ApplicationException):
    """アイテム情報検索関連の例外"""

    def __init__(self, message: str, error_code: str = None, item_spec_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if item_spec_id is not None:
            all_context['item_spec_id'] = item_spec_id
        super().__init__(message, error_code, **all_context)


class ItemSpecNotFoundException(ItemInfoQueryException):
    """アイテムスペックが見つからない場合の例外"""

    def __init__(self, item_spec_id: int):
        message = f"アイテムスペックが見つかりません: {item_spec_id}"
        super().__init__(message, "ITEM_SPEC_NOT_FOUND", item_spec_id=item_spec_id)


class InvalidItemSpecIdException(ItemInfoQueryException):
    """無効なアイテムスペックIDの場合の例外"""

    def __init__(self, item_spec_id: int):
        message = f"無効なアイテムスペックIDです: {item_spec_id}"
        super().__init__(message, "INVALID_ITEM_SPEC_ID", item_spec_id=item_spec_id)


class ItemSearchException(ItemInfoQueryException):
    """アイテム検索関連の例外"""

    def __init__(self, message: str, search_criteria: str):
        self.search_criteria = search_criteria
        super().__init__(message, "ITEM_SEARCH_ERROR")
