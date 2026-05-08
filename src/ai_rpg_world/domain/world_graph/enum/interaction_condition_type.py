from enum import Enum

class InteractionConditionTypeEnum(Enum):
    ALWAYS = "ALWAYS"
    HAS_ITEM = "HAS_ITEM"
    OBJECT_STATE = "OBJECT_STATE"
    FLAG_SET = "FLAG_SET"
    # 脱出ゲーム拡張
    PLAYERS_AT_SPOT = "PLAYERS_AT_SPOT"
    PREPARED_ACTION = "PREPARED_ACTION"
    PUZZLE_INPUT_MATCH = "PUZZLE_INPUT_MATCH"
    HAS_ITEMS = "HAS_ITEMS"
    # Phase 4-A: acting item instance の state を判定する。
    # 例: 「use_item 対象 instance が lit=true なら interaction 成立」
    ITEM_INSTANCE_STATE = "ITEM_INSTANCE_STATE"
    # Phase 4-B: target item instance (作用される側) の state を判定する。
    # 例: 「修理キットを錆びた剣に使う」の precondition で剣側の rusty=true を要求。
    TARGET_ITEM_INSTANCE_STATE = "TARGET_ITEM_INSTANCE_STATE"
