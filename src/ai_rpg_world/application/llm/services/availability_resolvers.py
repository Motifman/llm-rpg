"""ツール利用可否リゾルバのデフォルト実装"""

from typing import FrozenSet, Optional

from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


def _has_visible_action(obj, flag_name: str, legacy_name: str) -> bool:
    if getattr(obj, flag_name, False):
        return True
    return legacy_name in getattr(obj, "available_interactions", [])


def _iter_actionable_objects(context: PlayerCurrentStateDto):
    runtime = context.runtime_context
    world = context.world_state
    objs = runtime.actionable_objects or world.visible_objects
    return objs if objs is not None else []


def _world(context: PlayerCurrentStateDto):
    return context.world_state


def _runtime(context: PlayerCurrentStateDto):
    return context.runtime_context


def _app(context: PlayerCurrentStateDto):
    return context.app_session_state


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
        world = _world(context)
        runtime = _runtime(context)
        if world.is_busy or world.has_active_path:
            return False
        if world.current_spot_id is None:
            return False
        has_spot_moves = (
            world.available_moves is not None
            and world.total_available_moves is not None
            and world.total_available_moves > 0
        )
        has_location_moves = (
            world.available_location_areas is not None
            and len(world.available_location_areas) > 0
        )
        has_object_moves = (
            runtime.actionable_objects is not None
            and len(runtime.actionable_objects) > 0
        )
        return has_spot_moves or has_location_moves or has_object_moves


class PursuitStartAvailabilityResolver(IAvailabilityResolver):
    """追跡開始ツールは可視中のプレイヤーまたはモンスターがいて、かつ actor が busy でないときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        world = _world(context)
        if world.is_busy:
            return False
        visible = world.visible_objects or []
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
        return context is not None and _world(context).has_active_path


class MoveOneStepAvailabilityResolver(IAvailabilityResolver):
    """1歩移動ツールは、マップ上にいて行動可能なときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        world = _world(context)
        if world.is_busy:
            return False
        return world.current_spot_id is not None


class WhisperAvailabilityResolver(IAvailabilityResolver):
    """囁きツールは、視界内に自分以外のプレイヤーがいるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        visible = _world(context).visible_objects or []
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
        world = _world(context)
        runtime = _runtime(context)
        if world.is_busy or runtime.active_harvest is not None:
            return False
        return any(
            _has_visible_action(obj, "can_harvest", "harvest")
            for obj in _iter_actionable_objects(context)
            if not obj.is_self
        )


class HarvestCancelAvailabilityResolver(IAvailabilityResolver):
    """採集中断ツールは進行中採集があるときのみ利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and _runtime(context).active_harvest is not None


class ChangeAttentionAvailabilityResolver(IAvailabilityResolver):
    """注意レベル変更ツールは、切り替え候補があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and bool(_runtime(context).attention_level_options)


class ConversationAdvanceAvailabilityResolver(IAvailabilityResolver):
    """会話進行ツールはアクティブな会話があるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and _runtime(context).active_conversation is not None


class PlaceObjectAvailabilityResolver(IAvailabilityResolver):
    """設置ツールは設置可能な在庫アイテムがあるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        items = _runtime(context).inventory_items
        return any(item.is_placeable for item in items)


class InspectItemAvailabilityResolver(IAvailabilityResolver):
    """アイテム調査ツールは在庫アイテムが1件以上あるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return bool(_runtime(context).inventory_items)


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
        return context is not None and _runtime(context).can_destroy_placeable


class DropItemAvailabilityResolver(IAvailabilityResolver):
    """意図的ドロップツールは在庫アイテムがあるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and bool(_runtime(context).inventory_items)


class ChestStoreAvailabilityResolver(IAvailabilityResolver):
    """チェスト収納は開いているチェストと在庫アイテムがあり、かつ actor がビジーでないときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        world = _world(context)
        runtime = _runtime(context)
        if world.is_busy:
            return False
        has_open_chest = any(
            _has_visible_action(obj, "can_store_in_chest", "store_in_chest")
            for obj in _iter_actionable_objects(context)
            if not obj.is_self
        )
        return has_open_chest and bool(runtime.inventory_items)


class ChestTakeAvailabilityResolver(IAvailabilityResolver):
    """チェスト取得は取り出せるチェスト中身があり、かつ actor がビジーでないときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        world = _world(context)
        runtime = _runtime(context)
        if world.is_busy:
            return False
        return bool(runtime.chest_items)


class CombatUseSkillAvailabilityResolver(IAvailabilityResolver):
    """戦闘スキルは使用可能スキルがあるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return context is not None and bool(_runtime(context).usable_skills)


class SkillEquipAvailabilityResolver(IAvailabilityResolver):
    """スキル装備は候補スキルと装備先スロットの両方があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        runtime = _runtime(context)
        return bool(runtime.equipable_skill_candidates) and bool(runtime.skill_equip_slots)


class SkillAcceptProposalAvailabilityResolver(IAvailabilityResolver):
    """スキル提案受諾は pending proposal があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).pending_skill_proposals)


class SkillRejectProposalAvailabilityResolver(IAvailabilityResolver):
    """スキル提案却下は pending proposal があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).pending_skill_proposals)


class SkillActivateAwakenedModeAvailabilityResolver(IAvailabilityResolver):
    """覚醒モード発動は action label があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and _runtime(context).awakened_action is not None


class QuestAcceptAvailabilityResolver(IAvailabilityResolver):
    """クエスト受託はコンテキスト取得時に利用可能（受託可能なクエストは別途表示）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None


class QuestCancelAvailabilityResolver(IAvailabilityResolver):
    """クエストキャンセルは受託中クエストがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).active_quests)


class QuestApproveAvailabilityResolver(IAvailabilityResolver):
    """クエスト承認はギルド所属があるときに利用可能（オフィサー以上）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class QuestIssueAvailabilityResolver(IAvailabilityResolver):
    """クエスト発行はコンテキスト取得時に利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None


class GuildCreateAvailabilityResolver(IAvailabilityResolver):
    """ギルド作成はギルド未所属かつ current_spot_id と area_ids が存在するときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        world = _world(context)
        runtime = _runtime(context)
        if world.current_spot_id is None:
            return False
        if not world.area_ids:
            return False
        return not bool(runtime.guild_memberships)


class GuildAddMemberAvailabilityResolver(IAvailabilityResolver):
    """ギルド招待は guild_memberships があり、いずれかが leader または officer のときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        memberships = _runtime(context).guild_memberships
        if not memberships:
            return False
        return any(
            m.role in ("leader", "officer") for m in memberships
        )


class GuildChangeRoleAvailabilityResolver(IAvailabilityResolver):
    """ギルド役職変更は guild_memberships があり、いずれかが leader または officer のときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        memberships = _runtime(context).guild_memberships
        if not memberships:
            return False
        return any(
            m.role in ("leader", "officer") for m in memberships
        )


class GuildDisbandAvailabilityResolver(IAvailabilityResolver):
    """ギルド解散は guild_memberships のいずれかが leader のときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        memberships = _runtime(context).guild_memberships
        if not memberships:
            return False
        return any(m.role == "leader" for m in memberships)


class GuildLeaveAvailabilityResolver(IAvailabilityResolver):
    """ギルド脱退は所属ギルドがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class GuildDepositBankAvailabilityResolver(IAvailabilityResolver):
    """ギルド金庫入金は所属ギルドがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class GuildWithdrawBankAvailabilityResolver(IAvailabilityResolver):
    """ギルド金庫出金は所属ギルドがあるときに利用可能（オフィサー以上）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class ShopPurchaseAvailabilityResolver(IAvailabilityResolver):
    """ショップ購入は近隣ショップがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).nearby_shops)


class ShopListItemAvailabilityResolver(IAvailabilityResolver):
    """ショップ出品は近隣ショップがあるときに利用可能（オーナー時）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).nearby_shops)


class ShopUnlistItemAvailabilityResolver(IAvailabilityResolver):
    """ショップ取り下げは近隣ショップがあるときに利用可能（オーナー時）。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).nearby_shops)


class TradeOfferAvailabilityResolver(IAvailabilityResolver):
    """取引出品はインベントリがあるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).inventory_items)


class TradeAcceptAvailabilityResolver(IAvailabilityResolver):
    """取引受諾は宛先取引があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).available_trades)


class TradeCancelAvailabilityResolver(IAvailabilityResolver):
    """取引キャンセルは宛先取引または自分発信取引があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).available_trades)


class TradeDeclineAvailabilityResolver(IAvailabilityResolver):
    """取引拒否は自分宛ての直接取引があるときに利用可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(_runtime(context).available_trades)


class SnsToolAvailabilityResolver(IAvailabilityResolver):
    """
    SNS 操作系ツール共通の利用可否リゾルバ。
    SNS モード ON のときのみ利用可能（通常プレイ中は sns_enter のみ別 resolver）。
    """

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and _app(context).is_sns_mode_active


class SnsPageKindAvailabilityResolver(IAvailabilityResolver):
    """
    仮想 SNS 画面の種別が allowed に含まれるときのみ利用可能。
    仮想ページが未配線 (sns_virtual_page_kind is None) のときは True（従来の一覧挙動を維持）。
    """

    def __init__(self, allowed_page_kinds: FrozenSet[str]) -> None:
        self._allowed = allowed_page_kinds

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_sns_mode_active:
            return False
        k = app.sns_virtual_page_kind
        if k is None:
            return True
        return k in self._allowed


class SnsProfileUpdateAvailabilityResolver(IAvailabilityResolver):
    """profile 画面で自分自身を見ているときのみプロフィール更新を許可。未配線時は従来どおり許可。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_sns_mode_active:
            return False
        k = app.sns_virtual_page_kind
        if k is None:
            return True
        if k != "profile":
            return False
        return bool(app.sns_profile_is_self)


class SnsVirtualPageNavigationAvailabilityResolver(IAvailabilityResolver):
    """仮想ページが配線され SNS モード中のとき（画面種別が載っている）にナビ系ツールを出す。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_sns_mode_active:
            return False
        return app.sns_virtual_page_kind is not None


class SnsVirtualPageHomeTabAvailabilityResolver(IAvailabilityResolver):
    """home 画面でのみタブ切替を許可。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_sns_mode_active:
            return False
        return app.sns_virtual_page_kind == "home"


class SnsVirtualPagePagingAvailabilityResolver(IAvailabilityResolver):
    """一覧ページングが意味を持つ画面のみ次ページを許可。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_sns_mode_active:
            return False
        k = app.sns_virtual_page_kind
        if k is None:
            return False
        return k in ("home", "search", "profile", "notifications")


class SnsEnterToolAvailabilityResolver(IAvailabilityResolver):
    """ゲーム内 SNS アプリを開くツール。どのアプリも未起動のときのみ一覧に出す。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        return not app.is_sns_mode_active and not app.is_trade_mode_active


class SnsModeRequiredAvailabilityResolver(IAvailabilityResolver):
    """内側のリゾルバを、SNS モード ON のときだけ評価する。"""

    def __init__(self, inner: IAvailabilityResolver) -> None:
        self._inner = inner

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None or not _app(context).is_sns_mode_active:
            return False
        return self._inner.is_available(context)


class TradeModeRequiredAvailabilityResolver(IAvailabilityResolver):
    """内側のリゾルバを、取引所モード ON のときだけ評価する。"""

    def __init__(self, inner: IAvailabilityResolver) -> None:
        self._inner = inner

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None or not _app(context).is_trade_mode_active:
            return False
        return self._inner.is_available(context)


class TradeEnterToolAvailabilityResolver(IAvailabilityResolver):
    """取引所に入るツール。SNS も取引所も未起動のときのみ一覧に出す。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        return not app.is_sns_mode_active and not app.is_trade_mode_active


class TradeExitToolAvailabilityResolver(IAvailabilityResolver):
    """取引所を閉じるツール。取引所モード ON のときのみ一覧に出す。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and _app(context).is_trade_mode_active


class TradeVirtualPageNavigationAvailabilityResolver(IAvailabilityResolver):
    """仮想取引所画面が配線され一覧に載るとき（page kind が載っている）にナビ系ツールを出す。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_trade_mode_active:
            return False
        return app.trade_virtual_page_kind is not None


class TradeVirtualPagePagingAvailabilityResolver(IAvailabilityResolver):
    """一覧ページングが意味を持つ画面のみ次ページを許可。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_trade_mode_active:
            return False
        k = app.trade_virtual_page_kind
        if k is None:
            return False
        return k in ("market", "search", "my_trades")


class TradeVirtualPageMyTradesTabAvailabilityResolver(IAvailabilityResolver):
    """my_trades 画面でのみ selling / incoming を切り替え可能。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_trade_mode_active:
            return False
        return app.trade_virtual_page_kind == "my_trades"


class TradeAcceptTradePageAvailabilityResolver(IAvailabilityResolver):
    """受諾は my_trades / incoming のときのみ。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        k = app.trade_virtual_page_kind
        return k == "my_trades" and app.trade_my_trades_tab == "incoming"


class TradeDeclineTradePageAvailabilityResolver(IAvailabilityResolver):
    """拒否は my_trades / incoming のときのみ。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        k = app.trade_virtual_page_kind
        return k == "my_trades" and app.trade_my_trades_tab == "incoming"


class TradeCancelTradePageAvailabilityResolver(IAvailabilityResolver):
    """キャンセルは my_trades / selling のときのみ。

    selling タブでは `trade_ref` / スナップショットで対象を解決するため、
    `available_trades`（自分宛 incoming の要約）の有無には依存しない。
    """

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        app = _app(context)
        k = app.trade_virtual_page_kind
        if k == "my_trades" and app.trade_my_trades_tab == "selling":
            return True
        return False


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
