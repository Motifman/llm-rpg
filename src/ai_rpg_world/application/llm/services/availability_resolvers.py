"""ツール利用可否リゾルバのデフォルト実装"""

from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.world.contracts.dtos import (
    PlayerAppSessionStateDto,
    PlayerCurrentStateDto,
    PlayerRuntimeContextDto,
    PlayerWorldStateDto,
)


def _world(context: PlayerCurrentStateDto) -> PlayerWorldStateDto:
    return context.world_state


def _runtime(context: PlayerCurrentStateDto) -> PlayerRuntimeContextDto:
    return context.runtime_context


def _app(context: PlayerCurrentStateDto) -> PlayerAppSessionStateDto:
    return context.app_session_state


class NoOpAvailabilityResolver(IAvailabilityResolver):
    """何もしないツールは常に利用可能。"""

    def is_available(
        self,
        context: PlayerCurrentStateDto | None,
    ) -> bool:
        return True


class EpisodeRecallAvailabilityResolver(IAvailabilityResolver):
    """目次つきのエピソードの呼び出しと目次の直し (#1623)。目次が空でも呼べて、記憶が無いと返る。"""

    def is_available(
        self,
        context: PlayerCurrentStateDto | None,
    ) -> bool:
        return True


class SayAvailabilityResolver(IAvailabilityResolver):
    """発言ツールは、現在状態が取得できているときに利用可能。"""

    def is_available(
        self,
        context: PlayerCurrentStateDto | None,
    ) -> bool:
        return context is not None


class QuestAcceptAvailabilityResolver(IAvailabilityResolver):
    """クエスト受託はコンテキスト取得時に利用可能（受託可能なクエストは別途表示）。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None


class QuestCancelAvailabilityResolver(IAvailabilityResolver):
    """クエストキャンセルは受託中クエストがあるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).active_quests)


class QuestApproveAvailabilityResolver(IAvailabilityResolver):
    """クエスト承認はギルド所属があるときに利用可能（オフィサー以上）。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class QuestIssueAvailabilityResolver(IAvailabilityResolver):
    """クエスト発行はコンテキスト取得時に利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None


class GuildCreateAvailabilityResolver(IAvailabilityResolver):
    """ギルド作成はギルド未所属かつ current_spot_id と area_ids が存在するときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
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

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        memberships = _runtime(context).guild_memberships
        if not memberships:
            return False
        return any(m.role in ("leader", "officer") for m in memberships)


class GuildChangeRoleAvailabilityResolver(IAvailabilityResolver):
    """ギルド役職変更は guild_memberships があり、いずれかが leader または officer のときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        memberships = _runtime(context).guild_memberships
        if not memberships:
            return False
        return any(m.role in ("leader", "officer") for m in memberships)


class GuildDisbandAvailabilityResolver(IAvailabilityResolver):
    """ギルド解散は guild_memberships のいずれかが leader のときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        memberships = _runtime(context).guild_memberships
        if not memberships:
            return False
        return any(m.role == "leader" for m in memberships)


class GuildLeaveAvailabilityResolver(IAvailabilityResolver):
    """ギルド脱退は所属ギルドがあるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class GuildDepositBankAvailabilityResolver(IAvailabilityResolver):
    """ギルド金庫入金は所属ギルドがあるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class GuildWithdrawBankAvailabilityResolver(IAvailabilityResolver):
    """ギルド金庫出金は所属ギルドがあるときに利用可能（オフィサー以上）。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).guild_memberships)


class ShopPurchaseAvailabilityResolver(IAvailabilityResolver):
    """ショップ購入は近隣ショップがあるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).nearby_shops)


class ShopListItemAvailabilityResolver(IAvailabilityResolver):
    """ショップ出品は近隣ショップがあるときに利用可能（オーナー時）。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).nearby_shops)


class ShopUnlistItemAvailabilityResolver(IAvailabilityResolver):
    """ショップ取り下げは近隣ショップがあるときに利用可能（オーナー時）。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).nearby_shops)


class TradeOfferAvailabilityResolver(IAvailabilityResolver):
    """取引出品はインベントリがあるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).inventory_items)


class TradeAcceptAvailabilityResolver(IAvailabilityResolver):
    """取引受諾は宛先取引があるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).available_trades)


class TradeCancelAvailabilityResolver(IAvailabilityResolver):
    """取引キャンセルは宛先取引または自分発信取引があるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).available_trades)


class TradeDeclineAvailabilityResolver(IAvailabilityResolver):
    """取引拒否は自分宛ての直接取引があるときに利用可能。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and bool(_runtime(context).available_trades)


class SnsToolAvailabilityResolver(IAvailabilityResolver):
    """
    SNS 操作系ツール共通の利用可否リゾルバ。
    SNS モード ON のときのみ利用可能（通常プレイ中は sns_enter のみ別 resolver）。
    """

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and _app(context).is_sns_mode_active


class SnsPageKindAvailabilityResolver(IAvailabilityResolver):
    """
    仮想 SNS 画面の種別が allowed に含まれるときのみ利用可能。
    仮想ページが未配線 (sns_virtual_page_kind is None) のときは True（従来の一覧挙動を維持）。
    """

    def __init__(self, allowed_page_kinds: frozenset[str]) -> None:
        self._allowed = allowed_page_kinds

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
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

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
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

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_sns_mode_active:
            return False
        return app.sns_virtual_page_kind is not None


class SnsVirtualPageHomeTabAvailabilityResolver(IAvailabilityResolver):
    """home 画面でのみタブ切替を許可。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_sns_mode_active:
            return False
        return app.sns_virtual_page_kind == "home"


class SnsVirtualPagePagingAvailabilityResolver(IAvailabilityResolver):
    """一覧ページングが意味を持つ画面のみ次ページを許可。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
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

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        return not app.is_sns_mode_active and not app.is_trade_mode_active


class SnsModeRequiredAvailabilityResolver(IAvailabilityResolver):
    """内側のリゾルバを、SNS モード ON のときだけ評価する。"""

    def __init__(self, inner: IAvailabilityResolver) -> None:
        self._inner = inner

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None or not _app(context).is_sns_mode_active:
            return False
        return self._inner.is_available(context)


class TradeModeRequiredAvailabilityResolver(IAvailabilityResolver):
    """内側のリゾルバを、取引所モード ON のときだけ評価する。"""

    def __init__(self, inner: IAvailabilityResolver) -> None:
        self._inner = inner

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None or not _app(context).is_trade_mode_active:
            return False
        return self._inner.is_available(context)


class TradeEnterToolAvailabilityResolver(IAvailabilityResolver):
    """取引所に入るツール。SNS も取引所も未起動のときのみ一覧に出す。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        return not app.is_sns_mode_active and not app.is_trade_mode_active


class TradeExitToolAvailabilityResolver(IAvailabilityResolver):
    """取引所を閉じるツール。取引所モード ON のときのみ一覧に出す。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        return context is not None and _app(context).is_trade_mode_active


class TradeVirtualPageNavigationAvailabilityResolver(IAvailabilityResolver):
    """仮想取引所画面が配線され一覧に載るとき（page kind が載っている）にナビ系ツールを出す。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_trade_mode_active:
            return False
        return app.trade_virtual_page_kind is not None


class TradeVirtualPagePagingAvailabilityResolver(IAvailabilityResolver):
    """一覧ページングが意味を持つ画面のみ次ページを許可。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
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

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        if not app.is_trade_mode_active:
            return False
        return app.trade_virtual_page_kind == "my_trades"


class TradeAcceptTradePageAvailabilityResolver(IAvailabilityResolver):
    """受諾は my_trades / incoming のときのみ。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        k = app.trade_virtual_page_kind
        return k == "my_trades" and app.trade_my_trades_tab == "incoming"


class TradeDeclineTradePageAvailabilityResolver(IAvailabilityResolver):
    """拒否は my_trades / incoming のときのみ。"""

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
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

    def is_available(self, context: PlayerCurrentStateDto | None) -> bool:
        if context is None:
            return False
        app = _app(context)
        k = app.trade_virtual_page_kind
        if k == "my_trades" and app.trade_my_trades_tab == "selling":
            return True
        return False
