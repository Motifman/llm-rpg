"""観測配信先をイベントから解決する実装（戦略パターン）"""

from typing import Any, List, Optional, Sequence, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationRecipientResolver,
    IRecipientResolutionStrategy,
)
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


class ObservationRecipientResolver(IObservationRecipientResolver):
    """
    ドメインイベントから観測の配信先プレイヤーID一覧を解決する。
    登録された戦略のうち、supports(event) が True の先頭戦略に委譲し、
    返却リストの重複を除去して返す。
    """

    def __init__(
        self,
        strategies: Sequence[IRecipientResolutionStrategy],
    ) -> None:
        self._strategies = list(strategies)

    def resolve(self, event: Any) -> List[PlayerId]:
        """イベント種別に応じて配信先を返す。観測対象外または未知のイベントは空リスト。"""
        for strategy in self._strategies:
            if strategy.supports(event):
                raw = strategy.resolve(event)
                return self._deduplicate(raw)
        return []

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
    physical_map_repository: PhysicalMapRepository,
    quest_repository: Optional[QuestRepository] = None,
    guild_repository: Optional[GuildRepository] = None,
    shop_repository: Optional[ShopRepository] = None,
    trade_repository: Optional[TradeRepository] = None,
    monster_repository: Optional[MonsterRepository] = None,
    hit_box_repository: Optional[HitBoxRepository] = None,
    skill_loadout_repository: Optional[SkillLoadoutRepository] = None,
    skill_deck_progress_repository: Optional[SkillDeckProgressRepository] = None,
    sns_user_repository: Optional[Any] = None,
) -> IObservationRecipientResolver:
    """
    既存と同様の振る舞いになる Resolver を組み立てる。
    デフォルト戦略と WorldObjectToPlayerResolver を用いる。
    """
    world_object_resolver = WorldObjectToPlayerResolver(physical_map_repository)
    player_audience_query = PlayerAudienceQueryService(
        player_status_repository=player_status_repository,
    )
    strategies: List[IRecipientResolutionStrategy] = [
        ConversationRecipientStrategy(),
        QuestRecipientStrategy(
            player_audience_query=player_audience_query,
            quest_repository=quest_repository,
            guild_repository=guild_repository,
        ),
        ShopRecipientStrategy(
            player_audience_query=player_audience_query,
            shop_repository=shop_repository,
        ),
        TradeRecipientStrategy(trade_repository=trade_repository),
        SnsRecipientStrategy(sns_user_repository=sns_user_repository),
        GuildRecipientStrategy(
            player_audience_query=player_audience_query,
            guild_repository=guild_repository,
        ),
        HarvestRecipientStrategy(world_object_to_player_resolver=world_object_resolver),
        PursuitRecipientStrategy(world_object_to_player_resolver=world_object_resolver),
        MonsterRecipientStrategy(
            player_audience_query=player_audience_query,
            physical_map_repository=physical_map_repository,
            world_object_to_player_resolver=world_object_resolver,
            monster_repository=monster_repository,
        ),
        CombatRecipientStrategy(
            world_object_to_player_resolver=world_object_resolver,
            hit_box_repository=hit_box_repository,
        ),
        SkillRecipientStrategy(
            skill_loadout_repository=skill_loadout_repository,
            skill_deck_progress_repository=skill_deck_progress_repository,
        ),
        SpeechRecipientStrategy(player_status_repository=player_status_repository),
        DefaultRecipientStrategy(
            player_audience_query=player_audience_query,
            world_object_to_player_resolver=world_object_resolver,
        ),
    ]
    return ObservationRecipientResolver(strategies=strategies)
