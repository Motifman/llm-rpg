"""シナリオ読み込み結果のデータクラス。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_effect import ItemEffect
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.death_semantics import DeathSemantics
from ai_rpg_world.domain.trade.value_object.market_reach import MarketReach
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import DayNightCycleDef
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import PlayerOutcomeRule
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import ReactiveObjectStateBinding
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import ReactivePassageBinding
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import SynchronizedActionGroup
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

@dataclass(frozen=True)
class ScenarioMetadata:
    id: str
    title: str
    description: str
    theme: str
    difficulty: str
    estimated_ticks: int
    author: str
    tags: Tuple[str, ...]
    #: LLM 初期文脈用。`description` のネタバレを避け、未プレイ者向けの公開レイヤーだけを書く（任意）。
    llm_public_intro: str = ""
    #: 世界の見取り図をシステムプロンプトに載せるか。
    #:
    #: **既定は載せない。** 初期は閉じている通路を持つシナリオが 11 本あり
    #: (abandoned_hospital は 16 部屋中 10 通路)、無条件に載せると鍵の向こうの
    #: 部屋が最初から見える。探索して見つける、という体験がその世界から消える。
    #:
    #: 秘匿役職ものでは逆に、全体の地図が無いとアリバイの検証ができない。
    #: 「集会室から物資庫は 2 tick かかる」を全員が知っていて初めて、時刻の
    #: 食い違いを突ける。世界によって要否が反転するので宣言にする。
    show_world_map: bool = False
    #: 役割キー → プロンプトに出す呼び名。
    #:
    #: ``crew`` / ``keeper`` は engine 側の識別子で、そのまま出すと #892 に
    #: 反する。**呼び名は世界ごとに違う** (クルー / 村人 / 乗員) ので
    #: シナリオが持つ。宣言の無い役割は人数だけ数えて名前を出さない。
    role_labels: Dict[str, str] = field(default_factory=dict)
    #: LLM の objective section に直接埋め込む「現在のゴール」テキスト。
    #: scenario の win condition を LLM 視点で書き下す (例: 「狼煙を上げて山頂で
    #: 救助される」「廃墟から外へ脱出する」)。空のときは world_runtime 等の
    #: consumer 側で fail-fast する (ハードコード fallback は意図的に置かない:
    #: シナリオごとに勝利条件が違うため、空のまま LLM を回すと別シナリオの
    #: objective が混入する silent failure になる)。
    llm_objective_text: str = ""
    #: 終局結果ごとの観測文型。世界固有の場所や語彙は runtime でなくここに置く。
    player_outcome_messages: Mapping[PlayerOutcomeEnum, str] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ItemSpecDefinition:
    """シナリオ JSON で定義されたアイテム仕様。"""
    string_id: str
    spec_id: ItemSpecId
    name: str
    description: str
    category: str
    is_light_source: bool = False
    # Phase D-2: 食料腐敗。None なら腐らない。値は正の整数 tick (loader でチェック)。
    spoils_after_ticks: Optional[int] = None
    # Phase F: 消費効果。None なら使えない (装備・素材など)。値があれば
    # runtime で ItemType.CONSUMABLE として登録される。複合効果は
    # CompositeItemEffect で表現。
    consume_effect: Optional["ItemEffect"] = None
    # PR β (実験 #29 後続): 疲労回復量。0 (default) なら効果なし。
    # use_item 成功時に PlayerStatusAggregate.recover_fatigue() が呼ばれる。
    fatigue_recovery: int = 0
    # Issue #794 D: item の一般用途。具体的な spot / object 名ではなく、
    # 「どういう用途で、どういう種類の場所が要るか」を作者が書く。
    usage_hint: str = ""


@dataclass(frozen=True)
class InitialItemSpec:
    """シナリオで「プレイヤーに最初から持たせるアイテム」を表す値オブジェクト。

    ItemSpecId に加えて per-instance state を仕込めるようにしたもの (Phase 4-D)。
    state を持たない単純な所持なら空 dict を渡せば、PR #115 までの挙動と同じ。
    state を入れた場合は ItemAggregate.create(state=...) 経由で初期 state を
    持つ instance が生成され、`ITEM_INSTANCE_STATE` precondition や
    reactive binding がそのまま機能する。
    """

    spec_id: ItemSpecId
    state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlayerSpawnConfig:
    """プレイヤー初期配置。

    `initial_state` は Phase 4-D-2 PR 3 で追加。`PlayerStatusAggregate.state`
    に渡せる JSON プリミティブの flat dict (str / int / float / bool / None)。
    シナリオ JSON で `players[].initial_state` を省略すれば空 dict になり、
    PR 1 までの挙動と同じ。
    """
    string_id: str
    player_id: int
    name: str
    spawn_spot_id: SpotId
    initial_items: Tuple[InitialItemSpec, ...]
    initial_state: Mapping[str, Any] = field(default_factory=dict)
    # Phase E: プレイヤー個別のペルソナ文 (system prompt に注入される)。
    # None なら runtime fallback (spawn 名から組み立てる generic persona)。
    # 各プレイヤーの「公開プロフィール + 秘密の動機 + 話し方」を 1 つの
    # text block にまとめて入れる想定。秘密はそのプレイヤーの prompt にしか
    # 入らないので natural な info asymmetry になる。
    persona_prompt: Optional[str] = None
    # 目的層 G6: このプレイヤー個別の初期目的文。goal store の seed に使われる。
    # None なら `metadata.llm_objective_text` (シナリオ共通) へフォールバックする
    # ので、既存シナリオの挙動は変わらない。persona_prompt と同じく、秘密の動機を
    # 含む目的をそのプレイヤーの prompt にだけ入れられる (= 情報の非対称性)。
    objective: Optional[str] = None
    # 目的層 G6: このプレイヤーの初期目的を改訂不可にするか。None なら従来どおり
    # シナリオ全体の性質 (`_scenario_has_goal`) から導出する。明示すればそれが
    # 優先され、「勝敗条件つきシナリオでもこの 1 人だけは立て直せる」が書ける。
    goal_locked: Optional[bool] = None
    # 経済統合 Phase 0: 所持金の初期値。省略すれば 0 で、宣言しないシナリオの
    # 挙動は変わらない。PlayerStatusAggregate への配線は売買ツールを入れる PR
    # の管轄なので、ここでは宣言の保持までを行う。
    initial_gold: int = 0


@dataclass(frozen=True)
class ScenarioWeatherConfig:
    """Spot Graph シナリオ用の軽量天候設定。"""

    enabled: bool
    initial_state: WeatherState
    update_interval_ticks: int
    announce_changes: bool


@dataclass(frozen=True)
class ScenarioDayNightConfig:
    """昼夜サイクル設定 (Phase B-1)。

    シナリオが昼夜の流れを必要としない (常に昼など) 場合は本 config を
    持たない (= ScenarioLoadResult.day_night_config が None)。
    """

    cycle: DayNightCycleDef
    # フェーズ変化時に同スポット内 player へ観測を流すか。サバイバル系
    # シナリオでは true (「夕暮れになった」「夜が明けた」)、パズル単発の
    # 短時間シナリオでは false でもよい。
    announce_changes: bool = True


@dataclass(frozen=True)
class AreaDef:
    """シナリオ JSON で宣言された area 定義。

    area は実行時 state を持たない軽い定義表で、spot のまとまりと遠景知覚の
    単位を表す。`position` は宣言値または所属 spot の重心で解決済み。

    `description` は **作者向けの覚書** で prompt には出さない
    (`metadata.description` と同じ扱い)。遠景に出す文は
    `distant_descriptions[距離帯]` → `visible_name` からの定型文の順で決まる
    (docs/spot_graph_distant_view_design.md)。エージェントに見せたい文を
    ここに書いても表示されない。読まれない理由が書いていなかったため、
    配線漏れと見分けが付かなくなっていた。

    `position_source` も同様に読まれない。`position` が宣言由来か重心算出かを
    記録する派生値で、作者が書くものではない。
    """

    area_id: str
    name: str
    visible_name: str
    prominence: float
    position: Optional[SpotPosition]
    position_source: Optional[str] = None
    description: str = ""
    distant_descriptions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DistantCueSourceDef:
    """遠景に出す動的兆候の発生条件。

    段階2aでは object_state のみ対応する。world_flag / scenario_flag は
    未対応の source.kind として loader 境界で fail-fast する。
    """

    kind: str
    object_id: SpotObjectId
    state_key: str
    equals: Any


@dataclass(frozen=True)
class DistantCueAppearEventDef:
    """動的兆候が false→true になった境界で配る観測の宣言。"""

    message: str
    schedules_turn: bool


@dataclass(frozen=True)
class DistantCueDef:
    """シナリオ JSON で宣言された汎用の遠望可能な兆候。

    signal_fire 固有の概念は持たせず、object state が条件を満たしたときに
    area 由来の遠景候補へ混ぜるための軽い定義表として扱う。
    """

    cue_id: str
    source: DistantCueSourceDef
    origin_area_id: str
    visible_name: str
    prominence: float
    ambient_descriptions: Mapping[str, str] = field(default_factory=dict)
    appear_event: Optional[DistantCueAppearEventDef] = None


@dataclass(frozen=True)
class ScenarioLootTableDefinition:
    """シナリオ JSON で宣言された LootTable 定義 (PR #1 動的 loot)。

    runtime で InMemoryLootTableRepository に詰め直すための薄いラッパ。
    string_id: シナリオ作家が JSON で参照する識別子 (例: "deep_fishing_loot")
    table_id: LootTableId として割り振った内部 id (mapper 経由)
    entries: (item_spec_id, weight, min_quantity, max_quantity) のタプル
    """
    string_id: str
    table_id: int
    name: str
    entries: Tuple["ScenarioLootEntry", ...]


@dataclass(frozen=True)
class ScenarioLootEntry:
    """LootTable の 1 エントリ。"""
    item_spec_id: int
    weight: int
    min_quantity: int = 1
    max_quantity: int = 1


@dataclass(frozen=True)
class ScenarioMerchantPriceEntry:
    """商人の品揃え 1 行 (「この item_spec をこの価格で売る / 買う」)。

    item_spec は読み込み時に int id へ解決済み。価格は 1 以上の整数で、
    無料や負の価格は宣言できない (loader が弾く)。
    """

    item_spec_id: int
    price: int


@dataclass(frozen=True)
class ScenarioMerchantDefinition:
    """シナリオ JSON で宣言された NPC 商人 (経済統合 Phase 0)。

    商人は spot に居る存在として宣言する。同席していないと売買できない、
    という「店の位置が意味を持つ」形にするため、spot 参照を必須にしている。

    string_id: シナリオ作家が JSON で参照する識別子 (例: "gustav")
    merchant_id: mapper の "merchant" 名前空間で割り振った内部 id
    name: 表示名。将来 LLM が商人を名前で指すため、シナリオ全域で一意
    sells: 商人が売る品と売値。空なら買い取り専門の商人
    buys: 商人が買い取る品と買値。空なら売るだけの商人

    同じ item_spec が sells と buys の両方に出るのは正常 (売値と買値の差が
    スプレッドになる)。禁じているのは片側リスト内での重複だけで、そちらは
    どちらの価格が効くか決まらないため。
    """

    string_id: str
    merchant_id: int
    name: str
    spot_id: SpotId
    sells: Tuple[ScenarioMerchantPriceEntry, ...] = ()
    buys: Tuple[ScenarioMerchantPriceEntry, ...] = ()


@dataclass(frozen=True)
class ScenarioMarketInitialOrder:
    """板に最初から並んでいる注文 1 件 (経済統合 Phase 3)。

    出し手は商人にする。板が空だと相場感がゼロから始まり、最初の値付けが
    完全な当てずっぽうになる。商人名義なら数量が有限で補充されないので、
    売れれば自然に板から消え、「取り下げ手のいない注文」が居座らない。

    値は屋台の売り買いとわざとずらす。同じ値だと屋台と板で同じ取引ができて
    しまい、板を経由する理由が消える。

    ``expires_in_ticks`` は**この注文だけの寿命**。書かなければ板ぜんたいの
    既定に従う。run を通して居座る買い注文を 1 件だけ置きたいときに使う —
    買い注文が途中で流れると、そのあとに出た売り注文とすれ違い、交差が
    起きる機会そのものが消える (v3.4 で 6 tick 差で実際に起きた)。
    """

    merchant_id: int
    side: str
    item_spec_id: int
    quantity: int
    unit_price: int
    expires_in_ticks: Optional[int] = None


@dataclass(frozen=True)
class ScenarioMarketConfig:
    """掲示板型の市場の宣言 (経済統合 Phase 3)。

    board_spot_id: 板を置く spot。板は物理的に置かれる物なので必須
    order_expires_in_ticks: 注文が流れるまでの手番数。None なら engine の既定
    initial_orders: 板に最初から並んでいる注文
    reach: 板の届く範囲。既定は板と同じ場所に居るときだけ

    **``reach`` が ``GLOBAL`` でも ``board_spot_id`` は要る。** 届く範囲は
    使い方の話で、板が世界のどこに在るかは物の在り処の話。受け取れなかった品は
    板の足元に置かれるので、在り処が消えると取りに行く先が決まらない。
    """

    board_spot_id: SpotId
    order_expires_in_ticks: Optional[int] = None
    initial_orders: Tuple[ScenarioMarketInitialOrder, ...] = ()
    reach: MarketReach = MarketReach.AT_SPOT


@dataclass(frozen=True)
class ScenarioNeedsConfig:
    """needs 機構のシナリオ別調整値。"""

    starvation_damage_per_tick: int = 0
    #: 空腹の進み方 (tick あたり)。既定は現状維持の +1。
    hunger_per_tick: int = 1
    #: 疲労の自然増加 (tick あたり)。既定は 0 で、行動でのみ増える。
    fatigue_per_tick: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.starvation_damage_per_tick, bool)
            or not isinstance(self.starvation_damage_per_tick, int)
            or self.starvation_damage_per_tick < 0
        ):
            raise ValueError(
                "starvation_damage_per_tick must be a non-negative integer, "
                f"got {self.starvation_damage_per_tick!r}"
            )
        # 空腹だけ 0 を弾く。**0 を通すと「空腹の無い世界」が黙って出来上がる。**
        # 空腹が要らない世界は needs 節ごと書かなければよい (既定は据え置き) ので、
        # 0 は書き間違いの形しか持たない。疲労は既定がそもそも 0 なので許す。
        _require_int(self.hunger_per_tick, name="hunger_per_tick", minimum=1)
        _require_int(self.fatigue_per_tick, name="fatigue_per_tick", minimum=0)


def _require_int(value: object, *, name: str, minimum: int) -> None:
    """整数でない / 真偽値 / 下限未満をまとめて弾く。

    `bool` は `int` の派生なので素直に書くと `True` が 1 として通る。
    「空腹が True ずつ進む世界」を作らせない。
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(
            f"{name} must be an integer >= {minimum}, got {value!r}"
        )


@dataclass(frozen=True)
class ScenarioMonsterTemplate:
    """シナリオ JSON で宣言されたモンスター種別定義 (Phase B-2a)。

    domain `MonsterTemplate` をそのまま保持する薄いラッパ + string_id (作家が
    JSON で参照するための識別子)。runtime で repository に詰める際に
    template_id (int) と string_id の対応も id_mapper に登録する。
    """

    string_id: str
    template: MonsterTemplate


@dataclass(frozen=True)
class ScenarioMonsterSpawnCondition:
    """モンスター出現を環境条件で制御する宣言 (Phase B-2b)。

    すべての軸が AND で合成される。指定が無い軸は常に成立扱い (= 「気にしない」)。
    値が一つでも指定されたら、その軸はマッチしないと spawn しない。

    Attributes:
        day_night_phase_names: 出現を許可する day_night フェーズの name 集合。
            空 tuple なら時間帯は問わない。シナリオ作家は自由命名できるので
            事前検証はせず、実行時に day_night cycle が宣言した phase との
            突合で一致 / 不一致だけ判定する。
        required_flags: ON 状態にあるべき WorldFlag。例: `["high_tide"]` で
            「満潮中のみ出現」を表現。空なら制約なし。
        forbidden_flags: OFF 状態にあるべき WorldFlag。例: `["high_tide"]` で
            「干潮中のみ出現」を表現。空なら制約なし。
        weather_type_names: 許容する WeatherTypeEnum 名 (例: ["STORM"])。
            空なら天候は問わない。
    """

    day_night_phase_names: Tuple[str, ...] = ()
    required_flags: Tuple[str, ...] = ()
    forbidden_flags: Tuple[str, ...] = ()
    weather_type_names: Tuple[str, ...] = ()

    @property
    def is_always(self) -> bool:
        """全軸が空なら「常に成立」(条件付きでない)。"""
        return (
            not self.day_night_phase_names
            and not self.required_flags
            and not self.forbidden_flags
            and not self.weather_type_names
        )


@dataclass(frozen=True)
class ScenarioMonsterPlacement:
    """モンスター個体の配置 (Phase B-2a で導入、B-2b で spawn_condition 拡張)。

    spawn_condition が None (省略) または `is_always == True` のとき:
      → シナリオ起動時に static 配置 (B-2a の挙動)
    spawn_condition がいずれかの軸で条件付きのとき:
      → SpotGraphMonsterSpawnService が tick 毎に条件評価し、満たすときだけ
        spawn (満たさなくなったら despawn) する動的 spawn (B-2b の挙動)

    同 spot に同 template を複数体並べる場合、各 placement が独立スロットになる
    (slot_key は `template@spot#index` を順序保存で生成する想定)。
    """

    template_string_id: str
    spot_string_id: str
    # 同じ spot に複数体置きたい時用に座標を分けられるよう保持。シナリオが省略
    # していれば (0, 0, 0)。spot-graph では座標は behavior の参照点として
    # 使われる程度。
    coordinate_x: int = 0
    coordinate_y: int = 0
    coordinate_z: int = 0
    # spawn_condition が None / is_always なら static 配置。それ以外は動的。
    spawn_condition: Optional[ScenarioMonsterSpawnCondition] = None


@dataclass(frozen=True)
class OngoingConditionDef:
    """進行中の世界フラグと、招集制限・明示的な解決効果。"""

    flag: str
    message: str
    blocks_emergency_button: bool
    resolution: Tuple[InteractionEffect, ...] = ()
    on_meeting_start: Tuple[InteractionEffect, ...] = ()


@dataclass(frozen=True)
class ScenarioLoadResult:
    graph: SpotGraphAggregate
    interiors: Dict[SpotId, SpotInterior]
    win_conditions: Tuple[GameEndCondition, ...]
    lose_conditions: Tuple[GameEndCondition, ...]
    player_spawns: Tuple[PlayerSpawnConfig, ...]
    item_spec_definitions: Tuple[ItemSpecDefinition, ...]
    item_interaction_registry: "ItemInteractionRegistry"
    id_mapper: ScenarioIdMapper
    metadata: ScenarioMetadata
    initial_flags: Tuple[str, ...]
    end_conditions: Tuple[GameEndCondition, ...] = ()
    scenario_events: Tuple[ScenarioEventDef, ...] = ()
    player_outcome_rules: Tuple[PlayerOutcomeRule, ...] = ()
    needs_config: ScenarioNeedsConfig = field(default_factory=ScenarioNeedsConfig)
    #: 人が持つ属性の宣言。**書かないシナリオは空** = 従来どおりの扱い。
    player_attribute_specs: PlayerAttributeSpecs = field(
        default_factory=PlayerAttributeSpecs.empty
    )
    weather_config: Optional[ScenarioWeatherConfig] = None
    day_night_config: Optional[ScenarioDayNightConfig] = None
    reactive_passage_bindings: Tuple[ReactivePassageBinding, ...] = ()
    reactive_object_state_bindings: Tuple[ReactiveObjectStateBinding, ...] = ()
    synchronized_action_groups: Tuple[SynchronizedActionGroup, ...] = ()
    # 対人行為の定義。シナリオ直下に 1 回だけ書き、どこで使えるかは前提条件で
    # 表現する (spot object に紐づけると同じ行為の複数回定義が要るため)。
    player_interactions: Tuple[InteractionDef, ...] = ()
    monster_templates: Tuple[ScenarioMonsterTemplate, ...] = ()
    monster_placements: Tuple[ScenarioMonsterPlacement, ...] = ()
    # この世界では出さないツール。**世界の中身に無いものを出さないため**の宣言。
    #
    # モンスターの居ない世界に ``spot_graph_attack`` が並び続けるのが動機。
    # 対象候補が永久に空なのに毎ターン選択肢に載るので、実 run 007 では
    # インポスターが 3 手を捨てた。会議を宣言しない世界から投票系を落とす
    # のと同じ判断 (#860) だが、あちらは engine 側に条件を書いていた。
    # 何を出さないかは世界ごとに違うので、シナリオが決める。
    #
    # 名前は spot_graph 系ツールの実名で書く。記憶系ツールの露出は実験
    # profile の管轄なので、ここでは扱わない。
    disabled_tools: Tuple[str, ...] = ()
    # 同じ role の当事者同士だけが、互いを仲間として知る宣言。
    # role の生値は prompt へ渡さず、runtime が表示名へ解決する。
    mutually_known_roles: Tuple[str, ...] = ()
    # role ごとの不変な共通知識。個人の persona_prompt とは別に保持し、runtime が
    # 「人物 → 役職」の固定順で連結する。未宣言なら従来の persona_prompt だけを使う。
    role_personas: Mapping[str, str] = field(default_factory=dict)
    # 現在成立している異常を user prompt 末尾へ出す宣言。critical は後続の
    # 会議解除規則が読む分類であり、この段階では保持だけを行う。
    ongoing_conditions: Tuple[OngoingConditionDef, ...] = ()
    # PR #1 動的 loot: scenario JSON で宣言された LootTable 定義群。
    # runtime で InMemoryLootTableRepository に詰めて effect_service に注入する。
    loot_tables: Tuple[ScenarioLootTableDefinition, ...] = ()
    # 遠景知覚の土台: scenario JSON で宣言された area 定義群。
    # 実行時 state を持たないため、SpotGraphAggregate の子集約にはしない。
    areas: Tuple[AreaDef, ...] = ()
    # 遠景知覚の動的兆候: object state などを source とする定義群。
    # 段階2aでは読み込み・検証だけを行い、prompt 反映は段階2bで接続する。
    distant_cues: Tuple[DistantCueDef, ...] = ()
    # 会議機構を使うシナリオかどうか (会議と投票)。宣言の無いシナリオでは
    # 招集も投票も tool として出さず、runtime 側でも拒否する。
    #
    # 既定を False にしているのは、**比較実験の土台を黙って動かさない**ため。
    # #874 で report_body を無条件に出したとき、会議と無関係な
    # survival_island_v4_coop の tool 一覧が 16 → 17 に増え、過去 run との
    # 比較可能性が切れていた。同時行動 (prepare_action) と同じく、宣言した
    # シナリオにだけ出す。
    meeting_enabled: bool = False
    # 死の扱い。宣言が無ければ engine の既定 (蘇生できる世界)。
    death_semantics: DeathSemantics = field(default_factory=DeathSemantics)
    # 会議の調整値。None は既定 (GamePhaseStore のクラス定数) を使う。
    # シナリオごとに変えられないと、機構の確認用に短く回す run で会議 1 回
    # に run の大半を持っていかれる。
    meeting_tick_limit: Optional[int] = None
    meeting_silence_limit_ticks: Optional[int] = None
    meeting_cooldown_ticks: Optional[int] = None
    emergency_buttons_per_player: Optional[int] = None
    # DEAD 後も別位置で手番を持つ世界か。既定無効で比較実験を変えない。
    departed_agents_enabled: bool = False
    # 経済統合 Phase 2: エージェント同士の取引を使う世界か。
    #
    # 商人 (merchants) とは別の宣言にする。商人の居る町でも「人同士の取引は
    # しない」世界はありえるし、逆もある。meeting_enabled と同じく、宣言の
    # 無い世界では取引ツールを出さず、既存 run の tool 一覧を動かさない。
    player_trade_enabled: bool = False
    #: 提案が流れるまでの手番数。None なら engine の既定。
    #:
    #: **世界の広さで決まる値**なのでシナリオが持つ。生産の往復より短いと、
    #: 相手が現物を用意して戻る前に提案が流れ、予約注文が構造的に成立しない
    #: (market_town_v2_trade の初回 run で実際に起きた: 往復 12 手番に対して
    #: 既定 10 手番)。
    player_trade_offer_expires_in_ticks: Optional[int] = None
    # 経済統合 Phase 0: この世界に居る NPC 商人の宣言。
    #
    # disabled_tools (負の宣言) と対になる**正の宣言**で、商人の居ない世界では
    # 空 tuple のままになる。売買ツールの露出判断はこの宣言を見る (PR-3)。
    # 既定を空 tuple にしているのは、既存シナリオを 1 つも書き換えずに
    # 過去 run との比較可能性を保つため。
    merchants: Tuple[ScenarioMerchantDefinition, ...] = ()
    # 経済統合 Phase 3: 掲示板型の市場。宣言の無い世界には板が無い。
    market: Optional[ScenarioMarketConfig] = None
