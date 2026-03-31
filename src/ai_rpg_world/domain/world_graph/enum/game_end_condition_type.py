from enum import Enum


class GameEndConditionTypeEnum(str, Enum):
    """脱出・シナリオ用のゲーム終了条件の種類"""

    ALL_AT_SPOT = "ALL_AT_SPOT"
    ANY_AT_SPOT = "ANY_AT_SPOT"
    FLAG_SET = "FLAG_SET"
    TICK_LIMIT = "TICK_LIMIT"
