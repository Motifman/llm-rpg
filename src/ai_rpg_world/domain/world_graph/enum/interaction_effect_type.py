from enum import Enum

class InteractionEffectTypeEnum(Enum):
    GIVE_ITEM = "GIVE_ITEM"
    REMOVE_ITEM = "REMOVE_ITEM"
    CHANGE_OBJECT_STATE = "CHANGE_OBJECT_STATE"
    REVEAL_OBJECT = "REVEAL_OBJECT"
    REVEAL_SUB_LOCATION = "REVEAL_SUB_LOCATION"
    SET_FLAG = "SET_FLAG"
    SHOW_MESSAGE = "SHOW_MESSAGE"
    # 脱出ゲーム拡張
    APPLY_DAMAGE = "APPLY_DAMAGE"
    APPLY_STATUS_EFFECT = "APPLY_STATUS_EFFECT"
    TELEPORT_ENTITY = "TELEPORT_ENTITY"
    CHANGE_ATMOSPHERE = "CHANGE_ATMOSPHERE"
    COMBINE_ITEMS = "COMBINE_ITEMS"
    # 動的接続
    CREATE_CONNECTION = "CREATE_CONNECTION"
    DESTROY_CONNECTION = "DESTROY_CONNECTION"
    # passage（壁/扉/障壁）の状態遷移
    CHANGE_PASSAGE_STATE = "CHANGE_PASSAGE_STATE"
    # 欲求操作
    SATISFY_NEED = "SATISFY_NEED"
    # 動的世界 — 経時劣化/再生で使う「effect 発火時の tick を object.state に記録」
    RECORD_OBJECT_STATE_TICK = "RECORD_OBJECT_STATE_TICK"
    # Phase 4-A: per-instance item state を操作する effect。
    # acting item instance (use_item の対象 instance) を target にする。
    CHANGE_ITEM_INSTANCE_STATE = "CHANGE_ITEM_INSTANCE_STATE"
    RECORD_ITEM_INSTANCE_STATE_TICK = "RECORD_ITEM_INSTANCE_STATE_TICK"
    # Phase 4-B: cross-instance interaction で「使う側 (acting)」と
    # 「使われる側 (target)」を区別する。target_item_instance_id で
    # 渡された 2 番目の instance を操作する。
    CHANGE_TARGET_ITEM_INSTANCE_STATE = "CHANGE_TARGET_ITEM_INSTANCE_STATE"
    RECORD_TARGET_ITEM_INSTANCE_STATE_TICK = "RECORD_TARGET_ITEM_INSTANCE_STATE_TICK"
