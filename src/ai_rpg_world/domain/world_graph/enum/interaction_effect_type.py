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
    # Phase 4-D-2: 行動者プレイヤーの自由 state を操作する。
    # 「アイテム使用で buff/curse/変装が付与され、N tick で reactive に解除」
    # のような複合作用に使う。
    CHANGE_PLAYER_STATE = "CHANGE_PLAYER_STATE"
    RECORD_PLAYER_STATE_TICK = "RECORD_PLAYER_STATE_TICK"
    # 採取の累積・枯渇用。state[key] を整数 delta だけインクリメントする
    # (default delta=1)。
    # 例: gather のたびに state["harvest_count"] += 1 を記録 →
    # reactive_binding (OBJECT_STATE_INT_AT_LEAST predicate) で
    # 「N 回採取で永久枯渇」を表現できる。
    # CHANGE_OBJECT_STATE は「上書き」しか出来ないため、現在値を読んで
    # +1 する accumulator semantics を担えない。本 effect が必要。
    INCREMENT_OBJECT_STATE = "INCREMENT_OBJECT_STATE"
    # 備蓄プールを amount 個消費する。現在備蓄を lazy に算出 (経過 tick から
    # 再生) してから減算し、(stock, stock_tick) を object.state に書き戻す。
    # OBJECT_STOCK_AT_LEAST precondition と対で使う。parameters: amount
    # (default 1)。対象は _resolve_target_object と同じ規約で、object_id 指定が
    # あればそれ、無ければ acting object (= interact している採取源自身)。
    # 採取源は自分自身の stock を消費する self-interaction 用途を想定する。
    CONSUME_OBJECT_STOCK = "CONSUME_OBJECT_STOCK"
    # 動的 loot table 抽選。LootTableAggregate.roll() で確率に基づくアイテム
    # 選択を行う。parameters: loot_table_id (string id) + times (default 1)。
    # 結果は GIVE_ITEM と同じ経路で grant される。「沖の釣りで raw_fish が
    # 大体 / たまに何か別のもの」のような不確実性を表現できる。
    GIVE_FROM_LOOT_TABLE = "GIVE_FROM_LOOT_TABLE"
    # PR-F (#710 後続): 「看板」— プレイヤーが自由テキストを書き込める世界
    # オブジェクト。interaction ツールの自由入力 parameters (パズル用に既存)
    # から `text` を読み、書き手名・tick と共に object.state へ上書き保存する。
    # v1 は「最後に書いた 1 枚のみ保持」(上書き式)。
    WRITE_PLAYER_TEXT = "WRITE_PLAYER_TEXT"
    # 上記で書き込まれた自由テキストを object.state から読み出し、
    # 「『本文』 — 書き手名」形式の message を組む (examine 系 action 用)。
    # 未記入なら「何も書かれていない」。SHOW_MESSAGE と同じく messages に
    # 追加するだけで、state は変更しない (読む行為自体は他者に観測されない)。
    SHOW_PLAYER_TEXT = "SHOW_PLAYER_TEXT"
