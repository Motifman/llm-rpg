"""観測テキスト（プローズ＋構造化）を生成するフォーマッタ実装"""

from typing import Any, Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import IObservationFormatter
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.conversation_formatter import (
    ConversationObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.quest_formatter import (
    QuestObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.shop_formatter import (
    ShopObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.trade_formatter import (
    TradeObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.sns_formatter import (
    SnsObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.guild_formatter import (
    GuildObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.harvest_formatter import (
    HarvestObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.monster_formatter import (
    MonsterObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.combat_formatter import (
    CombatObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.skill_formatter import (
    SkillObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.world_formatter import (
    WorldObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.player_formatter import (
    PlayerObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.pursuit_formatter import (
    PursuitObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.repository.sns_user_repository import UserRepository
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
    from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.skill.repository.skill_repository import SkillSpecRepository


class ObservationFormatter(IObservationFormatter):
    """
    イベント＋配信先を観測テキスト（プローズ文と構造化 dict）に変換する。
    仕様の「観測内容（例）」に基づく。名前解決は任意のリポジトリで行う。
    """

    def __init__(
        self,
        spot_repository: Optional["SpotRepository"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
        item_spec_repository: Optional["ItemSpecRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        monster_repository: Optional["MonsterRepository"] = None,
        skill_spec_repository: Optional["SkillSpecRepository"] = None,
        sns_user_repository: Optional["UserRepository"] = None,
    ) -> None:
        self._name_resolver = ObservationNameResolver(
            spot_repository=spot_repository,
            player_profile_repository=player_profile_repository,
            item_spec_repository=item_spec_repository,
            item_repository=item_repository,
            shop_repository=shop_repository,
            guild_repository=guild_repository,
            monster_repository=monster_repository,
            skill_spec_repository=skill_spec_repository,
            sns_user_repository=sns_user_repository,
        )
        self._context = ObservationFormatterContext(
            name_resolver=self._name_resolver,
            item_repository=item_repository,
        )
        self._formatters = [
            ConversationObservationFormatter(self._context),
            QuestObservationFormatter(self._context),
            ShopObservationFormatter(self._context),
            TradeObservationFormatter(self._context),
            SnsObservationFormatter(self._context),
            GuildObservationFormatter(self._context),
            HarvestObservationFormatter(self._context),
            MonsterObservationFormatter(self._context),
            CombatObservationFormatter(self._context),
            SkillObservationFormatter(self._context),
            WorldObservationFormatter(self._context),
            PlayerObservationFormatter(self._context),
            PursuitObservationFormatter(self._context),
        ]

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
        attention_level: Optional[AttentionLevel] = None,
    ) -> Optional[ObservationOutput]:
        """指定プレイヤー向けの観測出力を生成。attention_level に応じてスキップする。"""
        output: Optional[ObservationOutput] = None
        for formatter in self._formatters:
            output = formatter.format(event, recipient_player_id)
            if output is not None:
                break
        return self._apply_attention_filter(output, attention_level)

    def _apply_attention_filter(
        self,
        output: Optional[ObservationOutput],
        attention_level: Optional[AttentionLevel],
    ) -> Optional[ObservationOutput]:
        if output is None:
            return None
        if attention_level is None or attention_level == AttentionLevel.FULL:
            return output
        if attention_level == AttentionLevel.FILTER_SOCIAL:
            if output.observation_category == "social":
                return None
        if attention_level == AttentionLevel.IGNORE:
            if output.observation_category != "self_only":
                return None
        return output
