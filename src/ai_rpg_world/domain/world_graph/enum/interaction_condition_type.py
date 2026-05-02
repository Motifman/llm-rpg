from enum import Enum

class InteractionConditionTypeEnum(Enum):
    ALWAYS = "ALWAYS"
    HAS_ITEM = "HAS_ITEM"
    OBJECT_STATE = "OBJECT_STATE"
    FLAG_SET = "FLAG_SET"
