from enum import Enum


class GuildRole(Enum):
    """ギルド役職（オフィサー以上がクエスト承認可能）"""
    LEADER = "leader"
    OFFICER = "officer"
    MEMBER = "member"
