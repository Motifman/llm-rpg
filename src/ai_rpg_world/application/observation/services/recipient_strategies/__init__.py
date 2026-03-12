"""観測配信先解決戦略（イベント型ごとのルール）"""

from ai_rpg_world.application.observation.services.recipient_strategies.default_recipient_strategy import (
    DefaultRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.combat_recipient_strategy import (
    CombatRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.conversation_recipient_strategy import (
    ConversationRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.guild_recipient_strategy import (
    GuildRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.harvest_recipient_strategy import (
    HarvestRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.monster_recipient_strategy import (
    MonsterRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.quest_recipient_strategy import (
    QuestRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.pursuit_recipient_strategy import (
    PursuitRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.shop_recipient_strategy import (
    ShopRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.trade_recipient_strategy import (
    TradeRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.skill_recipient_strategy import (
    SkillRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.speech_recipient_strategy import (
    SpeechRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.sns_recipient_strategy import (
    SnsRecipientStrategy,
)

__all__ = [
    "DefaultRecipientStrategy",
    "ConversationRecipientStrategy",
    "QuestRecipientStrategy",
    "PursuitRecipientStrategy",
    "ShopRecipientStrategy",
    "TradeRecipientStrategy",
    "GuildRecipientStrategy",
    "HarvestRecipientStrategy",
    "MonsterRecipientStrategy",
    "CombatRecipientStrategy",
    "SkillRecipientStrategy",
    "SpeechRecipientStrategy",
    "SnsRecipientStrategy",
]
