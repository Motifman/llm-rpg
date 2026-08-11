"""モンスター系イベントの観測配信先解決戦略"""

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
from ai_rpg_world.domain.monster.event.monster_events import (
    ActorStateChangedEvent,
    BehaviorStuckEvent,
    MonsterDamagedEvent,
    MonsterDecidedToInteractEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterFedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterRespawnedEvent,
    MonsterCreatedEvent,
    MonsterSpawnedEvent,
    TargetLostEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class MonsterRecipientStrategy(IRecipientResolutionStrategy):
    """モンスターイベントの配信先を解決する。基本は「同一スポットのプレイヤー」＋必要なら攻撃者本人。"""

    _STRATEGY_KEY = "monster"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        player_audience_query: IPlayerAudienceQueryPort,
        physical_map_repository: Optional[PhysicalMapRepository],
        world_object_to_player_resolver: IWorldObjectToPlayerResolver,
        monster_repository: Optional[MonsterRepository] = None,
    ) -> None:
        # physical_map_repository は tile-map ベース世界でのみ意味を持つ。
        # spot_graph 専用ランタイムでは None で渡され、
        # _spot_id_from_world_object は常に None を返す (該当 monster が tile に
        # 紐付かない世界では、攻撃者の spot 解決は別経路で行われる)。
        self._registry = observed_event_registry
        self._player_audience_query = player_audience_query
        self._physical_map_repository = physical_map_repository
        self._world_object_to_player_resolver = world_object_to_player_resolver
        self._monster_repository = monster_repository
        self._verify_the_registry_and_the_rules_agree()

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    @classmethod
    def handled_event_types(cls) -> Tuple[type, ...]:
        """配信規則を持つイベント型の一覧 (「配らない」宣言のものは含まない)。"""
        return tuple(_RECIPIENT_RULES)

    @classmethod
    def event_types_delivered_to_nobody(cls) -> Tuple[type, ...]:
        """意図的に誰にも配らないイベント型の一覧。"""
        return tuple(_DELIVERS_TO_NOBODY)

    def _verify_the_registry_and_the_rules_agree(self) -> None:
        """担当と宣言された全イベント型が、規則か「配らない」宣言に載っているか確かめる。"""
        verify_rules_cover_registry(
            registry=self._registry,
            strategy_key=self._STRATEGY_KEY,
            rules=_RECIPIENT_RULES,
            delivers_to_nobody=_DELIVERS_TO_NOBODY,
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        """配信先プレイヤーIDのリストを返す（重複は除く）。

        以前は重複を残していた (``recipients.append`` を直接呼んでいた)。同じ
        場所に居る攻撃者は「その場の全員」と「攻撃した本人」の両方で足されるので
        実際に重複が出る。``ObservationRecipientResolver`` が出口で必ず
        ``_deduplicate`` するため外からは見えなかったが、**見えない差は誰も
        検証できない**。実際、ここに重複除去を足しても全 6,181 件が緑のままだと
        レビューで実証された。

        他の 2 つの strategy (spot_graph / default) は内側で除いているので、
        揃えて「重複を除いて返す」を明示した契約にする。
        """
        # イベント型 → 配信規則の表引き。以前は isinstance の連鎖で、末尾の
        # fall-through が空リストを返していた。そのため「意図的に配らない」型と
        # 「規則を書き忘れた型」が同じ見た目になっていた。表を 2 つに分けて、
        # 前者は理由つきで宣言し、後者は構築時に落とす。
        if type(event) in _DELIVERS_TO_NOBODY:
            return []

        rule = _RECIPIENT_RULES.get(type(event))
        if rule is None:
            raise RecipientRuleWiringError(
                f"{type(event).__name__} に配信規則がありません "
                "(構築時の検査を通っているはずなので、表が実行中に変わっています)"
            )

        recipients: List[PlayerId] = []
        seen: Set[int] = set()

        def add(player_id: PlayerId) -> None:
            if player_id.value in seen:
                return
            seen.add(player_id.value)
            recipients.append(player_id)

        rule(self, event, add)
        return recipients

    # ------------------------------------------------------------------
    # 配信規則。表 (_RECIPIENT_RULES) から引かれる。
    # ------------------------------------------------------------------

    def _add_all_at_spot(self, spot_id: Optional[SpotId], add: _Add) -> None:
        """スポットが判っていれば、そこに居る全プレイヤーを足す。"""
        if spot_id is None:
            return
        for player_id in self._player_audience_query.players_at_spot(spot_id):
            add(player_id)

    def _deliver_to_everyone_at_the_declared_spot(self, event: Any, add: _Add) -> None:
        """イベントが持つ ``spot_id`` に居る全員へ届ける。

        出現・再出現はイベント自身がスポットを持つので、monster を引き直さない。
        """
        self._add_all_at_spot(event.spot_id, add)

    def _deliver_to_everyone_at_the_monsters_spot(self, event: Any, add: _Add) -> None:
        """monster の現在スポットに居る全員へ届ける。

        イベントがスポットを持たないので monster を引いて調べる。monster
        リポジトリが未注入なら誰にも届かない (tile-map 前提の経路)。
        """
        self._add_all_at_spot(self._spot_id_from_monster(event.aggregate_id), add)

    def _deliver_death_to_the_spot_and_the_killer(self, event: Any, add: _Add) -> None:
        """死んだ場所の全員と、倒したプレイヤーへ届ける。

        倒した本人は離れていることがある (遠距離の一撃) ので、スポットとは別に
        足す。イベントがスポットを持たない場合は monster を引く。
        """
        self._add_all_at_spot(
            event.spot_id or self._spot_id_from_monster(event.aggregate_id), add
        )
        if event.killer_player_id is not None:
            add(event.killer_player_id)

    def _deliver_damage_to_the_spot_and_the_attacker(
        self, event: Any, add: _Add
    ) -> None:
        """monster の居る場所の全員と、攻撃したプレイヤーへ届ける。"""
        self._add_all_at_spot(self._spot_id_from_monster(event.aggregate_id), add)
        if event.attacker_id is not None:
            player_id = self._world_object_to_player_resolver.resolve_player_id(
                event.attacker_id
            )
            if player_id is not None:
                add(player_id)

    def _deliver_to_everyone_at_the_actors_spot(self, event: Any, add: _Add) -> None:
        """``actor_id`` の world object が居るスポットの全員へ届ける。

        physical map リポジトリが未注入 (spot_graph 専用ランタイム) なら誰にも
        届かない。
        """
        self._add_all_at_spot(self._spot_id_from_world_object(event.actor_id), add)

    def _spot_id_from_world_object(self, object_id) -> Optional[SpotId]:
        if self._physical_map_repository is None:
            return None
        return self._physical_map_repository.find_spot_id_by_object_id(object_id)

    def _spot_id_from_monster(self, monster_id) -> Optional[SpotId]:
        if self._monster_repository is None:
            return None
        monster = self._monster_repository.find_by_id(monster_id)
        if monster is None:
            return None
        return monster.spot_id


#: イベント型 → 配信規則。
_RECIPIENT_RULES: RuleTable = {
    # 出現・再出現はイベント自身が spot_id を持つ。
    MonsterSpawnedEvent: MonsterRecipientStrategy._deliver_to_everyone_at_the_declared_spot,
    MonsterRespawnedEvent: MonsterRecipientStrategy._deliver_to_everyone_at_the_declared_spot,
    # 死は場所の全員 + 倒した本人 (遠距離の一撃で離れていることがある)。
    MonsterDiedEvent: MonsterRecipientStrategy._deliver_death_to_the_spot_and_the_killer,
    # 被弾は場所の全員 + 攻撃した本人。
    MonsterDamagedEvent: MonsterRecipientStrategy._deliver_damage_to_the_spot_and_the_attacker,
    # 回避・回復は monster を引いて場所を決める (イベントが spot を持たない)。
    MonsterEvadedEvent: MonsterRecipientStrategy._deliver_to_everyone_at_the_monsters_spot,
    MonsterHealedEvent: MonsterRecipientStrategy._deliver_to_everyone_at_the_monsters_spot,
    # 採食・状態変化は actor の world object から場所を引く。
    MonsterFedEvent: MonsterRecipientStrategy._deliver_to_everyone_at_the_actors_spot,
    ActorStateChangedEvent: MonsterRecipientStrategy._deliver_to_everyone_at_the_actors_spot,
}

#: 意図的に誰にも配らないイベント型と、その理由。
#:
#: 以前は isinstance 連鎖の末尾で空リストを返していたため、**「配らないと決めた
#: 型」と「規則を書き忘れた型」が同じ見た目**だった。理由を書く場所を分けて、
#: 書き忘れは構築時に落ちるようにした (`_ALLOWED_UNCONSUMED` と同じ判断)。
#:
#: ここに挙げた 8 型は、配信先だけでなく **formatter も一致して None を返す**
#: ことを確認済み (monster_formatter.py の `_format_monster_created` /
#: `_format_target_spotted` / `_format_target_lost` / `_format_behavior_stuck` /
#: `_format_monster_mp_recovered` / `_format_monster_decided_to_*`)。2 層が揃って
#: 「観測させない」と言っているので、意図的な非観測と判断した。
_DELIVERS_TO_NOBODY: dict[type, str] = {
    MonsterCreatedEvent: (
        "集約の生成そのもの。世界に現れる瞬間は MonsterSpawnedEvent が表すので、"
        "生成は誰の知覚にも対応しない"
    ),
    MonsterMpRecoveredEvent: (
        "monster の内部資源の回復。外から見て分かる変化ではないので、"
        "観測させると monster の内部状態が漏れる"
    ),
    MonsterDecidedToMoveEvent: (
        "monster の意思決定そのもの。決定は行動として現れてから観測される "
        "(移動なら EntityEnteredSpotEvent)。決定を配ると先読みができてしまう"
    ),
    MonsterDecidedToUseSkillEvent: "同上。決定ではなく発動の結果を観測させる",
    MonsterDecidedToInteractEvent: "同上",
    TargetSpottedEvent: (
        "monster が誰かを標的に定めた、という内部状態。狙われたことを本人に"
        "伝えるかは別の設計判断で、伝えるなら追跡の観測 "
        "(MonsterStartedChasingInSpotEvent) が担う"
    ),
    TargetLostEvent: "同上。見失ったことは MonsterAbandonedChaseInSpotEvent が担う",
    BehaviorStuckEvent: (
        "monster の行動が詰まったという実装側の診断情報。世界の出来事ではないので"
        "観測にしない (trace で見る)"
    ),
}
