from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.enum.quest_enum import QuestScopeType
from ai_rpg_world.domain.quest.exception.quest_exception import QuestScopeValidationException


@dataclass(frozen=True)
class QuestScope:
    """クエストの公開範囲を表す値オブジェクト（TradeScope に倣う）"""

    scope_type: QuestScopeType
    target_player_id: Optional[PlayerId] = None
    guild_id: Optional[int] = None  # Phase 3 用。int で統一。

    def __post_init__(self):
        if self.scope_type == QuestScopeType.DIRECT and self.target_player_id is None:
            raise QuestScopeValidationException("DIRECT scope requires target_player_id")
        if self.scope_type == QuestScopeType.GUILD_MEMBERS and self.guild_id is None:
            raise QuestScopeValidationException("GUILD_MEMBERS scope requires guild_id")
        if self.scope_type == QuestScopeType.PUBLIC and (self.target_player_id is not None or self.guild_id is not None):
            raise QuestScopeValidationException("PUBLIC scope must not have target_player_id or guild_id")

    @classmethod
    def public_scope(cls) -> "QuestScope":
        """公開クエストを作成"""
        return cls(scope_type=QuestScopeType.PUBLIC)

    @classmethod
    def direct_scope(cls, target_player_id: PlayerId) -> "QuestScope":
        """特定プレイヤー向けクエストを作成"""
        return cls(scope_type=QuestScopeType.DIRECT, target_player_id=target_player_id)

    @classmethod
    def guild_scope(cls, guild_id: int) -> "QuestScope":
        """ギルドメンバー向けクエストを作成（Phase 3 用）"""
        return cls(scope_type=QuestScopeType.GUILD_MEMBERS, guild_id=guild_id)

    def is_public(self) -> bool:
        return self.scope_type == QuestScopeType.PUBLIC

    def is_direct(self) -> bool:
        return self.scope_type == QuestScopeType.DIRECT

    def is_guild(self) -> bool:
        return self.scope_type == QuestScopeType.GUILD_MEMBERS
