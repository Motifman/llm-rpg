from enum import Enum


class TrapTriggerTypeEnum(Enum):
    ON_ENTRY = "ON_ENTRY"        # スポット進入時に発動
    ON_INTERACT = "ON_INTERACT"  # オブジェクト操作時に発動
