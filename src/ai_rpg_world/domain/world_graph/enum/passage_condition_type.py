from enum import Enum


class PassageConditionTypeEnum(Enum):
    """スポット間接続の通行条件の種類"""

    ALWAYS = "ALWAYS"
    ITEM_REQUIRED = "ITEM_REQUIRED"
    FLAG_SET = "FLAG_SET"
    PUZZLE_SOLVED = "PUZZLE_SOLVED"
