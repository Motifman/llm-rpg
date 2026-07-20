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
    # Phase 4-D-1: プレイヤー状態 (needs / HP) を判定する precondition。
    # アイテムを使う前提として「空腹なときだけ」「HP が低いときだけ」など
    # プレイヤー側の状況を組み合わせるために使う。境界条件は名前と一致:
    PLAYER_NEED_AT_LEAST = "PLAYER_NEED_AT_LEAST"  # need.value >= need_threshold
    PLAYER_HP_RATIO_BELOW = "PLAYER_HP_RATIO_BELOW"  # hp.percentage < hp_ratio (strict <)
    PLAYER_HP_RATIO_AT_LEAST = "PLAYER_HP_RATIO_AT_LEAST"  # hp.percentage >= hp_ratio
    # Phase 4-D-2: プレイヤー個別の自由 state (PlayerStatusAggregate.state) を判定。
    # 「変装中のプレイヤーだけ NPC が反応を変える」「呪いを受けてる時だけ祭壇が
    # 光る」など、Phase 4-D-1 (HP/needs) では拾えない自由フィールドの判定用。
    PLAYER_STATE_IS = "PLAYER_STATE_IS"
    # PR4 (v2 行動制限): 時間帯 / 天候による interaction 制限。
    # シナリオで「夜は釣りできない」「嵐の日は沖の釣り場へ行けない」のような
    # 物理的・時間的制約を宣言できる。
    # _IS は「該当 phase / weather のときだけ実行可能」、
    # _IS_NOT は「該当しないときだけ実行可能」(否定形)。
    TIME_OF_DAY_IS = "TIME_OF_DAY_IS"
    TIME_OF_DAY_IS_NOT = "TIME_OF_DAY_IS_NOT"
    WEATHER_IS = "WEATHER_IS"
    WEATHER_IS_NOT = "WEATHER_IS_NOT"
    # 備蓄プール (stock pool): object.state の (stock / stock_capacity /
    # stock_tick / stock_refill_interval) から現在備蓄を lazy に算出し、
    # required_quantity 以上あるときだけ interaction を許可する。採取源が
    # 「一度に取れる量 / 備蓄量 / 再生間隔」を持つモデル用 (毎 tick 更新せず、
    # アクセス時に経過 tick から再生を計算する)。
    OBJECT_STOCK_AT_LEAST = "OBJECT_STOCK_AT_LEAST"
