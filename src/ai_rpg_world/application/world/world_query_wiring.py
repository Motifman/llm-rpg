"""WorldQueryService の wiring。PlayerLocationQueryService・SpotContextQueryService 等を明示的に注入する。

create_llm_agent_wiring 等に world_query_service を渡す際、本モジュールの create_world_query_service を用いて
構築すると、依存関係が明示的になる。
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.repository.transition_policy_repository import ITransitionPolicyRepository
from ai_rpg_world.application.common.interfaces import IPlayerAudienceQueryPort
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.social.services.sns_mode_session_service import (
        SnsModeSessionService,
    )
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
    from ai_rpg_world.application.conversation.services.conversation_command_service import (
        ConversationCommandService,
    )
    from ai_rpg_world.application.trade.services.personal_trade_query_service import (
        PersonalTradeQueryService,
    )
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.player.repository.player_inventory_repository import (
        PlayerInventoryRepository,
    )
    from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
    from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
    from ai_rpg_world.domain.skill.repository.skill_repository import (
        SkillDeckProgressRepository,
        SkillLoadoutRepository,
    )
    from ai_rpg_world.domain.world.service.world_time_config_service import (
        WorldTimeConfigService,
    )


def create_world_query_service(
    *,
    player_status_repository: PlayerStatusRepository,
    player_profile_repository: PlayerProfileRepository,
    physical_map_repository: PhysicalMapRepository,
    spot_repository: SpotRepository,
    connected_spots_provider: IConnectedSpotsProvider,
    monster_repository: Optional["MonsterRepository"] = None,
    transition_policy_repository: Optional[ITransitionPolicyRepository] = None,
    transition_condition_evaluator: Optional[TransitionConditionEvaluator] = None,
    player_inventory_repository: Optional["PlayerInventoryRepository"] = None,
    item_repository: Optional["ItemRepository"] = None,
    conversation_command_service: Optional["ConversationCommandService"] = None,
    skill_loadout_repository: Optional["SkillLoadoutRepository"] = None,
    skill_deck_progress_repository: Optional["SkillDeckProgressRepository"] = None,
    game_time_provider: Optional["GameTimeProvider"] = None,
    world_time_config_service: Optional["WorldTimeConfigService"] = None,
    quest_repository: Optional["QuestRepository"] = None,
    guild_repository: Optional["GuildRepository"] = None,
    shop_repository: Optional["ShopRepository"] = None,
    personal_trade_query_service: Optional["PersonalTradeQueryService"] = None,
    player_audience_query: Optional[IPlayerAudienceQueryPort] = None,
    sns_mode_session: Optional["SnsModeSessionService"] = None,
) -> WorldQueryService:
    """
    PlayerLocationQueryService・SpotContextQueryService・AvailableMovesQueryService・
    VisibleContextQueryService・PlayerCurrentStateBuilder を構築し、WorldQueryService を返す。

    create_llm_agent_wiring(world_query_service=create_world_query_service(...)) のように使用する。

    Args:
        player_status_repository: プレイヤー状態リポジトリ
        player_profile_repository: プレイヤープロフィールリポジトリ
        physical_map_repository: 物理マップリポジトリ
        spot_repository: スポットリポジトリ
        connected_spots_provider: 接続スポットプロバイダ
        monster_repository: モンスターリポジトリ（省略可）
        transition_policy_repository: ゲートウェイ遷移ポリシー（省略可）
        transition_condition_evaluator: 遷移条件評価器（省略可）
        player_inventory_repository: プレイヤーインベントリリポジトリ（省略可）
        item_repository: アイテムリポジトリ（省略可）
        conversation_command_service: 会話コマンドサービス（省略可）
        skill_loadout_repository: スキルロードアウトリポジトリ（省略可）
        skill_deck_progress_repository: スキルデッキ進行リポジトリ（省略可）
        game_time_provider: ゲーム時間プロバイダ（省略可）
        world_time_config_service: ワールド時間設定サービス（省略可）
        quest_repository: クエストリポジトリ（省略可）
        guild_repository: ギルドリポジトリ（省略可）
        shop_repository: ショップリポジトリ（省略可）
        personal_trade_query_service: 個人取引クエリサービス（省略可）
        player_audience_query: プレイヤーオーディエンスクエリ（省略可、省略時は PlayerAudienceQueryService を自前構築）

    Returns:
        WorldQueryService: 構築済みの WorldQueryService
    """
    audience_query = player_audience_query or PlayerAudienceQueryService(
        player_status_repository=player_status_repository
    )
    return WorldQueryService(
        player_status_repository=player_status_repository,
        player_profile_repository=player_profile_repository,
        physical_map_repository=physical_map_repository,
        spot_repository=spot_repository,
        connected_spots_provider=connected_spots_provider,
        monster_repository=monster_repository,
        transition_policy_repository=transition_policy_repository,
        transition_condition_evaluator=transition_condition_evaluator,
        player_inventory_repository=player_inventory_repository,
        item_repository=item_repository,
        conversation_command_service=conversation_command_service,
        skill_loadout_repository=skill_loadout_repository,
        skill_deck_progress_repository=skill_deck_progress_repository,
        game_time_provider=game_time_provider,
        world_time_config_service=world_time_config_service,
        quest_repository=quest_repository,
        guild_repository=guild_repository,
        shop_repository=shop_repository,
        personal_trade_query_service=personal_trade_query_service,
        player_audience_query=audience_query,
        sns_mode_session=sns_mode_session,
    )


__all__ = ["create_world_query_service"]
