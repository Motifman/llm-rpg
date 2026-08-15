"""スポットグラフ固有イベントの観測配信先解決。

方針:
- 行為者本人は配信先から除外する（ツール結果で十分）
- 同一スポットの他プレイヤーに social として配信する
- 環境変化（Connection/ObjectState）は影響スポットの全プレイヤーに配信する
"""

from typing import Any, Callable, List, Set, Tuple

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies._dispatch import (
    Add,
    RecipientRuleWiringError,
    RuleTable,
    verify_rules_cover_registry,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
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
    MarketBoardActivityEvent,
    MarketDeliveryLeftAtBoardEvent,
    PlayerTradeOfferEvent,
    PlayerTradedWithMerchantEvent,
    PlayerOverflowedItemEvent,
    PlayerPickedUpItemEvent,
    SpotPresenceListenedEvent,
    SpotSoundHeardEvent,
    TimeOfDayChangedEvent,
    GamePhaseChangedEvent,
    MeetingVoteCastEvent,
    MeetingVoteResolvedEvent,
    SpotExploredEvent,
    PlayerInteractedWithPlayerEvent,
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
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)


#: 配信規則が recipient を足すために呼ぶ関数。重複は呼ばれた側で潰される。
_Add = Add


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
        departed_position_store: DepartedPositionStore | None = None,
    ) -> None:
        self._registry = observed_event_registry
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._departed_position_store = departed_position_store
        self._verify_the_registry_and_the_rules_agree()

    def _verify_the_registry_and_the_rules_agree(self) -> None:
        """担当と宣言されたイベント型すべてに配信規則があることを構築時に確かめる。"""
        verify_rules_cover_registry(
            registry=self._registry,
            strategy_key=self._STRATEGY_KEY,
            rules=_RECIPIENT_RULES,
        )

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    @classmethod
    def handled_event_types(cls) -> Tuple[type, ...]:
        """配信規則を持つイベント型の一覧。

        ``ObservedEventRegistry`` が spot_graph に割り当てた型と一致している
        ことを ``test_recipient_dispatch_is_exhaustive.py`` が強制する。
        """
        return tuple(_RECIPIENT_RULES)

    def resolve(self, event: Any) -> List[PlayerId]:
        result: List[PlayerId] = []
        seen: Set[int] = set()

        def add(pid: PlayerId) -> None:
            if pid.value in seen:
                return
            seen.add(pid.value)
            result.append(pid)

        # イベント型 → 配信規則の表引き。以前は 34 個の isinstance の連鎖で、
        # **どれにも当たらないと空リストを返して終わっていた**。レジストリに
        # 登録したのに分岐を書き忘れると、supports() は True・resolve() は空・
        # 例外なし・テスト緑で、そのイベントは誰にも観測されなかった。
        #
        # 表引きなら、規則の追加は 1 行になり、忘れれば網羅テストが落ちる。
        #
        # 型は厳密一致で引く。イベント型に継承関係は無く (35 型で 0 件)、
        # レジストリ自身も ``type(event)`` で引いているので判定がずれない。
        rule = _RECIPIENT_RULES.get(type(event))
        if rule is None:
            # 構築時に突き合わせているので、ここに来ることは無い。来たら不変
            # 条件が壊れているので落とす。空リストを返すと「配信先が居なかった」
            # と区別がつかず、配線漏れが run 分析から消える。
            raise RecipientRuleWiringError(
                f"{type(event).__name__} に配信規則がありません "
                "(構築時の検査を通っているはずなので、表が実行中に変わっています)"
            )
        rule(self, event, add)

        # 倒れている player の除外は **resolver の出口** で行う
        # (ObservationRecipientResolver._without_the_fallen)。
        #
        # かつてはここに書いていたが、上のコメント自身が「speech 等は別経路
        # なので、必要ならその strategy 側で除外」と認めていて、**書かれない
        # まま実 run 008 で漏れた** (死んだセナが生者の声を拾った)。
        # strategy ごとに配ると、strategy を 1 つ足した人が忘れる。
        return result

    # ------------------------------------------------------------------
    # 配信規則。表 (_RECIPIENT_RULES) から引かれる。
    # ------------------------------------------------------------------

    def _deliver_to_others_at_the_event_spot(self, event: Any, add: _Add) -> None:
        """同じスポットの他プレイヤーへ届ける (行為者 ``entity_id`` を除く)。

        行為者本人にはツール結果として個別メッセージが返るので、観測経路では
        除外する (二重観測の防止)。
        """
        self._resolve_at_spot_excluding_actor(event.spot_id, event.entity_id, add)

    def _deliver_only_to_the_subject(self, event: Any, add: _Add) -> None:
        """出来事の主体だけへ届ける (居場所を問わない)。"""
        add(PlayerId(int(event.entity_id)))

    def _deliver_market_activity(self, event: Any, add: _Add) -> None:
        """板の前に居る人と、離れていても知るべき当事者へ届ける。

        板は公開の場なので、そこで起きたことはその場に居る人に見える。加えて、
        **板越しの取引では当事者がその場に居ない**ことがある — 自分の出品が
        売れた、預けた注文が流れた。届けないと、次に板へ寄るまで自分の持ち物が
        変わった理由が分からない。

        期限切れは第三者に流さない。当事者だけの出来事で、毎回流すと板の前が
        通知で埋まる (Phase 2 の辞退・期限切れと同じ扱い)。
        """
        if str(event.kind).startswith("expired"):
            # 期限切れは**持ち主だけ**の出来事。行為者は世界の時計なので、
            # 「行為者を除く」の除外が効かない (持ち主 = entity_id)。ここで
            # 明示的に持ち主へ届ける。第三者には流さない — 毎回流すと板の前が
            # 通知で埋まる (Phase 2 の辞退・期限切れと同じ扱い)。
            add(PlayerId(int(event.entity_id)))
            return
        self._resolve_at_spot_excluding_actor(event.spot_id, event.entity_id, add)
        notify = event.notify_entity_id
        if notify is not None and int(notify) != int(event.entity_id):
            # 売り手がその場に居なくても「売れた」は届ける。届かないと、次に
            # 板へ寄るまで自分の持ち物が変わった理由が分からない。
            add(PlayerId(int(notify)))

    def _deliver_to_others_only_when_witnessed(self, event: Any, add: _Add) -> None:
        """``witness_policy`` が SAME_SPOT のときだけ、同席者へ届ける。

        ACTOR_ONLY なら誰にも届けない (空集合)。行為者本人は別経路 (ツール結果
        の result_message) で結果を受け取るので observation を出さなくて構わ
        ない。「壁の写真を見つめる」のような私的な行為で、他者に気付かれずに
        済ませるために要る。
        """
        if event.witness_policy == WitnessPolicy.SAME_SPOT:
            self._resolve_at_spot_excluding_actor(event.spot_id, event.entity_id, add)

    def _deliver_interpersonal_action(self, event: Any, add: _Add) -> None:
        """対人行為を届ける。物体版と違い **対象本人は配信先に含める**。

        自分が何をされたのかは第三者の目撃より先に知る必要がある。倒れている
        間の出来事でも、起きたときに読めなければ持ち物が減った理由が永久に
        分からない。

        ACTOR_ONLY (秘匿して奪う) のときは既定で対象にも届けない。気づかれずに
        盗るという行為が成立しなくなるため。ただし ``notify_target`` を宣言した
        行為だけは、第三者に伏せたまま対象本人に届ける (可視性の 3 軸目)。
        「毒を盛られた本人だけが異変に気づく」は、この組み合わせでしか書けない。
        """
        if event.witness_policy == WitnessPolicy.SAME_SPOT:
            # 対象は「同スポットの他プレイヤー」として既に足されるので、
            # notify_target 側の分岐へは進まない (意図的)。
            self._resolve_at_spot_excluding_actor(event.spot_id, event.entity_id, add)
        elif event.notify_target:
            # 直接属性で読む。以前は getattr(event, "notify_target", False) で、
            # フィールド名を間違えたり将来リネームしたときに **既定値 False で
            # 「対象に届けない」へ静かに倒れた**。伏せたまま本人だけに届ける、
            # という宣言が黙って無効になる形なので、無ければ AttributeError で
            # 落とす。
            add(PlayerId(int(event.target_entity_id)))

    def _deliver_to_everyone_at_the_event_spot(self, event: Any, add: _Add) -> None:
        """同じスポットに居る全プレイヤーへ届ける (除外なし)。

        モンスターの出現・捕食・状態遷移など、行為者がプレイヤーでないイベント
        で使う。被害者本人も含める: プレイヤーへのダメージは tick 駆動で
        ツール起因ではないので、観測として届けないと「自分が襲われている」と
        認識できない。
        """
        self._resolve_all_at_spot(event.spot_id, add)

    def _deliver_to_others_excluding_the_attacker(self, event: Any, add: _Add) -> None:
        """攻撃したプレイヤーを除いて、同じスポットの全員へ届ける。

        行為者にはツール結果として個別 message が返るので観測経路では除外する。
        同席者には「A がオオカミを攻撃した」と社会的な観測として届く。
        """
        self._resolve_at_spot_excluding_actor(event.spot_id, event.attacker_entity_id, add)

    def _deliver_excluding_the_actor_if_known(self, event: Any, add: _Add) -> None:
        """``actor_entity_id`` が判れば除外し、判らなければ同席者全員へ届ける。

        world tick 由来のように行為者の概念が無い (None) イベントでは、同じ
        スポットの全員が観測する。行為者が判るときだけ二重観測を防ぐ。
        """
        if event.actor_entity_id is not None:
            self._resolve_at_spot_excluding_actor(
                event.spot_id, event.actor_entity_id, add
            )
        else:
            self._resolve_all_at_spot(event.spot_id, add)

    def _deliver_to_both_ends_of_the_connection(self, event: Any, add: _Add) -> None:
        """接続の両端スポットの全員へ届ける。

        動的に生成・破棄された接続は、行為者の概念を持たない (graph aggregate
        が emit する) ので除外対象は無い。
        """
        self._resolve_all_at_spot(event.from_spot_id, add)
        self._resolve_all_at_spot(event.to_spot_id, add)

    def _deliver_to_everyone_in_the_world(self, event: Any, add: _Add) -> None:
        """世界の全プレイヤーへ届ける。

        会議の開始や昼夜の変化は世界全体の出来事で、届かない人が居るとその人
        だけ議論に参加できないまま進む。屋内でも空の色や肌寒さで時間経過は
        感じられる、というモデルなので屋内 / 屋外を区別しない。

        倒れている player は resolve() の出口の一括除外で落ちる (ターンが
        回らないので観測を消化できない: Issue #621 Phase 4)。
        """
        self._resolve_all_players(add)

    def _deliver_vote_progress_to_the_other_voters(
        self, event: Any, add: _Add
    ) -> None:
        """投票した本人以外の参加者へ、投票の進捗を届ける。

        本人にはツール結果が返る。本人を再起床させると、投票直後に余分な
        会話ターンを 1 回増やすことになる。
        """
        for status in self._player_status_repository.find_all():
            if status.player_id != event.voter_player_id:
                add(status.player_id)

    def _deliver_only_to_the_listener(self, event: Any, add: _Add) -> None:
        """聞いた本人 (``entity_id``) だけに届ける。

        環境音の観測。``entity_id`` が既知の player と一致するときだけ足す。
        monster の入退場 (= monster 自身が聞いた音) は player の観測にしない。
        """
        self._resolve_known_player_entity(event.entity_id, add)

    def _resolve_known_player_entity(self, entity_id: EntityId, add) -> None:
        """`entity_id` が known player の ID と一致するなら recipient に追加。

        Phase 5 環境音観測など「entity 本人にだけ届く」観測で使う。
        `find_all()` を呼ばず `find_by_id` で 1 件だけ引いて O(N) → O(1)。
        """
        player_id = PlayerId(entity_id.value)
        if self._player_status_repository.find_by_id(player_id) is not None:
            add(player_id)

    def _resolve_all_players(self, add: Callable[[PlayerId], None]) -> None:
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
        physical = [
            PlayerId(eid.value)
            for eid, sid in entity_spot.items()
            if sid == spot_id and eid.value in known_player_ids
        ]
        departed = (
            list(self._departed_position_store.players_at(spot_id))
            if self._departed_position_store is not None
            else []
        )
        seen = {int(player_id) for player_id in physical}
        return physical + [pid for pid in departed if int(pid) not in seen]

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


#: イベント型 → 配信規則。``ObservedEventRegistry`` が spot_graph に割り当てた
#: 全型がここに載っていることを、テストが enum ではなくレジストリを回して
#: 強制する (``test_recipient_dispatch_is_exhaustive.py``)。
#:
#: **イベントを足したら 1 行足す。忘れればテストが落ちる。** 以前は 34 個の
#: isinstance 連鎖で、書き忘れても空リストが返るだけだった。
_RECIPIENT_RULES: RuleTable = {
    # --- 同席者へ (行為者 entity_id を除く) ---
    EntityEnteredSpotEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,
    EntityLeftSpotEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,
    # 失敗観測。actor 本人にはツール結果として個別メッセージが返る。
    SpotObjectInteractionFailedEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,
    # give: 受け手もこの集合に含まれるので、自分宛の受け渡しを観測できる。
    PlayerGaveItemEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,
    # 商人との売買。相手は NPC なので受け手は居らず、同席の第三者だけが見る。
    PlayerTradedWithMerchantEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,
    # 人同士の取引。持ちかけと成立は第三者にも見えるが、辞退と期限切れは
    # 当事者だけに届く (formatter が kind を見て第三者ぶんを落とす)。
    PlayerTradeOfferEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MarketBoardActivityEvent: SpotGraphRecipientStrategy._deliver_market_activity,
    # 取り落としは**本人にも届ける**。置いた側は自分の行動なので結果文で分かるが、
    # 取り落としは「採取の結果が手元に無い理由」で、本人が知らないと拾い直せない。
    PlayerOverflowedItemEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    # 届かなかった品の行き先は、**買い手にだけ**届ける。板の前に居る人には
    # 「地面に品が増えた」以上の意味が無く、買い手には gold が減っているのに
    # 品が無い理由がここでしか分からない。
    MarketDeliveryLeftAtBoardEvent: SpotGraphRecipientStrategy._deliver_only_to_the_subject,
    # 「相方が prepare した」観測。actor は prepare のツール結果を得る。
    SpotPlayerPreparedActionEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,
    SpotExploredEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,
    # 公開可能なプレイヤー state 変化。本人は current_state プロンプトで知る。
    SpotPlayerStateChangedInSpotEvent: SpotGraphRecipientStrategy._deliver_to_others_at_the_event_spot,

    # --- witness_policy を見てから同席者へ ---
    SpotObjectInteractedEvent: SpotGraphRecipientStrategy._deliver_to_others_only_when_witnessed,
    PlayerDroppedItemEvent: SpotGraphRecipientStrategy._deliver_to_others_only_when_witnessed,
    PlayerPickedUpItemEvent: SpotGraphRecipientStrategy._deliver_to_others_only_when_witnessed,

    # --- 対人行為 (対象本人を含める / notify_target で伏せたまま届ける) ---
    PlayerInteractedWithPlayerEvent: SpotGraphRecipientStrategy._deliver_interpersonal_action,

    # --- 行為者が判れば除外、判らなければ同席者全員 ---
    SpotObjectStateChangedEvent: SpotGraphRecipientStrategy._deliver_excluding_the_actor_if_known,
    SpotPublicEffectObservedEvent: SpotGraphRecipientStrategy._deliver_excluding_the_actor_if_known,

    # --- 接続の変化 ---
    # 状態変化は両端 + 音が漏れる隣接まで (Issue #184 の軸 3)。
    ConnectionStateChangedEvent: SpotGraphRecipientStrategy._resolve_connection_changed,
    ConnectionCreatedEvent: SpotGraphRecipientStrategy._deliver_to_both_ends_of_the_connection,
    ConnectionDestroyedEvent: SpotGraphRecipientStrategy._deliver_to_both_ends_of_the_connection,

    # --- 世界全体 ---
    # 追放が起きなかった場合も同じ経路を通す (会議設計 doc §6.4)。
    MeetingVoteResolvedEvent: SpotGraphRecipientStrategy._deliver_to_everyone_in_the_world,
    GamePhaseChangedEvent: SpotGraphRecipientStrategy._deliver_to_everyone_in_the_world,
    TimeOfDayChangedEvent: SpotGraphRecipientStrategy._deliver_to_everyone_in_the_world,
    MeetingVoteCastEvent: SpotGraphRecipientStrategy._deliver_vote_progress_to_the_other_voters,

    # --- 同席者全員 (行為者がプレイヤーでないので除外なし) ---
    MonsterAppearedAtSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterLeftSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    # 被害者本人も含める (tick 駆動なのでツール結果が返らない)。
    MonsterAttackedPlayerInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterAteGroundItemEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterPredatedMonsterInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterStartedFleeingInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterStartedChasingInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterAbandonedChaseInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterFeltTemperatureDiscomfortInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterRespondedToPackHelpInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterFollowedPackFleeInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,
    MonsterAlertedByPackInSpotEvent: SpotGraphRecipientStrategy._deliver_to_everyone_at_the_event_spot,

    # --- 攻撃したプレイヤーだけ除外 (フィールド名が attacker_entity_id) ---
    PlayerAttackedMonsterInSpotEvent: SpotGraphRecipientStrategy._deliver_to_others_excluding_the_attacker,

    # --- 聞いた本人だけ ---
    SpotSoundHeardEvent: SpotGraphRecipientStrategy._deliver_only_to_the_listener,
    SpotPresenceListenedEvent: SpotGraphRecipientStrategy._deliver_only_to_the_listener,
}
