"""ツール利用可否リゾルバのデフォルト実装"""

from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


def _has_visible_action(obj, flag_name: str, legacy_name: str) -> bool:
    if getattr(obj, flag_name, False):
        return True
    return legacy_name in getattr(obj, "available_interactions", [])


class NoOpAvailabilityResolver(IAvailabilityResolver):
    """何もしないツールは常に利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return True


class SetDestinationAvailabilityResolver(IAvailabilityResolver):
    """目的地設定ツールは、現在地があり利用可能な移動先が1件以上あるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        if context.is_busy or context.has_active_path:
            return False
        if context.current_spot_id is None:
            return False
        if context.available_moves is None or context.total_available_moves is None:
            return False
        return context.total_available_moves > 0


class WhisperAvailabilityResolver(IAvailabilityResolver):
    """囁きツールは、視界内に自分以外のプレイヤーがいるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return any(
            obj.object_kind == "player" and not obj.is_self
            for obj in context.visible_objects
        )


class SayAvailabilityResolver(IAvailabilityResolver):
    """発言ツールは、現在状態が取得できているときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None


class InteractAvailabilityResolver(IAvailabilityResolver):
    """追加引数不要の相互作用があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return any(
            _has_visible_action(obj, "can_interact", "interact")
            for obj in context.visible_objects
            if not obj.is_self
        )


class HarvestStartAvailabilityResolver(IAvailabilityResolver):
    """採集開始ツールは、視界内に採集可能な資源があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return any(
            _has_visible_action(obj, "can_harvest", "harvest")
            for obj in context.visible_objects
            if not obj.is_self
        )


class ChangeAttentionAvailabilityResolver(IAvailabilityResolver):
    """注意レベル変更ツールは、切り替え候補があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and bool(context.attention_level_options)


class ConversationAdvanceAvailabilityResolver(IAvailabilityResolver):
    """会話進行ツールはアクティブな会話があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and context.active_conversation is not None


class PlaceObjectAvailabilityResolver(IAvailabilityResolver):
    """設置ツールは設置可能な在庫アイテムがあるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return any(item.is_placeable for item in context.inventory_items)


class DestroyPlaceableAvailabilityResolver(IAvailabilityResolver):
    """破壊ツールは前方に設置物があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and context.can_destroy_placeable


class ChestStoreAvailabilityResolver(IAvailabilityResolver):
    """チェスト収納は開いているチェストと在庫アイテムがあるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        has_open_chest = any(
            _has_visible_action(obj, "can_store_in_chest", "store_in_chest")
            for obj in context.visible_objects
            if not obj.is_self
        )
        return has_open_chest and bool(context.inventory_items)


class ChestTakeAvailabilityResolver(IAvailabilityResolver):
    """チェスト取得は取り出せるチェスト中身があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and bool(context.chest_items)


class CombatUseSkillAvailabilityResolver(IAvailabilityResolver):
    """戦闘スキルは使用可能スキルがあるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and bool(context.usable_skills)
