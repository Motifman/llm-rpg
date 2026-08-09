"""観測配信先をイベントから解決する実装（戦略パターン）"""

from typing import TYPE_CHECKING, Any, List, Optional, Sequence, Set

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.repository.sns_user_repository import UserRepository

from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationRecipientResolver,
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.player.services.player_life_query import PlayerLifeQuery
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
from ai_rpg_world.domain.trade.repository.trade_repository import TradeRepository
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
    SkillLoadoutRepository,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)
from ai_rpg_world.application.observation.services.world_object_to_player_resolver import (
    WorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.recipient_strategies import (
    CombatRecipientStrategy,
    ConversationRecipientStrategy,
    DefaultRecipientStrategy,
    GuildRecipientStrategy,
    HarvestRecipientStrategy,
    MonsterRecipientStrategy,
    PursuitRecipientStrategy,
    QuestRecipientStrategy,
    ShopRecipientStrategy,
    SkillRecipientStrategy,
    SpeechRecipientStrategy,
    SnsRecipientStrategy,
    TradeRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.item_use_recipient_strategy import (
    ItemUseRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    SpotGraphRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_speech_recipient_strategy import (
    SpotGraphSpeechRecipientStrategy,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
    SoundPropagationService,
)


#: 「自分のこと」と判断してよい event の集約種別。
#:
#: 倒れた / 復帰した は player 集約から出る。spot graph の event は
#: aggregate_id が graph を指すので、ここに含めてはいけない。
_PLAYER_AGGREGATE_TYPE = "PlayerStatusAggregate"


class ObservationRecipientResolver(IObservationRecipientResolver):
    """
    ドメインイベントから観測の配信先プレイヤーID一覧を解決する。
    登録された戦略のうち、supports(event) が True の先頭戦略に委譲し、
    返却リストの重複を除去して返す。
    """

    def __init__(
        self,
        strategies: Sequence[IRecipientResolutionStrategy],
        # 本番は共有 query を渡す。軽量な既存構築経路では status repository
        # から同じ規則の query を作り、判定を二重実装しない。
        player_status_repository: Optional[PlayerStatusRepository] = None,
        player_life_query: Optional[PlayerLifeQuery] = None,
    ) -> None:
        self._strategies = list(strategies)
        self._player_life_query = player_life_query or PlayerLifeQuery(
            player_status_repository=player_status_repository,
            player_outcome_registry=None,
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        """イベント種別に応じて配信先を返す。観測対象外または未知のイベントは空リスト。"""
        for strategy in self._strategies:
            if strategy.supports(event):
                raw = strategy.resolve(event)
                return self._without_the_fallen(event, self._deduplicate(raw))
        return []

    def _without_the_fallen(self, event: Any, player_ids: List[PlayerId]) -> List[PlayerId]:
        """倒れている人を、**自分以外のこと**の配信先から外す。

        倒れている player は LLM ターンが回らず観測を消化できない。復帰時に
        buffer を clear する仕様 (復活直前の他者発話を引きずらない) とも
        整合しない。

        ## なぜ strategy ではなくここに置くか

        以前は SpotGraphRecipientStrategy の中だけにあった。当時のコメント
        自身が「speech 等は別経路なので、必要ならその strategy 側で除外」と
        認めていて、**実際に漏れていた**。実 run 008 で、死んだセナが t=5 に
        生者の声を拾っている。

        各 strategy に同じ判定を配ると、strategy を 1 つ足した人が忘れる。
        **出口は 1 つしかないので、ここに置けば忘れようがない。**

        ## 自分のことは届く

        一律に落とすと、倒れた本人に「倒れて動けなくなりました」が届かなく
        なる。復帰の通知も同じ。**規則は「倒れている人は周りのことを観測
        しない」であって「何も観測しない」ではない。**

        event の主体 (``aggregate_id``) と一致する相手だけは残す。
        """
        if not player_ids:
            return player_ids
        subject = self._subject_player_id(event)
        return [
            pid
            for pid in player_ids
            if pid.value == subject
            or self._player_life_query.can_receive_world_observation(pid)
        ]

    @staticmethod
    def _subject_player_id(event: Any) -> Optional[int]:
        """その event が「誰のこと」か。player を指していなければ None。

        **``aggregate_type`` を必ず見る。** spot graph の event は
        ``aggregate_id`` が graph の id で、その値も int なので、見ないと
        **graph の id と同じ番号の player が「主体」に化ける**。
        graph id が 1 なら player 1 だけが観測を受け取り続ける、という
        気付きにくい形になる。テストがこれを捕まえた。
        """
        if getattr(event, "aggregate_type", None) != _PLAYER_AGGREGATE_TYPE:
            return None
        value = getattr(getattr(event, "aggregate_id", None), "value", None)
        return int(value) if isinstance(value, int) else None

    def _is_player_down(self, player_id: PlayerId) -> bool:
        """既存テスト向けに、観測可否の逆を倒れている判定として返す。"""
        return not self._player_life_query.can_receive_world_observation(player_id)

    def _deduplicate(self, player_ids: List[PlayerId]) -> List[PlayerId]:
        """順序を保ちつつ重複を除去する。"""
        seen: Set[int] = set()
        result: List[PlayerId] = []
        for pid in player_ids:
            if pid.value in seen:
                continue
            seen.add(pid.value)
            result.append(pid)
        return result


def create_observation_recipient_resolver(
    player_status_repository: PlayerStatusRepository,
    player_life_query: Optional[PlayerLifeQuery] = None,
    physical_map_repository: Optional[PhysicalMapRepository] = None,
    quest_repository: Optional[QuestRepository] = None,
    guild_repository: Optional[GuildRepository] = None,
    shop_repository: Optional[ShopRepository] = None,  # 後方互換のみ（未使用）
    trade_repository: Optional[TradeRepository] = None,
    monster_repository: Optional[MonsterRepository] = None,
    hit_box_repository: Optional[HitBoxRepository] = None,
    skill_loadout_repository: Optional[SkillLoadoutRepository] = None,
    skill_deck_progress_repository: Optional[SkillDeckProgressRepository] = None,
    sns_user_repository: Optional["UserRepository"] = None,
    spot_graph_repository: Optional[ISpotGraphRepository] = None,
) -> IObservationRecipientResolver:
    """
    既存と同様の振る舞いになる Resolver を組み立てる。
    デフォルト戦略と WorldObjectToPlayerResolver を用いる。
    """
    _ = shop_repository
    _ = sns_user_repository
    observed_event_registry = ObservedEventRegistry()
    # tile-map なし (spot_graph 専用) ランタイムでは physical_map_repository=None
    # で呼ばれる。その場合は NullWorldObjectToPlayerResolver を使い、
    # WorldObjectId→PlayerId の解決は常に None (= 該当なし) として処理する。
    if physical_map_repository is not None:
        world_object_resolver: IWorldObjectToPlayerResolver = (
            WorldObjectToPlayerResolver(physical_map_repository)
        )
    else:
        from ai_rpg_world.application.observation.services.null_world_object_to_player_resolver import (
            NullWorldObjectToPlayerResolver,
        )
        world_object_resolver = NullWorldObjectToPlayerResolver()
    player_audience_query = PlayerAudienceQueryService(
        player_status_repository=player_status_repository,
        spot_graph_repository=spot_graph_repository,
    )
    strategies: List[IRecipientResolutionStrategy] = [
        ConversationRecipientStrategy(
            observed_event_registry=observed_event_registry,
        ),
        QuestRecipientStrategy(
            observed_event_registry=observed_event_registry,
            player_audience_query=player_audience_query,
            quest_repository=quest_repository,
            guild_repository=guild_repository,
        ),
        ShopRecipientStrategy(
            observed_event_registry=observed_event_registry,
            player_audience_query=player_audience_query,
        ),
        TradeRecipientStrategy(
            observed_event_registry=observed_event_registry,
            trade_repository=trade_repository,
        ),
        SnsRecipientStrategy(
            observed_event_registry=observed_event_registry,
        ),
        GuildRecipientStrategy(
            observed_event_registry=observed_event_registry,
            player_audience_query=player_audience_query,
            guild_repository=guild_repository,
        ),
        HarvestRecipientStrategy(
            observed_event_registry=observed_event_registry,
            world_object_to_player_resolver=world_object_resolver,
        ),
        PursuitRecipientStrategy(
            observed_event_registry=observed_event_registry,
            world_object_to_player_resolver=world_object_resolver,
        ),
        MonsterRecipientStrategy(
            observed_event_registry=observed_event_registry,
            player_audience_query=player_audience_query,
            physical_map_repository=physical_map_repository,
            world_object_to_player_resolver=world_object_resolver,
            monster_repository=monster_repository,
        ),
        CombatRecipientStrategy(
            observed_event_registry=observed_event_registry,
            world_object_to_player_resolver=world_object_resolver,
            hit_box_repository=hit_box_repository,
        ),
        SkillRecipientStrategy(
            observed_event_registry=observed_event_registry,
            skill_loadout_repository=skill_loadout_repository,
            skill_deck_progress_repository=skill_deck_progress_repository,
        ),
        *(
            (
                SpotGraphRecipientStrategy(
                    observed_event_registry=observed_event_registry,
                    spot_graph_repository=spot_graph_repository,
                    player_status_repository=player_status_repository,
                ),
                ItemUseRecipientStrategy(
                    observed_event_registry=observed_event_registry,
                    spot_graph_repository=spot_graph_repository,
                    player_status_repository=player_status_repository,
                ),
                SpotGraphSpeechRecipientStrategy(
                    observed_event_registry=observed_event_registry,
                    spot_graph_repository=spot_graph_repository,
                    player_status_repository=player_status_repository,
                    sound_propagation_service=SoundPropagationService(),
                ),
            )
            if spot_graph_repository is not None
            else ()
        ),
        SpeechRecipientStrategy(
            observed_event_registry=observed_event_registry,
            player_status_repository=player_status_repository,
        ),
        DefaultRecipientStrategy(
            observed_event_registry=observed_event_registry,
            player_audience_query=player_audience_query,
            world_object_to_player_resolver=world_object_resolver,
            spot_graph_repository=spot_graph_repository,
        ),
    ]
    return ObservationRecipientResolver(
        strategies=strategies,
        player_status_repository=player_status_repository,
        player_life_query=player_life_query,
    )
