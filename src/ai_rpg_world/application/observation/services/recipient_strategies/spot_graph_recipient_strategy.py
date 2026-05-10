"""スポットグラフ固有イベントの観測配信先解決。

方針:
- 行為者本人は配信先から除外する（ツール結果で十分）
- 同一スポットの他プレイヤーに social として配信する
- 環境変化（Connection/ObjectState）は影響スポットの全プレイヤーに配信する
"""

from typing import Any, List, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
    MonsterAbandonedChaseInSpotEvent,
    MonsterAppearedAtSpotEvent,
    MonsterAteGroundItemEvent,
    MonsterAttackedPlayerInSpotEvent,
    MonsterLeftSpotEvent,
    MonsterPredatedMonsterInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
    PlayerAttackedMonsterInSpotEvent,
    SpotExploredEvent,
    SpotObjectInteractedEvent,
    SpotObjectInteractionFailedEvent,
    SpotPlayerPreparedActionEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
    SpotPublicEffectObservedEvent,
    ConnectionCreatedEvent,
    ConnectionDestroyedEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class SpotGraphRecipientStrategy(IRecipientResolutionStrategy):
    """スポットグラフ固有イベントの配信先解決。

    行為者は配信先から除外し、同一スポットの他プレイヤーのみに配信する。
    """

    _STRATEGY_KEY = "spot_graph"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._registry = observed_event_registry
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        result: List[PlayerId] = []
        seen: Set[int] = set()

        def add(pid: PlayerId) -> None:
            if pid.value in seen:
                return
            seen.add(pid.value)
            result.append(pid)

        if isinstance(event, EntityEnteredSpotEvent):
            self._resolve_entity_entered(event, add)
        elif isinstance(event, EntityLeftSpotEvent):
            self._resolve_entity_left(event, add)
        elif isinstance(event, SpotObjectInteractedEvent):
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, SpotObjectInteractionFailedEvent):
            # 失敗観測は同じスポットの他プレイヤーにのみ届ける（actor 本人には
            # ツール結果として個別メッセージが返るので除外）。
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, SpotPlayerPreparedActionEvent):
            # 「相方が prepare した」観測は同スポットの他プレイヤーにのみ。
            # actor 本人は prepare ツール結果で個別フィードバックを得る。
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, SpotExploredEvent):
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, ConnectionStateChangedEvent):
            self._resolve_connection_changed(event, add)
        elif isinstance(event, SpotObjectStateChangedEvent):
            # Phase 4-E: actor_entity_id が設定されていれば二重観測防止のため
            # 行為者を除外する。world tick 等の非アクター由来 (None) では
            # 同スポット全員が観測する従来動作。
            if event.actor_entity_id is not None:
                self._resolve_at_spot_excluding_actor(
                    event.spot_id, event.actor_entity_id, add
                )
            else:
                self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, SpotPlayerStateChangedInSpotEvent):
            # Phase 4-E: 公開可能なプレイヤー state 変化は同スポットの
            # 他プレイヤーに届ける。本人は自分の state を current_state
            # プロンプトで知るので除外。
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, SpotPublicEffectObservedEvent):
            # Phase 4-E PR 3: 汎用 public observable effect。actor は
            # ツール結果 (direct_effects) と messages で受け取るのでここ
            # では除外する。actor 不明 (世界 tick 由来等) は全員配信。
            if event.actor_entity_id is not None:
                self._resolve_at_spot_excluding_actor(
                    event.spot_id, event.actor_entity_id, add
                )
            else:
                self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, ConnectionCreatedEvent):
            # 動的に生成された接続は両端 spot 全員に通知。actor 概念は
            # この event には無い (graph aggregate が emit するため)。
            self._resolve_all_at_spot(event.from_spot_id, add)
            self._resolve_all_at_spot(event.to_spot_id, add)
        elif isinstance(event, ConnectionDestroyedEvent):
            self._resolve_all_at_spot(event.from_spot_id, add)
            self._resolve_all_at_spot(event.to_spot_id, add)
        elif isinstance(event, MonsterAppearedAtSpotEvent):
            # モンスター出現は同じスポットに居る全プレイヤーが目撃する。
            # actor 概念は無い (graph aggregate / spawn ロジックが emit する)
            # ため除外対象は無し。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterLeftSpotEvent):
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterAttackedPlayerInSpotEvent):
            # 被害者本人を含む同スポット全員に届ける。プレイヤー側に対する
            # ダメージはツール起因ではなく tick 駆動なので、被害者にも観測
            # として通知して「自分が襲われている」と認識させる必要がある。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, PlayerAttackedMonsterInSpotEvent):
            # 行為者プレイヤー本人にはツール結果として個別 message が返るので
            # 観測経路では除外する（二重観測防止）。同スポットの他プレイヤーには
            # 「Aがオオカミを攻撃した」と social として届ける。
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.attacker_entity_id, add
            )
        elif isinstance(event, MonsterAteGroundItemEvent):
            # 採食観測: monster が actor なので player の self 除外は不要、
            # 同スポット全員が目撃する。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterPredatedMonsterInSpotEvent):
            # 捕食観測: actor / target どちらも monster なので player の
            # self 除外は不要、同スポット全員が目撃する。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterStartedFleeingInSpotEvent):
            # FLEE 状態遷移: 同 spot 全員に「相手が逃げ出した」観測を届ける。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterStartedChasingInSpotEvent):
            # CHASE 状態遷移: 同 spot 全員に「相手が襲いかかってくる」観測。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterAbandonedChaseInSpotEvent):
            # CHASE 諦め: 同 spot 全員に「相手が諦めて去っていった」観測。
            self._resolve_all_at_spot(event.spot_id, add)

        return result

    def _players_at_spot_on_graph(self, spot_id: SpotId) -> List[PlayerId]:
        """グラフ上の指定スポットにいるプレイヤーの一覧を返す。"""
        graph = self._spot_graph_repository.find_graph()
        entity_spot = graph.entity_spot_mapping()
        known_player_ids: Set[int] = {
            s.player_id.value
            for s in self._player_status_repository.find_all()
        }
        return [
            PlayerId(eid.value)
            for eid, sid in entity_spot.items()
            if sid == spot_id and eid.value in known_player_ids
        ]

    def _resolve_entity_entered(self, event: EntityEnteredSpotEvent, add) -> None:
        for pid in self._players_at_spot_on_graph(event.spot_id):
            if pid.value != event.entity_id.value:
                add(pid)

    def _resolve_entity_left(self, event: EntityLeftSpotEvent, add) -> None:
        for pid in self._players_at_spot_on_graph(event.spot_id):
            if pid.value != event.entity_id.value:
                add(pid)

    def _resolve_at_spot_excluding_actor(
        self, spot_id: SpotId, actor_entity_id: EntityId, add
    ) -> None:
        for pid in self._players_at_spot_on_graph(spot_id):
            if pid.value != actor_entity_id.value:
                add(pid)

    def _resolve_connection_changed(
        self, event: ConnectionStateChangedEvent, add
    ) -> None:
        for pid in self._players_at_spot_on_graph(event.from_spot_id):
            add(pid)
        for pid in self._players_at_spot_on_graph(event.to_spot_id):
            add(pid)

    def _resolve_all_at_spot(self, spot_id: SpotId, add) -> None:
        for pid in self._players_at_spot_on_graph(spot_id):
            add(pid)
