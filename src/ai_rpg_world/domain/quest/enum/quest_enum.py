from enum import Enum


class QuestStatus(Enum):
    """クエスト状態"""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    OPEN = "open"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QuestScopeType(Enum):
    """クエストの公開範囲（TradeScope に倣う）"""
    PUBLIC = "public"
    GUILD_MEMBERS = "guild_members"
    DIRECT = "direct"


class QuestObjectiveType(Enum):
    """クエスト目標の種別"""
    KILL_MONSTER = "kill_monster"
    KILL_PLAYER = "kill_player"
    REACH_SPOT = "reach_spot"
    REACH_LOCATION = "reach_location"  # スポット内の特定ロケーション（target_id=location_id, target_id_secondary=spot_id）
    TALK_TO_NPC = "talk_to_npc"
    OBTAIN_ITEM = "obtain_item"
    TAKE_FROM_CHEST = "take_from_chest"
