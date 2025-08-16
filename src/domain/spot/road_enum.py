from enum import Enum


class ConditionType(Enum):
    MIN_LEVEL = "min_level"
    HAS_ITEM = "has_item"
    HAS_GOLD = "has_gold"
    HAS_ROLE = "has_role"
    TIME_RANGE = "time_range"
    WEATHER_CONDITION = "weather_condition"