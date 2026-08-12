"""観測対象イベント全体を扱うデフォルト配信先解決戦略（既存ロジックを集約）"""

import logging
from typing import Any, List, Optional, Set, Tuple

from ai_rpg_world.application.observation.contracts.interfaces import (
    IPlayerAudienceQueryPort,
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies._dispatch import (
    Add as _Add,
    RecipientRuleWiringError,
    RuleTable,
    verify_rules_cover_registry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import (
    LocationEnteredEvent,
    LocationExitedEvent,
    ItemTakenFromChestEvent,
    ItemStoredInChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.player.event.status_events import (
    PlayerLocationChangedEvent,
    PlayerDownedEvent,
    PlayerRevivedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)

logger = logging.getLogger(__name__)


class DefaultRecipientStrategy(IRecipientResolutionStrategy):
    """
    既存の観測対象イベントすべてに対する配信先解決。
    Gateway / マップ / プレイヤー状態 / インベントリ系を一括で扱う。
    """

    _STRATEGY_KEY = "default"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        player_audience_query: IPlayerAudienceQueryPort,
        world_object_to_player_resolver: IWorldObjectToPlayerResolver,
        spot_graph_repository: Optional[ISpotGraphRepository] = None,
    ) -> None:
        self._registry = observed_event_registry
        self._player_audience_query = player_audience_query
        self._world_object_to_player_resolver = world_object_to_player_resolver
        self._spot_graph_repository = spot_graph_repository
        self._verify_the_registry_and_the_rules_agree()

    def supports(self, event: Any) -> bool:
        """観測対象として定義されているイベント型なら True。"""
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    @classmethod
    def handled_event_types(cls) -> Tuple[type, ...]:
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

    def resolve(self, event: Any) -> List[PlayerId]:
        """配信先プレイヤーIDのリストを返す（重複あり。Resolver が重複除去する）。"""
        result: List[PlayerId] = []
        seen: Set[int] = set()

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

    def _deliver_only_to_the_acting_player(self, event: Any, add: _Add) -> None:
        """行為したプレイヤーだけに届ける (``player_id_value`` が行為者)。"""
        add(PlayerId(event.player_id_value))

    def _deliver_only_to_the_player_behind_the_actor(
        self, event: Any, add: _Add
    ) -> None:
        """``actor_id`` の world object に対応するプレイヤーだけに届ける。

        対応するプレイヤーが居ない (monster 等の) 場合は誰にも届けない。
        """
        player_id = self._world_object_to_player_resolver.resolve_player_id(
            event.actor_id
        )
        if player_id is not None:
            add(player_id)

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

    def _resolve_location_entered(
        self, event: LocationEnteredEvent, add
    ) -> None:
        if event.player_id_value is not None:
            add(PlayerId(event.player_id_value))
        for pid in self._player_audience_query.players_at_spot(event.spot_id):
            add(pid)

    def _resolve_location_exited(self, event: LocationExitedEvent, add) -> None:
        pid = self._world_object_to_player_resolver.resolve_player_id(
            event.object_id
        )
        if pid is not None:
            add(pid)

    def _resolve_player_location_changed(
        self, event: PlayerLocationChangedEvent, add
    ) -> None:
        add(event.aggregate_id)
        for pid in self._player_audience_query.players_at_spot(event.new_spot_id):
            add(pid)

    def _resolve_item_stored_in_chest(
        self, event: ItemStoredInChestEvent, add
    ) -> None:
        add(PlayerId(event.player_id_value))
        for pid in self._player_audience_query.players_at_spot(event.spot_id):
            add(pid)

    def _resolve_spot_weather_changed(
        self, event: SpotWeatherChangedEvent, add
    ) -> None:
        # 屋内スポットでは天候変化を観測させない（窓があるとは限らない・空が直接
        # 見えない前提）。SpotGraph 上で is_outdoor=False のスポットは配信先から外す。
        #
        # ## 例外を握らない (#1035)
        #
        # 以前はこの判定を丸ごと ``except Exception: pass`` で囲み、「リポジトリ参照
        # に失敗した場合は配信を抑制せず従来挙動を維持」していた。そのため
        # ``find_graph`` / ``contains_spot`` / ``get_spot`` のどこで落ちても抑制の
        # ``return`` に到達せず、**屋内にいる人へ屋外の天候が届いた**。trace にも
        # log にも何も残らないので、**発火していないのか、発火して静かなのかを
        # 区別できなかった**。
        #
        # その「従来挙動」は害が大きい。``is_outdoor`` の既定値は False (= 屋内) で、
        # 実測すると abandoned_hospital は 16 spot 中 15 が屋内扱いかつ天候が有効
        # である。握り潰しが発火すれば、ほぼ全スポットへ誤配信する。
        #
        # 上流 (`ObservationRecipientResolver.resolve` / `ObservationPipeline`) に
        # 広い ``except`` は無いので、投げれば実際に見える。どのスポットで落ちたかは
        # 例外だけでは分からないので warning に残す。
        #
        # **「登録されていない」は例外とは別の正当な分岐**として残す。宣言の無い
        # スポットへ天候が来る形は、抑制の判断材料が無いだけで壊れてはいない。
        spot_node = None
        if self._spot_graph_repository is not None:
            try:
                graph = self._spot_graph_repository.find_graph()
                is_registered = graph.contains_spot(event.spot_id)
                spot_node = graph.get_spot(event.spot_id) if is_registered else None
            except Exception:
                logger.warning(
                    "屋内判定に失敗したため天候の配信先を決められない: spot_id=%s",
                    getattr(event.spot_id, "value", event.spot_id),
                    exc_info=True,
                )
                raise
            if spot_node is not None and not spot_node.is_outdoor:
                return
        for pid in self._player_audience_query.players_at_spot(event.spot_id):
            add(pid)


#: イベント型 → 配信規則。担当と登録された全型がここに載っていることを、構築時
#: (`verify_rules_cover_registry`) とテストの両方が確かめる。
#:
#: **イベントを足したら 1 行足す。忘れれば strategy が構築できない。** 以前は
#: 18 個の isinstance 連鎖で、書き忘れても空リストが返るだけだった。
_RECIPIENT_RULES: RuleTable = {
    # --- 場所の出入り ---
    # 入った本人と、その場に居た全員。すれ違いが見えるように両方へ。
    LocationEnteredEvent: DefaultRecipientStrategy._resolve_location_entered,
    # 出ていく側は本人だけ。残った側は EnteredEvent で相手の到着を知る。
    LocationExitedEvent: DefaultRecipientStrategy._resolve_location_exited,
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
    ItemEquippedEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    ItemUnequippedEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,
    InventorySlotOverflowEvent: DefaultRecipientStrategy._deliver_only_to_the_subject,

    # --- 保管庫 ---
    # 取り出しは本人だけ。中身が減ったことは開けた人しか知らない。
    ItemTakenFromChestEvent: DefaultRecipientStrategy._deliver_only_to_the_acting_player,
    # 預け入れは本人とその場の全員へ。「誰かが何かを置いた」は同席者に見える。
    ItemStoredInChestEvent: DefaultRecipientStrategy._resolve_item_stored_in_chest,

    # --- world object を介した行為 (actor が player でないこともある) ---
    ResourceHarvestedEvent: DefaultRecipientStrategy._deliver_only_to_the_player_behind_the_actor,
    WorldObjectInteractedEvent: DefaultRecipientStrategy._deliver_only_to_the_player_behind_the_actor,

    # --- 天候 ---
    # 屋内は空が見えないので配らない (spot graph の is_outdoor で判定)。
    SpotWeatherChangedEvent: DefaultRecipientStrategy._resolve_spot_weather_changed,
}
