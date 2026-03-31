from enum import Enum

class DiscoveryConditionTypeEnum(Enum):
    ALWAYS = "ALWAYS"
    SEARCH_COUNT = "SEARCH_COUNT"
    HAS_ITEM = "HAS_ITEM"
    FLAG_SET = "FLAG_SET"
