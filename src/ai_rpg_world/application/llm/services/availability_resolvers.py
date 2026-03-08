"""ツール利用可否リゾルバのデフォルト実装"""

from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


def _has_visible_action(obj, flag_name: str, legacy_name: str) -> bool:
    if getattr(obj, flag_name, False):
        return True
    return legacy_name in getattr(obj, "available_interactions", [])


def _iter_actionable_objects(context: PlayerCurrentStateDto):
    return context.actionable_objects or context.visible_objects


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
