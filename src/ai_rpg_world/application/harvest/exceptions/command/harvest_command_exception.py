"""
採集コマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.harvest.exceptions.base_exception import HarvestApplicationException


class HarvestCommandException(HarvestApplicationException):
    """採集コマンド関連の例外"""

    def __init__(
        self, 
        message: str, 
        error_code: str = None, 
        actor_id: Optional[str] = None, 
        target_id: Optional[str] = None, 
        spot_id: Optional[str] = None, 
        **context
    ):
        all_context = context.copy()
        if actor_id is not None:
            all_context['actor_id'] = actor_id
        if target_id is not None:
            all_context['target_id'] = target_id
        if spot_id is not None:
            all_context['spot_id'] = spot_id
        super().__init__(message, error_code, **all_context)


class HarvestResourceNotFoundException(HarvestCommandException):
    """採集対象の資源が見つからない場合の例外"""

    def __init__(self, target_id: str, spot_id: str):
        message = f"スポット {spot_id} 内に採集対象の資源が見つかりません: {target_id}"
        super().__init__(message, "HARVEST_RESOURCE_NOT_FOUND", target_id=target_id, spot_id=spot_id)


class HarvestActorNotFoundException(HarvestCommandException):
    """アクターが見つからない場合の例外"""

    def __init__(self, actor_id: str):
        message = f"アクターが見つかりません: {actor_id}"
        super().__init__(message, "HARVEST_ACTOR_NOT_FOUND", actor_id=actor_id)
