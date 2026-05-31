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
    MonsterAlertedByPackInSpotEvent,
    MonsterAppearedAtSpotEvent,
    MonsterAteGroundItemEvent,
    MonsterAttackedPlayerInSpotEvent,
    MonsterFeltTemperatureDiscomfortInSpotEvent,
    MonsterFollowedPackFleeInSpotEvent,
    MonsterLeftSpotEvent,
    MonsterPredatedMonsterInSpotEvent,
    MonsterRespondedToPackHelpInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
    PlayerAttackedMonsterInSpotEvent,
    PlayerDroppedItemEvent,
    PlayerGaveItemEvent,
    PlayerPickedUpItemEvent,
    SpotSoundHeardEvent,
    TimeOfDayChangedEvent,
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
        elif isinstance(event, PlayerDroppedItemEvent):
            # witness 最小版: drop の事実を同スポットの他プレイヤーにのみ届ける。
            # 行為者本人には ItemTransferResult.messages で個別返答する。
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, PlayerPickedUpItemEvent):
            # pickup も同様に同スポットの他者にのみ届ける。
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, PlayerGaveItemEvent):
            # give: 同スポットの他プレイヤー (送り手除く) に届ける。
            # 受け手 recipient_entity_id もこの集合に含まれるため自分宛の
            # 受け渡しを観測できる。送り手本人にはツール結果で個別返答する。
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.entity_id, add
            )
        elif isinstance(event, TimeOfDayChangedEvent):
            # 昼夜サイクルのフェーズ変化は世界全体のイベント。屋内 / 屋外を
            # 区別せず、全プレイヤーに観測として届ける (屋内でも空の色や
            # 肌寒さで時間経過は感じられる、というモデル)。
            self._resolve_all_players(add)
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
        elif isinstance(event, MonsterFeltTemperatureDiscomfortInSpotEvent):
            # 温度不快: 同 spot 全員に「相手が寒さ/暑さで弱っている」観測。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterRespondedToPackHelpInSpotEvent):
            # pack 援護: responder の現在 spot 全員に「仲間が駆け付けた」観測。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterFollowedPackFleeInSpotEvent):
            # pack 群れ逃走: follower の現在 spot 全員に「リーダーに続いて
            # 逃げ出した」観測。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, MonsterAlertedByPackInSpotEvent):
            # pack 警戒共有: responder の現在 spot 全員に「仲間の警戒を
            # 察知した」観測。
            self._resolve_all_at_spot(event.spot_id, add)
        elif isinstance(event, SpotSoundHeardEvent):
            # Phase 5: 環境音観測。聞いた本人 (entity_id) だけに届ける。
            # entity_id が known player の ID と一致する場合のみ追加。
            # monster の入退場 (= 自分が聞いた音) は player 観測しない。
            self._resolve_known_player_entity(event.entity_id, add)

        return result

    def _resolve_known_player_entity(self, entity_id: EntityId, add) -> None:
        """`entity_id` が known player の ID と一致するなら recipient に追加。

        Phase 5 環境音観測など「entity 本人にだけ届く」観測で使う。
        `find_all()` を呼ばず `find_by_id` で 1 件だけ引いて O(N) → O(1)。
        """
        player_id = PlayerId(entity_id.value)
        if self._player_status_repository.find_by_id(player_id) is not None:
            add(player_id)

    def _resolve_all_players(self, add) -> None:
        """全プレイヤーを recipient として追加する。

        昼夜サイクルなど世界全体のイベントで使う。除外対象は無い (行為者
        概念が無いイベント)。
        """
        for status in self._player_status_repository.find_all():
            add(status.player_id)

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
        """ConnectionStateChangedEvent の配信先を解決する。

        Issue #184 (軸 3): 観測者の位置に応じた段階的な観測を実装する。
        - 直接観測 (両端 spot): 状態変化を明示的に観測する
        - 間接観測 (隣接 spot 経由で sound_permeability >= 0.1): 「音」として
          観測する。formatter 側で recipient の位置を見て prose を切り替える
        - その他: 配信しない

        sound_permeability の閾値は ``passage.sound_permeability_to_hops`` の
        既定モデル (>=0.1 で可聴) と整合させる。完全遮音 (0.1 未満) の
        connection は隣接にも音が漏れない。
        """
        # 直接観測: 両端 spot の全員
        direct_recipients: Set[int] = set()
        for pid in self._players_at_spot_on_graph(event.from_spot_id):
            add(pid)
            direct_recipients.add(pid.value)
        for pid in self._players_at_spot_on_graph(event.to_spot_id):
            add(pid)
            direct_recipients.add(pid.value)

        # 間接観測: from_spot / to_spot に隣接する spot で、その connection の
        # 音が漏れ伝わる位置にいる人に届ける。直接観測者は除外 (重複防止)。
        for pid in self._audible_neighbor_recipients(event):
            if pid.value in direct_recipients:
                continue
            add(pid)

    def _audible_neighbor_recipients(
        self, event: ConnectionStateChangedEvent
    ) -> List[PlayerId]:
        """変化した connection の音が漏れ届く隣接 spot の player を返す。

        from_spot と to_spot それぞれから 1 hop 出ていく接続のうち、
        その接続自体の sound_permeability が ``0.1`` 以上のものを通って
        隣接 spot に音が伝わるモデル。完全遮音 (permeability < 0.1) の
        connection は隣接観測を生まない。
        """
        graph = self._spot_graph_repository.find_graph()
        # source = 変化が起きた connection の両端
        sources: Set[SpotId] = {event.from_spot_id, event.to_spot_id}
        neighbor_spots: Set[SpotId] = set()
        for source_spot in sources:
            for conn in graph.iter_outgoing_connections_from(source_spot):
                # この path 自体が完全遮音なら隣接にも音は漏れない
                if conn.passage.sound_permeability < 0.1:
                    continue
                other = conn.to_spot_id
                if other in sources:
                    continue  # 直接観測の対象なのでスキップ
                neighbor_spots.add(other)
        result: List[PlayerId] = []
        for spot_id in neighbor_spots:
            result.extend(self._players_at_spot_on_graph(spot_id))
        return result

    def _resolve_all_at_spot(self, spot_id: SpotId, add) -> None:
        for pid in self._players_at_spot_on_graph(spot_id):
            add(pid)
