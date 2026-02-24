from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CreateGuildCommand:
    """ギルド作成コマンド"""
    name: str
    description: str
    creator_player_id: int


@dataclass(frozen=True)
class AddGuildMemberCommand:
    """ギルドメンバー追加コマンド（招待。招待者はオフィサー以上）"""
    guild_id: int
    inviter_player_id: int
    new_member_player_id: int


@dataclass(frozen=True)
class LeaveGuildCommand:
    """ギルド脱退コマンド"""
    guild_id: int
    player_id: int


@dataclass(frozen=True)
class ChangeGuildRoleCommand:
    """ギルド役職変更コマンド（変更者はオフィサー以上）"""
    guild_id: int
    changer_player_id: int
    target_player_id: int
    new_role: str  # "leader" | "officer" | "member"


@dataclass(frozen=True)
class DepositToGuildBankCommand:
    """ギルド金庫入金コマンド（メンバー全員可能）"""
    guild_id: int
    player_id: int
    amount: int


@dataclass(frozen=True)
class WithdrawFromGuildBankCommand:
    """ギルド金庫出金コマンド（オフィサー以上のみ）"""
    guild_id: int
    player_id: int
    amount: int


@dataclass(frozen=True)
class DisbandGuildCommand:
    """ギルド解散コマンド（リーダーのみ）"""
    guild_id: int
    player_id: int
