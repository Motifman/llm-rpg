"""ツール利用可否リゾルバのデフォルト実装"""

from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


def _has_visible_action(obj, flag_name: str, legacy_name: str) -> bool:
    if getattr(obj, flag_name, False):
        return True
    return legacy_name in getattr(obj, "available_interactions", [])


def _iter_actionable_objects(context: PlayerCurrentStateDto):
    objs = context.actionable_objects or context.visible_objects
    return objs if objs is not None else []


class NoOpAvailabilityResolver(IAvailabilityResolver):
    """何もしないツールは常に利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return True


class SetDestinationAvailabilityResolver(IAvailabilityResolver):
    """目的地設定ツールは、現在地があり利用可能な移動先（スポット・ロケーション）が1件以上あるときに利用可能。"""

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
        has_spot_moves = (
            context.available_moves is not None
            and context.total_available_moves is not None
            and context.total_available_moves > 0
        )
        has_location_moves = (
            context.available_location_areas is not None
            and len(context.available_location_areas) > 0
        )
        has_object_moves = (
            context.actionable_objects is not None
            and len(context.actionable_objects) > 0
        )
        return has_spot_moves or has_location_moves or has_object_moves


class PursuitStartAvailabilityResolver(IAvailabilityResolver):
    """追跡開始ツールは可視中のプレイヤーまたはモンスターがいて、かつ actor が busy でないときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None or context.is_busy:
            return False
        visible = context.visible_objects if context.visible_objects is not None else []
        return any(
            obj.object_kind in {"player", "monster"} and not obj.is_self
            for obj in visible
        )


class PursuitCancelAvailabilityResolver(IAvailabilityResolver):
    """追跡中断ツールは現在状態が取得できていれば利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None


class CancelMovementAvailabilityResolver(IAvailabilityResolver):
    """移動キャンセルツールは、経路設定中（has_active_path）のときのみ利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and context.has_active_path


class WhisperAvailabilityResolver(IAvailabilityResolver):
    """囁きツールは、視界内に自分以外のプレイヤーがいるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        visible = context.visible_objects if context.visible_objects is not None else []
        return any(
            obj.object_kind == "player" and not obj.is_self
            for obj in visible
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
            for obj in _iter_actionable_objects(context)
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
            for obj in _iter_actionable_objects(context)
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
        items = context.inventory_items if context.inventory_items is not None else []
        return any(item.is_placeable for item in items)


class InspectItemAvailabilityResolver(IAvailabilityResolver):
    """アイテム調査ツールは在庫アイテムが1件以上あるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return bool(context.inventory_items)


class InspectTargetAvailabilityResolver(IAvailabilityResolver):
    """対象調査ツールは視界内に interact/harvest 可能な対象があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return any(
            _has_visible_action(obj, "can_interact", "interact")
            or _has_visible_action(obj, "can_harvest", "harvest")
            for obj in _iter_actionable_objects(context)
            if not obj.is_self
        )


class DestroyPlaceableAvailabilityResolver(IAvailabilityResolver):
    """破壊ツールは前方に設置物があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and context.can_destroy_placeable


class DropItemAvailabilityResolver(IAvailabilityResolver):
    """意図的ドロップツールは在庫アイテムがあるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and bool(context.inventory_items)


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
            for obj in _iter_actionable_objects(context)
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


class QuestAcceptAvailabilityResolver(IAvailabilityResolver):
    """クエスト受託はコンテキスト取得時に利用可能（受託可能なクエストは別途表示）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None


class QuestCancelAvailabilityResolver(IAvailabilityResolver):
    """クエストキャンセルは受託中クエストがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.active_quests)


class QuestApproveAvailabilityResolver(IAvailabilityResolver):
    """クエスト承認はギルド所属があるときに利用可能（オフィサー以上）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.guild_memberships)


class GuildLeaveAvailabilityResolver(IAvailabilityResolver):
    """ギルド脱退は所属ギルドがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.guild_memberships)


class GuildDepositBankAvailabilityResolver(IAvailabilityResolver):
    """ギルド金庫入金は所属ギルドがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.guild_memberships)


class GuildWithdrawBankAvailabilityResolver(IAvailabilityResolver):
    """ギルド金庫出金は所属ギルドがあるときに利用可能（オフィサー以上）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.guild_memberships)


class ShopPurchaseAvailabilityResolver(IAvailabilityResolver):
    """ショップ購入は近隣ショップがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.nearby_shops)


class ShopListItemAvailabilityResolver(IAvailabilityResolver):
    """ショップ出品は近隣ショップがあるときに利用可能（オーナー時）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.nearby_shops)


class ShopUnlistItemAvailabilityResolver(IAvailabilityResolver):
    """ショップ取り下げは近隣ショップがあるときに利用可能（オーナー時）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.nearby_shops)


class TradeOfferAvailabilityResolver(IAvailabilityResolver):
    """取引出品はインベントリがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.inventory_items)


class TradeAcceptAvailabilityResolver(IAvailabilityResolver):
    """取引受諾は宛先取引があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.available_trades)


class TradeCancelAvailabilityResolver(IAvailabilityResolver):
    """取引キャンセルは宛先取引または自分発信取引があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.available_trades)


class MemoryQueryAvailabilityResolver(IAvailabilityResolver):
    """memory_query は現在状態が取得できているときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None


class SubagentAvailabilityResolver(IAvailabilityResolver):
    """subagent は現在状態が取得できているときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None


class TodoAddAvailabilityResolver(IAvailabilityResolver):
    """TODO 追加は常に利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return True


class TodoListAvailabilityResolver(IAvailabilityResolver):
    """TODO 一覧は常に利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return True


class TodoCompleteAvailabilityResolver(IAvailabilityResolver):
    """TODO 完了は常に利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return True


class WorkingMemoryAppendAvailabilityResolver(IAvailabilityResolver):
    """作業メモ追加は常に利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return True
