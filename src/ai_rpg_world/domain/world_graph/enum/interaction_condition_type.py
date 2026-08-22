from enum import Enum

class InteractionConditionTypeEnum(Enum):
    ALWAYS = "ALWAYS"
    HAS_ITEM = "HAS_ITEM"
    OBJECT_STATE = "OBJECT_STATE"
    # object.state の整数値が required_quantity 以上であることを要求する。
    # キー不在・整数以外は 0 とみなし、ScenarioEventCondition と意味を揃える。
    OBJECT_STATE_INT_AT_LEAST = "OBJECT_STATE_INT_AT_LEAST"
    FLAG_SET = "FLAG_SET"
    # 世界フラグがまだ立っていないことを要求する。時限ギミックの解決後に
    # 操作を閉じる用途で、scenario_event の FLAG_NOT_SET と意味を揃える。
    FLAG_NOT_SET = "FLAG_NOT_SET"
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
    PLAYER_GOLD_AT_LEAST = "PLAYER_GOLD_AT_LEAST"  # gold >= gold_threshold
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
    # 対人インタラクション: 行為の対象が「行動不能」(倒れている or 死んでいる)
    # であることを要求する。持ち物を奪う・引きずるなど、相手が抵抗できない
    # 状態でのみ成立する行為のための条件。
    #
    # 「起きて動いている相手からは奪えない」を宣言で書けるようにする。常時
    # スリが成立すると窃盗が作業になって質感が薄れるので、奪う前に倒す必要が
    # 生まれる形にする (設計判断はユーザ確定)。
    TARGET_PLAYER_IS_INCAPACITATED = "TARGET_PLAYER_IS_INCAPACITATED"
    # 対人インタラクション: 対象プレイヤーの所持を見る。``HAS_ITEM`` は行為者の
    # 所持しか見ないので、奪う (take) を書くとこれが要る。相手が持っていない
    # のを内部エラーで落とすと、LLM から見て学習できない失敗になる
    # (「相手はそれを持っていない」は普通に起きる状況である)。
    #
    # 判定する品目は ``target_item_spec_id`` で固定するか、
    # ``item_spec_id_parameter_key`` で ``interaction_parameters`` のキーを
    # 指して実行時に決める。後者は「見えている持ち物から LLM が名指しする」
    # 経路で使う。
    TARGET_HAS_ITEM = "TARGET_HAS_ITEM"
    TARGET_HAS_NO_ITEM = "TARGET_HAS_NO_ITEM"
    # 対象プレイヤーの自由 state を判定する。``PLAYER_STATE_IS`` は行為者しか
    # 見ないので、「crew だけ殺せる」「まだ印が無い相手だけ」を書くには
    # 対象側を見る条件が要る。
    TARGET_PLAYER_STATE_IS = "TARGET_PLAYER_STATE_IS"
    # 場所の明るさによる制限。「暗い場所ならどこでも襲える」を 1 回の宣言で
    # 書くための条件で、特定の部屋に紐付ける代わりに使う。
    #
    # 判定するのは **実効照明** (SpotPerceptionService.compute_effective_lighting)
    # であって spot の静的 atmosphere ではない。屋外の昼夜・悪天候・同席者の
    # 光源まで合成した値を見る。「明るすぎる。誰かに見られる」という意図は
    # 松明を持った同席者が居れば崩れるべきなので、raw では足りない。
    SPOT_LIGHTING_IS = "SPOT_LIGHTING_IS"
    SPOT_LIGHTING_IS_NOT = "SPOT_LIGHTING_IS_NOT"
    # 行為者の現在地による制限。場所は「成立条件のひとつ」であって、行為の
    # 置き場所ではない (設計 doc §3.2)。
    AT_SPOT_IS = "AT_SPOT_IS"
    AT_SPOT_IS_NOT = "AT_SPOT_IS_NOT"
