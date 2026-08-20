"""スポットグラフ用の現在状態スナップショット（LLM プロンプト向け）"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ai_rpg_world.domain.memory.goal.service.stagnation_pressure_band import (
    STAGNATION_PRESSURE_BAND_NONE,
)


# --- 構造化エントリ（UiContextBuilder がラベル付与に使用） ---

@dataclass(frozen=True)
class SpotGraphInteractionEntry:
    action_name: str
    display_label: str
    # prompt 表示専用の前提条件ヒント。tool 解決に使う action_name とは分ける。
    # 例: ("夜不可", "嵐不可") → [fish_deep(夜不可・嵐不可)]
    condition_hints: Tuple[str, ...] = ()
    # prompt 表示専用の「この瞬間に満たしていない理由」。候補自体は残すが、
    # 選べる行動の角括弧からは分けて「いまできない」行に表示する。
    blocking_hints: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SpotGraphConnectionEntry:
    """接続先1件の構造化データ。

    注: フィールド名 `is_passable` は LLM プロンプト・WebSocket/REST レスポンスで
    使われている外部互換のフィールド名なので、ドメイン側の `passage.traversable`
    とは意図的に名前を分けている（リネームすると外部契約が壊れるため温存）。
    """
    destination_spot_id: int
    connection_name: str
    destination_spot_name: str
    is_passable: bool
    passage_condition_text: Optional[str] = None


@dataclass(frozen=True)
class SpotGraphObjectEntry:
    """スポット内オブジェクト1件の構造化データ。"""
    object_id: int
    name: str
    description: str
    interactions: Tuple[SpotGraphInteractionEntry, ...]
    # Phase 4-E: スポット内オブジェクトの可観測な state 値 (扉が開いている、
    # 燭台が点いている など)。プロンプト現在状態に「燭台: lit=True」のように
    # 載せるための入力。スポットに居る全員から見える前提なので絞り込みは無し。
    state: Dict[str, Any] = field(default_factory=dict)
    # 行為者の伏せた条件により、宣言済みの操作が表示からすべて落ちたか。
    # 操作名や件数は持たせない。物体そのものを resolver 候補に残しつつ、
    # 偽装版などの存在をプロンプトへ漏らさないための内部判定だけに使う。
    has_actor_hidden_interactions: bool = False
    # 行為者の**役割や世界の状態**が理由で、宣言済みの操作がすべて落ちたか。
    # 存在層 (幽霊など) が理由の場合は False のままにする。**理由によって
    # 見せてよいものが違う** — 職能違いは伝えてよいが、存在層は伝えると
    # 「生者にだけ見える操作がある」ことを漏らす。
    has_role_hidden_interactions: bool = False
    # 落ちた理由のうち、**変えられない属性**によるぶんの注記。公開された
    # 属性だけが入る。空なら従来どおりの注記に落ちる。
    unreachable_attribute_notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SpotGraphSubLocationEntry:
    """サブロケーション1件の構造化データ。"""
    sub_location_id: int
    name: str
    is_current: bool
    is_hidden: bool


@dataclass(frozen=True)
class SpotGraphWeatherEntry:
    """天候情報の構造化データ。屋外スポットのみ有効。"""
    weather_type: str
    weather_intensity: float
    is_outdoor: bool


@dataclass(frozen=True)
class SpotGraphAtmosphereEntry:
    """雰囲気情報の構造化データ。"""
    lighting: str
    sound_ambient: Optional[str]
    temperature: str
    smell: Optional[str]
    perception_note: Optional[str] = None  # 照明知覚の補足テキスト


@dataclass(frozen=True)
class SpotGraphTimeOfDayEntry:
    """現在時刻 (昼夜サイクルの今のフェーズ) の prompt 用構造化データ。

    シナリオが day_night サイクルを宣言していなければ snapshot.time_of_day は
    None。「現在時刻: 朝」のような行をプロンプトに 1 行足すために使う。
    """
    phase_name: str
    display_text: str
    is_dark: bool


@dataclass(frozen=True)
class SpotGraphTradeOfferEntry:
    """自分宛てに来ている取引の申し出 1 件の表示用データ。

    accept / decline は常時露出なので、**申し出が見えていないと受けようが
    ない** (相手も中身も分からない)。残り手番まで出すのは、放っておくと
    流れることを判断材料にできるようにするため。
    """

    offerer_name: str
    gives_text: str
    asks_text: str
    remaining_ticks: int


@dataclass(frozen=True)
class SpotGraphMerchantPriceEntry:
    """商人の品揃え 1 行の表示用データ。

    ``item_name`` は item_spec の表示名で、シナリオの識別子や int id は
    載せない (設計判断「ラベルから名前へ」)。
    """

    item_name: str
    price: int
    #: 売買ツールが対象を解決するための内部 id。表示には出さない。
    item_spec_id: int = -1


@dataclass(frozen=True)
class SpotGraphMerchantEntry:
    """現在地に居る NPC 商人 1 人の表示用データ。

    ``merchant_id`` は表示には出さず、売買ツールが対象を一意に解決するために
    保持する (PR-3 で使う)。
    """

    merchant_id: int
    name: str
    sells: Tuple[SpotGraphMerchantPriceEntry, ...] = ()
    buys: Tuple[SpotGraphMerchantPriceEntry, ...] = ()


@dataclass(frozen=True)
class SpotGraphInventoryItemEntry:
    """所持アイテム1件の構造化データ。

    quantity > 1 のときは spec が同じ複数 instance を集約表示するが、
    LLM tool (drop_item 等) が単体を指せるよう slot_id と item_instance_id
    も保持する。集約時は代表 instance (最初に発見したスロットの instance)
    の id を載せる。-1 は未設定を表す sentinel。
    """
    item_spec_id: int
    name: str
    quantity: int
    # 代表 instance のスロット番号 (drop_item でスロットを直接指す代替手段)
    slot_id: int = -1
    # 代表 instance の ItemInstanceId (drop_item で対象を一意に指せる)
    item_instance_id: int = -1
    # Phase D-3a: 食料腐敗の表示用フラグ。同 spec でも spoiled 状態が異なる
    # instance は別エントリに集約する想定 (「生の魚 x2」と「生の魚 x1 (腐敗)」
    # を並べて表示するため)。default False で既存呼び出し側に無影響。
    is_spoiled: bool = False
    # 実験 #29 後続: LLM が「これは使えるか」を持ち物リストだけで判断できる
    # よう、ItemType の文字列値 (例: "consumable" / "material" / "tool")
    # を保持する。prompt 側で日本語タグ ((食料) / (素材) / (道具)) に整形して
    # 表示し、ITEM_NOT_CONSUMABLE 失敗 (= 食料じゃないものを食べようとする
    # 誤判断) を減らす。
    # default "" で旧呼び出し側との後方互換を保つ (タグなし表示)。
    item_type: str = ""
    # ItemSpec.description 由来の作者文。非空なら所持品行で分類の定型文より
    # 優先して表示する。空なら従来の item category / type 表示へ縮退する。
    description: str = ""
    # Issue #794 D: item spec 作者文の一般用途ヒント。具体 spot / object 名では
    # なく、所持品欄で「どういう用途か」だけを伝える。空なら非表示。
    usage_hint: str = ""
    # scenario item_specs[].category。ItemType とは別軸の物語上の分類で、
    # 所持品欄の既定文言を決めるためだけに使う。空なら item_type 表示へ
    # フォールバックする。
    category: str = ""
    # item_specs[].interactions から解決した、所持者が知ってよい操作。
    # 物体行と同じ DTO を使い、表示・伏せる判断・待ち理由を二重化しない。
    interactions: Tuple[SpotGraphInteractionEntry, ...] = ()


@dataclass(frozen=True)
class SpotGraphGroundItemEntry:
    """現在地の地面アイテム1件の構造化データ。

    プレイヤーが drop した、またはモンスター死亡時に落とした、シナリオ
    初期配置で置かれたアイテムを、pickup tool が指せるラベル付きで
    プロンプトに載せるために使う。
    """
    item_instance_id: int
    item_spec_id: int
    name: str
    # Phase D-3a: 地面に落ちている食料も腐敗する。表示用フラグ。default False。
    is_spoiled: bool = False


@dataclass(frozen=True)
class SpotGraphNearbyEntityEntry:
    """同スポットにいるエンティティ1件の構造化データ。"""
    entity_id: int
    display_name: str = ""
    # PR #347 後続: PlayerDownedEvent が一度通知された後でも、snapshot からは
    # 「あの人が床に倒れている」が見えないと OFF mode で会話 / 看取り / 通り抜け
    # 判断が破綻する。entity の現在 is_down 状態を snapshot に lift する。
    # status 未解決 (entity が player でない / repo に居ない) なら False。
    is_down: bool = False
    # 同 spot の他 player が終局 DEAD (= 復活不可) か。is_down (蘇生可能) と区別し、
    # 表示を「(死亡している)」に分けるために使う。DEAD が downed と同一表示だと
    # 仲間が蘇生を試み続ける / 死者を救助対象にし続ける (観察: リオ 145 tick) ため。
    is_dead: bool = False
    # PR β (実験 #29 後続): 同 spot の他 player の疲労 tier。
    # ``ok`` / ``tired`` / ``fatigued`` / ``severe`` / ``exhausted`` の 5 段階。
    # nearby_entities の prompt 表示で「(ぐったりしている)」等を出すために使う。
    # 仲間の状態を「常時見えている」モデル: Observation ではなく state として
    # 毎 tick 反映する (#421/#425 のラベル → 名前+状態 設計に対称的)。
    fatigue_level: str = "ok"
    # P-U4 (停滞感の表出・他者): 同 spot の他 player の停滞感バンド。
    # ``none`` / ``light`` / ``strong`` の3段階 (P-U2 の
    # ``resolve_stagnation_pressure_band`` の戻り値と同型)。ゲージ値そのものは
    # 見せず、バンドだけを渡す設計 (docs/memory_system 系の停滞感 UX 判断)。
    # fatigue_level と対称に「常時見えている」state として扱う。
    stagnation_band: str = STAGNATION_PRESSURE_BAND_NONE
    # 行動不能 (is_down / is_dead) の相手が持っているものの表示名。
    #
    # 実 run のボトルネックが背景にある。山頂で仲間が倒れ、その荷物 (狼煙に要る
    # 流木) を回収できずに救助が失敗した。回収の手段を足す前に「誰が何を持った
    # まま倒れているのか」が見えないことを解く。
    #
    # 行動不能の相手についてのみ埋める。起きて動いている相手の持ち物まで常時
    # 見えると窃盗が作業になって質感が薄れるので、奪う前に倒す必要が生まれる
    # 形にする (ユーザ確定)。
    carried_item_names: Tuple[str, ...] = ()
    # **この相手に対して提示する**対人 action の構造化表示。
    #
    # snapshot 単位の 1 本のタプルだと全員の行に同じ一覧が出てしまい、
    # 倒れている相手にしか使えない take が立っている相手の行にも並ぶ
    # (v4 第 3 回 run で take 16 回全失敗の原因)。行ごとに持たせる。
    #
    # 絞り込みに使ってよいのは **その行に既に見えている事実だけ**
    # (is_down / is_dead)。見えていない事実 (役割など) で絞ると、
    # ラベルの有無そのものが情報漏れになる。
    action_entries: Tuple[SpotGraphInteractionEntry, ...] = ()
    # 幽霊が倒れた場所に居るときだけ出す、自分自身の身体を表す行。
    # 行為主体とは別の存在であり、tool の対象には登録しない。
    is_own_fallen_body: bool = False


@dataclass(frozen=True)
class SpotGraphMonsterEntry:
    """同スポットに居るモンスター個体1件の構造化データ。

    LLM プロンプトに「灰色のオオカミ（敵対的・弱っている）」のような形で
    載せ、ラベル付与（M1, M2 等）と targeting に使う。

    可視化方針:
    - `display_name`: モンスターテンプレート名（種族名）
    - `behavior_label`: idle/alert/hostile/fleeing 等を日本語化した短い表記
    - `health_bucket`: 数値 HP は隠し、`healthy`/`wounded`/`dying` の 3 段階に丸める。
      現実世界での観測（姿勢・出血・荒い呼吸）に近づける狙い
    - `appearance`: テンプレート description 由来の見た目。空なら表示しない。
    - `is_dead`: 死体の場合に True。生存個体とは表記を分ける
    """

    monster_id: int
    display_name: str
    behavior_label: str
    health_bucket: str
    appearance: str = ""
    is_dead: bool = False


# --- agent busy 状態 ---

@dataclass(frozen=True)
class SpotGraphAgentStatusEntry:
    """プレイヤーの現在の行動状態 (busy / 中断可能性) を LLM に伝えるための構造化情報。

    travel_to のような multi-tick 行動の途中、agent が「物理的にロックされている」
    ことを snapshot から読み取れるようにする。中断可能 (= 別の重い行動を取ると
    travel をキャンセルして新行動に切り替わる) ことも明示する。
    """
    # 現在 busy 状態にあるか (= multi-tick action の途中)。
    busy: bool = False
    # busy の理由 (人間可読、例: "山頂への移動中")。None なら busy=False のときだけ。
    busy_reason: Optional[str] = None
    # 残り何 tick で busy が終わるか。is_traveling 経由でわかる値。
    remaining_ticks: int = 0
    # busy 中でも「軽い行動」(speech, memo, examine 等) は可能。
    # 「重い行動」(別 travel, interact, use_item, attack) を選ぶと busy が中断され
    # 現在地で停止する。LLM にこの選択肢の存在を伝える。
    interruptible: bool = True


# --- 市場の掲示板 (経済統合 Phase 3) ---

@dataclass(frozen=True)
class SpotGraphMarketRowEntry:
    """板の 1 行を、**見る人が打てる手**の言葉で持つ。

    「売り 3 件 (最安 18G)」ではなく「18G で買える (出品 3 件)」。板に出ている
    売り注文は、見る人にとっては「買える」で、注文の向きと打てる手は逆になる。
    向きのまま持つと、読む側が毎回変換することになり視点が混線する。

    ``buy_price_gold`` が None なら「買えない」。件数は競争の激しさ (4 件も
    出ている = 下げないと売れない) を読む材料になる。
    """

    item_name: str
    buy_price_gold: Optional[int] = None
    listing_count: int = 0
    buyable_quantity: int = 0
    #: この品を売るときに受け取る単価。None なら売れない (買い注文が無い)。
    sell_price_gold: Optional[int] = None
    bid_count: int = 0
    sellable_quantity: int = 0
    #: 直近にこの品が実際に成立した単価。None なら一度も成立していない。
    #: 最良の売り値・買い値は「誰かが望んでいる値」でしかないので、値を付ける
    #: ときの確かな手がかりはこちらになる。
    last_trade_price_gold: Optional[int] = None


@dataclass(frozen=True)
class SpotGraphMarketOwnOrderEntry:
    """自分が板に出している注文 1 件。

    集約表示だけだと、値を変える・取り下げるときに**どの注文を指すのかを
    組み立てられない**。自分のぶんだけは品名と値が見える形で個別に出す。
    """

    item_name: str
    side: str
    quantity: int
    unit_price_gold: int
    is_awaiting_collection: bool = False


# --- スナップショット ---

@dataclass(frozen=True)
class SpotGraphPlayerSnapshotDto:
    """スポットグラフ上のプレイヤー周辺の読み取り専用スナップショット。

    ``own_fatigue_level`` は行動者本人の疲労 tier。``ok`` / ``tired`` /
    ``fatigued`` / ``severe`` / ``exhausted`` の 5 段階で、ui_context_builder が
    身体の状態 section に「重い行動が block されている」等の hint を出すために
    参照する。仲間用の ``SpotGraphNearbyEntityDto.fatigue_level`` の自分版。
    旧構造では ``player_state`` dict に ``fatigue_level`` を入れる構造だったが、
    実際には ``dict(player.state)`` (= 自由 state) しか乗らず、hint が常に空に
    なる silent failure があった。専用 field として明示する。

    ``own_stagnation_band`` は P-U3 (停滞感の表出・自己) 用。行動者本人の
    停滞感バンド (``none`` / ``light`` / ``strong``)。fatigue と同じく
    ui_context_builder の「身体の状態」section で hint に変換される。"""

    current_spot_id: int
    current_spot_name: str
    current_spot_description: str
    travel_status_line: Optional[str]
    # 現在状態を読む本人が、物理的な身体から離れた主体か。
    # 存在状態の説明と身体状態の非表示を同じ事実から導出する。
    viewer_is_departed: bool = False
    # 常時遠景。現在状態の一部として毎ターン再生成され、observation/episode には
    # 流さない。本文には area_id ではなく visible_name/name 由来の prose だけを載せる。
    distant_view_lines: Tuple[str, ...] = ()

    connections: Tuple[SpotGraphConnectionEntry, ...] = ()
    objects: Tuple[SpotGraphObjectEntry, ...] = ()
    sub_locations: Tuple[SpotGraphSubLocationEntry, ...] = ()
    atmosphere: Optional[SpotGraphAtmosphereEntry] = None
    weather: Optional[SpotGraphWeatherEntry] = None
    # 現在時刻 (昼夜フェーズ) — シナリオが day_night を宣言していなければ None
    time_of_day: Optional[SpotGraphTimeOfDayEntry] = None
    nearby_entities: Tuple[SpotGraphNearbyEntityEntry, ...] = ()
    #: 同席者行の見出しで「give_item で渡せる」と案内してよいか。
    #:
    #: 案内文はプロンプト本文なので、ツール定義を組む側の判断が届かない。
    #: シナリオが give_item を無効化した世界で案内だけ残ると、**存在しない
    #: 手段を勧める**ことになる。tend_to_player で実際に起きた形。
    can_give_item: bool = True
    #: 自由 state のキー=値 → (見出し, 呼び名)。宣言の無いキーは載らない。
    #:
    #: engine のキー (``duty=weather``) をプロンプトに出さないため (#892)。
    #: 呼び名の出所はシナリオの宣言で、ここで新しく作らない。
    state_display_names: Mapping[str, Any] = field(default_factory=dict)
    monsters_at_spot: Tuple[SpotGraphMonsterEntry, ...] = ()
    # 経済統合 Phase 1: この世界が商人を宣言しているか。
    #
    # 宣言していない世界では商人節も所持金行も出さない。**空の一覧と
    # 「経済の無い世界」を同じ沈黙に潰さない**ための旗で、宣言した世界では
    # 商人の居ない spot でも不在を明示する。
    economy_declared: bool = False
    # 現在地に居る NPC 商人。economy_declared が False のときは常に空。
    merchants_at_spot: Tuple[SpotGraphMerchantEntry, ...] = ()
    # 行動者本人の所持金。economy_declared が False のときは表示しない。
    own_gold: int = 0
    # 経済統合 Phase 2: 自分宛てに来ている取引の申し出。宣言の無い世界では
    # 常に空で、節ごと出さない。
    incoming_trade_offers: Tuple[SpotGraphTradeOfferEntry, ...] = ()
    # 経済統合 Phase 3: 市場の掲示板。宣言の無い世界では常に False / 空で、
    # 節ごと出さない (既存シナリオの prompt を動かさない)。
    market_declared: bool = False
    # 板がこの場所にあるか。宣言した世界では、無い場所でも不在を明示する
    # (黙って節を消すと「ここには無い」と「まだ見つけていない」が同じ沈黙に
    # 潰れ、板を探して手番を溶かす)。
    market_board_here: bool = False
    # 他人の注文は**常駐させない**。見るには market_view で 1 手番を払う。
    # 無料で最新の板が見える世界では、値を読む巧拙が消える。自分の注文だけは
    # 残す — 外すと預けた品がどこからも見えなくなり、値を変える・取り下げる
    # 手がかりが消える (静かな失敗)。
    market_own_orders: Tuple[SpotGraphMarketOwnOrderEntry, ...] = ()
    inventory_items: Tuple[SpotGraphInventoryItemEntry, ...] = ()
    # 現在地の地面に落ちているアイテム (drop された / モンスター死亡時ドロップ /
    # シナリオ初期配置)。pickup tool が G1, G2 ... ラベルで指せるよう
    # 構造化して保持する。
    ground_items: Tuple[SpotGraphGroundItemEntry, ...] = ()
    ground_item_lines: List[str] = field(default_factory=list)

    # エージェントの欲求状態テキスト
    need_lines: Tuple[str, ...] = ()

    # 欲求そのもの (値オブジェクト)。**表示文とは別に持つ。**
    #
    # 想起の検索語を決めるのに、以前は need_lines を文字列として読み直して
    # 「高い or 危険 を含むか」を見ていた。判定に要る値 (need_type と閾値) は
    # AgentNeed が持っているので、それを渡す。表示の言い回しを変えても検索語が
    # 変わらないようにするため (系統2)。
    need_states: Tuple[Any, ...] = ()

    # 行動者本人の HP 行 (値 + 前 turn からの増減)。空文字は「HP 行を出さない」。
    # need_lines と同じ「身体の状態」section の先頭に描画する。従来は HP が
    # プロンプトに一切出ておらず、エージェントは被弾観測を暗算で積み上げるしか
    # なかった (rolling summary の圧縮で累計がズレる) 問題への対処。
    hp_line: str = ""

    # PR #2 状態異常: 適用中の StatusEffect を読みやすい文字列行に変換したもの。
    # 「出血 (残り 9 tick)」のような表記で LLM に渡し、bandage を探す行動連鎖を
    # 取れるようにする。effects が空のときは () を返す。
    active_effect_lines: Tuple[str, ...] = ()

    # 現在の行動状態 (travel 等の multi-tick action 中か)。busy=False が default。
    agent_status: SpotGraphAgentStatusEntry = field(
        default_factory=SpotGraphAgentStatusEntry
    )

    # 本人の疲労 tier。`ok` / `tired` / `fatigued` / `severe` / `exhausted`。
    # ui_context_builder が「身体の状態」section に
    # 「→ 疲労が限界。travel / attack / interact は実行できない。…」
    # のような操作可能性 hint を出すために参照する。
    # default `ok` は player aggregate が無い経路 (= テスト等) の fallback。
    own_fatigue_level: str = "ok"

    # P-U3 (停滞感の表出・自己): 行動者本人の停滞感バンド。``none`` / ``light``
    # / ``strong`` の3段階。ui_context_builder が「身体の状態」section に
    # 「何かが前に進んでいない気がする」等の hint を出すために参照する。
    # default ``none`` は provider 未配線 / flag OFF の経路の fallback
    # (= 導入前と同じく何も描画しない)。
    own_stagnation_band: str = STAGNATION_PRESSURE_BAND_NONE

    # Phase 4-E: 行動者本人の自由 state (HIDDEN を含む全項目)。
    # 自分自身の内面なので毒・呪い・隠しフラグも本人プロンプトには載せる。
    # 第三者観測には流れない (formatter は他プレイヤー snapshot を作らない設計)。
    player_state: Dict[str, Any] = field(default_factory=dict)
    # 手番を記録する効果が書いた key。表示から外す。`tick` は世界の中に無い
    # 語 (#892) で、生値が出ると読み手はその数字で何も判断できない。
    hidden_player_state_keys: frozenset = field(default_factory=frozenset)

    # 後方互換用の文字列行（formatter のフォールバック用）
    connection_lines: List[str] = field(default_factory=list)
    sub_location_lines: List[str] = field(default_factory=list)
    object_lines: List[str] = field(default_factory=list)
    # 物体名を知らない扱いにするためプロンプト本文へは出さない。LLM が記憶や
    # 目的文から名前を指定したときだけ、「不存在」ではなく暗さを理由として
    # 返すための内部照合に使う。
    dark_hidden_object_names: Tuple[str, ...] = ()
