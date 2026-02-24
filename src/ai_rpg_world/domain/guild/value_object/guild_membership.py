from dataclasses import dataclass
from datetime import datetime

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole


@dataclass(frozen=True)
class GuildMembership:
    """ギルドメンバーシップの値オブジェクト

    役職に応じ「クエスト承認」等の権限は GuildRole で判定する。
    """
    player_id: PlayerId
    role: GuildRole
    joined_at: datetime
    contribution_points: int = 0

    def __post_init__(self):
        if self.contribution_points < 0:
            raise ValueError("contribution_points must be non-negative")

    def can_approve_quest(self) -> bool:
        """クエスト承認権限（オフィサー以上）"""
        return self.role in (GuildRole.LEADER, GuildRole.OFFICER)

    def can_invite_member(self) -> bool:
        """メンバー招待権限（オフィサー以上）"""
        return self.role in (GuildRole.LEADER, GuildRole.OFFICER)

    def can_change_role(self) -> bool:
        """役職変更権限（オフィサー以上）"""
        return self.role in (GuildRole.LEADER, GuildRole.OFFICER)

    def can_deposit_to_bank(self) -> bool:
        """金庫入金権限（メンバー全員）"""
        return True

    def can_withdraw_from_bank(self) -> bool:
        """金庫出金権限（オフィサー以上）"""
        return self.role in (GuildRole.LEADER, GuildRole.OFFICER)
