"""観測対象イベント全体を扱うデフォルト配信先解決戦略（既存ロジックを集約）"""

from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.observation.contracts.interfaces import (
    IPlayerAudienceQueryPort,
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies._dispatch import (
    Add as _Add,
)
from ai_rpg_world.application.observation.services.recipient_strategies._dispatch import (
    RecipientRuleWiringError,
    RuleTable,
    verify_rules_cover_registry,
)
from ai_rpg_world.domain.player.event.inventory_events import (
    InventorySlotOverflowEvent,
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemRemovedFromInventoryEvent,
    ItemUnequippedEvent,
)
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
    PlayerLevelUpEvent,
    PlayerLocationChangedEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultRecipientStrategy(IRecipientResolutionStrategy):
    """
    既存の観測対象イベントすべてに対する配信先解決。
    プレイヤー状態・所持品の観測先を決める。
    """

    _STRATEGY_KEY = "default"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        player_audience_query: IPlayerAudienceQueryPort,
    ) -> None:
        self._registry = observed_event_registry
        self._player_audience_query = player_audience_query
        self._verify_the_registry_and_the_rules_agree()

    def supports(self, event: Any) -> bool:
        """観測対象として定義されているイベント型なら True。"""
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    @classmethod
    def handled_event_types(cls) -> tuple[type, ...]:
        """配信規則を持つイベント型の一覧。

        ``ObservedEventRegistry`` が default に割り当てた型と一致していることを
        ``test_recipient_dispatch_is_exhaustive.py`` が強制する。
        """
        return tuple(_RECIPIENT_RULES)

    def _verify_the_registry_and_the_rules_agree(self) -> None:
        """担当と宣言されたイベント型すべてに配信規則があることを構築時に確かめる。"""
        verify_rules_cover_registry(
            registry=self._registry,
            strategy_key=self._STRATEGY_KEY,
            rules=_RECIPIENT_RULES,
        )

    def resolve(self, event: Any) -> list[PlayerId]:
        """配信先プレイヤーIDのリストを返す（重複あり。Resolver が重複除去する）。"""
        result: list[PlayerId] = []
        seen: set[int] = set()

        def add(pid: PlayerId) -> None:
            if pid.value in seen:
                return
            seen.add(pid.value)
            result.append(pid)

        # イベント型 → 配信規則の表引き。以前は 18 個の isinstance の連鎖で、
        # どれにも当たらないと空リストを返して終わっていた。登録したのに規則を
        # 書き忘れると、そのイベントは誰にも観測されないまま気づけない。
        #
        # 構築時に突き合わせているので、ここで規則が無いことは起こらない。
        # 起きたら不変条件が壊れているので落とす。
        rule = _RECIPIENT_RULES.get(type(event))
        if rule is None:
            raise RecipientRuleWiringError(
                f"{type(event).__name__} に配信規則がありません "
                "(構築時の検査を通っているはずなので、表が実行中に変わっています)"
            )
        rule(self, event, add)
        return result

    # ------------------------------------------------------------------
    # 配信規則。表 (_RECIPIENT_RULES) から引かれる。
    # ------------------------------------------------------------------

    def _deliver_only_to_the_subject(self, event: Any, add: _Add) -> None:
        """当人だけに届ける (``aggregate_id`` が本人)。

        レベルアップ・所持金の増減・インベントリの出入りは、本人の状態変化で
        あって他者から見えるものではない。
        """
        add(event.aggregate_id)

    def _deliver_to_everyone_known(self, event: Any, add: _Add) -> None:
        """本人と、既知の全プレイヤーに届ける。

        ダウンと復帰は物語上の重大な状態変化なので、位置に関わらず共有する。
        詳細な目撃か「遠くの気配」かは formatter が recipient との位置関係から
        分ける。ダウンだけ共有して復帰を共有しないと、倒れたままだと思い込んだ
        まま話が進むので対称にしてある。
        """
        add(event.aggregate_id)
        for player_id in self._player_audience_query.all_known_players():
            add(player_id)

    def _resolve_player_location_changed(
        self, event: PlayerLocationChangedEvent, add: Callable[[PlayerId], None]
    ) -> None:
        add(event.aggregate_id)
        for pid in self._player_audience_query.players_at_spot(event.new_spot_id):
            add(pid)


#: イベント型 → 配信規則。担当と登録された全型がここに載っていることを、構築時
#: (`verify_rules_cover_registry`) とテストの両方が確かめる。
#:
#: **イベントを足したら 1 行足す。忘れれば strategy が構築できない。** 以前は
#: 18 個の isinstance 連鎖で、書き忘れても空リストが返るだけだった。
_RECIPIENT_RULES: RuleTable = {
    # --- 場所の出入り ---
    # 入った本人と、その場に居た全員。すれ違いが見えるように両方へ。
    PlayerLocationChangedEvent: DefaultRecipientStrategy._resolve_player_location_changed,
    # --- 重大な状態変化は位置に関わらず全員へ ---
    PlayerDownedEvent: DefaultRecipientStrategy._deliver_to_everyone_known,
    PlayerRevivedEvent: DefaultRecipientStrategy._deliver_to_everyone_known,
    # --- 本人だけ (他者から見えない内部状態) ---
    PlayerLevelUpEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    PlayerGoldEarnedEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    PlayerGoldPaidEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    ItemAddedToInventoryEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    ItemDroppedFromInventoryEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    ItemRemovedFromInventoryEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    ItemEquippedEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    ItemUnequippedEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    InventorySlotOverflowEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
}
