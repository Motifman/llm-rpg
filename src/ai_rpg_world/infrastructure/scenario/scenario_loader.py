"""シナリオ定義 JSON → ドメインオブジェクト変換。

scenario_format_version "1.0" に対応。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    ExpEffect,
    GoldEffect,
    DamageHpEffect,
    HealEffect,
    ItemEffect,
    RecoverMpEffect,
    ReviveEffect,
    SatisfyNeedEffect,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import (
    ReactivePassageBinding,
)
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import (
    ObjectDescriptionVariant,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import (
    ScenarioIdMapper,
    ScenarioIdMappingError,
)


SUPPORTED_FORMAT_VERSIONS = ("1.0",)


class ScenarioLoadError(Exception):
    """シナリオ読み込み中のエラー。"""


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
    #: LLM の objective section に直接埋め込む「現在のゴール」テキスト。
    #: scenario の win condition を LLM 視点で書き下す (例: 「狼煙を上げて山頂で
    #: 救助される」「廃墟から外へ脱出する」)。空のときは world_runtime 等の
    #: consumer 側で fail-fast する (ハードコード fallback は意図的に置かない:
    #: シナリオごとに勝利条件が違うため、空のまま LLM を回すと別シナリオの
    #: objective が混入する silent failure になる)。
    llm_objective_text: str = ""


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
class ScenarioOutcomeResolutionConfig:
    """プレイヤー個別 outcome の解決設定 (Phase E-3b)。

    シナリオが個別 outcome (RESCUED/DEAD/STRANDED) を使わない場合は本 config
    を持たない (= ScenarioLoadResult.outcome_resolution_config が None)。
    存在する場合は PlayerOutcomeResolutionStageService が tick 駆動で
    判定を回す。

    意味論:
    - 各 rescue_at_ticks (= 救助船通過 tick) で、`signal_fire_flag` が立ち、
      かつ summit_spot_id に居る UNRESOLVED プレイヤーは RESCUED に確定
    - `stranded_at_tick` 到達時、まだ UNRESOLVED のプレイヤーは STRANDED に確定
    - DEAD は別経路 (PlayerDownedOutcomeHandler) で確定する
    """

    rescue_at_ticks: Tuple[int, ...]
    stranded_at_tick: int
    summit_spot_id: SpotId
    signal_fire_flag: str
    # 飢餓ダメージ: HUNGER=max のプレイヤーに毎 tick 与える HP ダメージ。
    # 0 で無効。サバイバル系シナリオの緊張感を JSON で調整可能にする。
    # 1 = 元の挙動 (#306 hardcoded)、2 = 約 50 tick (= ~2 day) で 100→0。
    starvation_damage_per_tick: int = 1

    def __post_init__(self) -> None:
        # 値オブジェクトの不変条件は constructor 層でも保証する
        # (code-review HIGH 対応)。loader だけの validation だと
        # `ScenarioOutcomeResolutionConfig(... starvation_damage_per_tick=-999)`
        # のような直接構築で不正値が通ってしまう。
        if self.starvation_damage_per_tick < 0:
            raise ValueError(
                "starvation_damage_per_tick must be non-negative, "
                f"got {self.starvation_damage_per_tick}"
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
class ScenarioLoadResult:
    graph: SpotGraphAggregate
    interiors: Dict[SpotId, SpotInterior]
    win_conditions: Tuple[GameEndCondition, ...]
    lose_conditions: Tuple[GameEndCondition, ...]
    player_spawns: Tuple[PlayerSpawnConfig, ...]
    item_spec_definitions: Tuple[ItemSpecDefinition, ...]
    id_mapper: ScenarioIdMapper
    metadata: ScenarioMetadata
    initial_flags: Tuple[str, ...]
    scenario_events: Tuple[ScenarioEventDef, ...] = ()
    weather_config: Optional[ScenarioWeatherConfig] = None
    day_night_config: Optional[ScenarioDayNightConfig] = None
    reactive_passage_bindings: Tuple[ReactivePassageBinding, ...] = ()
    reactive_object_state_bindings: Tuple[ReactiveObjectStateBinding, ...] = ()
    synchronized_action_groups: Tuple[SynchronizedActionGroup, ...] = ()
    monster_templates: Tuple[ScenarioMonsterTemplate, ...] = ()
    monster_placements: Tuple[ScenarioMonsterPlacement, ...] = ()
    # Phase E-3b: プレイヤー個別 outcome 解決設定 (RESCUED / STRANDED 自動判定)。
    # None なら個別 outcome を使わない (= 既存の集団 win/lose 経路のみ)。
    outcome_resolution_config: Optional[ScenarioOutcomeResolutionConfig] = None
    # PR #1 動的 loot: scenario JSON で宣言された LootTable 定義群。
    # runtime で InMemoryLootTableRepository に詰めて effect_service に注入する。
    loot_tables: Tuple[ScenarioLootTableDefinition, ...] = ()
    # 遠景知覚の土台: scenario JSON で宣言された area 定義群。
    # 実行時 state を持たないため、SpotGraphAggregate の子集約にはしない。
    areas: Tuple[AreaDef, ...] = ()
    # 遠景知覚の動的兆候: object state などを source とする定義群。
    # 段階2aでは読み込み・検証だけを行い、prompt 反映は段階2bで接続する。
    distant_cues: Tuple[DistantCueDef, ...] = ()


class ScenarioLoader:
    """シナリオ定義 JSON を読み込んでドメインオブジェクト群に変換する。"""

    def load_from_file(self, path: Path) -> ScenarioLoadResult:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return self.load_from_dict(raw)

    def load_from_dict(self, raw: Dict[str, Any]) -> ScenarioLoadResult:
        version = raw.get("scenario_format_version")
        if version not in SUPPORTED_FORMAT_VERSIONS:
            raise ScenarioLoadError(
                f"Unsupported scenario_format_version: {version!r}. "
                f"Supported: {SUPPORTED_FORMAT_VERSIONS}"
            )

        mapper = ScenarioIdMapper()

        metadata = self._parse_metadata(raw["metadata"])
        item_defs = self._parse_item_specs(raw.get("item_specs", []), mapper)
        # PR #1: 動的 loot table を先にパース (effect parameter で
        # "loot_table" → id 解決するため、spots/effects のパース時点で
        # mapper に loot_table ns が登録済みである必要)。
        loot_tables = self._parse_loot_tables(raw.get("loot_tables", []), mapper)
        self._pre_register_ids(raw, mapper)
        graph, interiors = self._parse_spots_and_graph(raw, mapper)
        areas = self._parse_areas(raw.get("areas", []), raw.get("spots", []))
        distant_cues = self._parse_distant_cues(
            raw.get("distant_cues", []),
            mapper,
            {area.area_id for area in areas},
        )
        self._parse_connections(raw.get("connections", []), graph, mapper)
        players = self._parse_players(raw.get("players", []), mapper)
        win_conds = self._parse_end_conditions(raw.get("game_end_conditions", {}).get("win", []), mapper)
        lose_conds = self._parse_end_conditions(raw.get("game_end_conditions", {}).get("lose", []), mapper)
        initial_flags = tuple(raw.get("initial_flags", []))
        scenario_events = self._parse_scenario_events(raw.get("scenario_events", []), mapper)
        weather_config = self._parse_weather_config(raw.get("environment", {}))
        day_night_config = self._parse_day_night_config(raw.get("environment", {}))
        monster_templates, monster_placements = self._parse_monsters_block(
            raw.get("monsters"), mapper,
        )
        reactive_bindings = self._parse_reactive_passage_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        reactive_object_bindings = self._parse_reactive_object_state_bindings(
            raw.get("reactive_bindings", {}), mapper,
        )
        sync_groups = self._parse_synchronized_action_groups(
            raw.get("synchronized_action_groups", []), mapper,
        )
        outcome_resolution_config = self._parse_outcome_resolution_config(
            raw.get("outcome_resolution"), mapper,
        )

        return ScenarioLoadResult(
            graph=graph,
            interiors=interiors,
            win_conditions=tuple(win_conds),
            lose_conditions=tuple(lose_conds),
            player_spawns=tuple(players),
            item_spec_definitions=tuple(item_defs),
            id_mapper=mapper,
            metadata=metadata,
            initial_flags=initial_flags,
            scenario_events=scenario_events,
            weather_config=weather_config,
            day_night_config=day_night_config,
            reactive_passage_bindings=reactive_bindings,
            reactive_object_state_bindings=reactive_object_bindings,
            synchronized_action_groups=sync_groups,
            monster_templates=monster_templates,
            monster_placements=monster_placements,
            outcome_resolution_config=outcome_resolution_config,
            loot_tables=loot_tables,
            areas=areas,
            distant_cues=distant_cues,
        )

    def _parse_loot_tables(
        self,
        raw_list: List[Dict[str, Any]],
        mapper: ScenarioIdMapper,
    ) -> Tuple[ScenarioLootTableDefinition, ...]:
        """`loot_tables` block を解析する (PR #1 動的 loot)。

        スキーマ:
          "loot_tables": [
            {
              "id": "deep_fishing_loot",
              "name": "沖の釣り" (optional),
              "entries": [
                {"item_spec": "raw_fish", "weight": 70, "min_quantity": 1, "max_quantity": 2},
                {"item_spec": "shellfish", "weight": 20},
                {"item_spec": "treasure_compass", "weight": 1}
              ]
            }
          ]

        IDs は mapper に "loot_table" 名前空間で登録する。
        """
        out: List[ScenarioLootTableDefinition] = []
        for raw in raw_list:
            string_id = raw.get("id")
            if not isinstance(string_id, str) or not string_id:
                raise ScenarioLoadError(
                    f"loot_tables[*].id is required (got {string_id!r})"
                )
            table_id = mapper.register("loot_table", string_id)
            entries_raw = raw.get("entries", [])
            if not entries_raw:
                raise ScenarioLoadError(
                    f"loot_tables[{string_id!r}].entries must be non-empty"
                )
            entries: List[ScenarioLootEntry] = []
            for index, e in enumerate(entries_raw):
                item_sid = e.get("item_spec")
                if not isinstance(item_sid, str):
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].item_spec required"
                    )
                # PR #1 follow-up: 数値変換失敗 (例: weight="abc") は Python の
                # ValueError として落ちると場所が分からない。シナリオ作家が
                # 直すべき項目を ScenarioLoadError に包んで surface する。
                try:
                    weight = int(e.get("weight", 1))
                    min_q = int(e.get("min_quantity", 1))
                    max_q = int(e.get("max_quantity", 1))
                except (TypeError, ValueError) as exc:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}] has "
                        f"non-integer weight/quantity: {e!r}"
                    ) from exc
                if weight < 0:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].weight "
                        f"must be >= 0 (got {weight})"
                    )
                if min_q < 1:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].min_quantity "
                        f"must be >= 1 (got {min_q})"
                    )
                if max_q < min_q:
                    raise ScenarioLoadError(
                        f"loot_tables[{string_id!r}].entries[{index}].max_quantity "
                        f"({max_q}) must be >= min_quantity ({min_q})"
                    )
                entries.append(ScenarioLootEntry(
                    item_spec_id=mapper.get_int("item_spec", item_sid),
                    weight=weight,
                    min_quantity=min_q,
                    max_quantity=max_q,
                ))
            out.append(ScenarioLootTableDefinition(
                string_id=string_id,
                table_id=table_id,
                name=raw.get("name", ""),
                entries=tuple(entries),
            ))
        return tuple(out)

    def _parse_metadata(self, raw: Dict[str, Any]) -> ScenarioMetadata:
        return ScenarioMetadata(
            id=raw["id"],
            title=raw["title"],
            description=raw.get("description", ""),
            theme=raw.get("theme", ""),
            difficulty=raw.get("difficulty", "medium"),
            estimated_ticks=int(raw.get("estimated_ticks", 100)),
            author=raw.get("author", ""),
            tags=tuple(raw.get("tags", [])),
            llm_public_intro=str(raw.get("llm_public_intro", "") or "").strip(),
            llm_objective_text=str(raw.get("llm_objective_text", "") or "").strip(),
        )

    def _pre_register_ids(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> None:
        """スポット・接続・オブジェクトの全 ID を先行登録する。

        interaction effect が他スポットの接続やオブジェクトを参照する場合に備え、
        実体の解析よりも先に全名前空間の ID を確定させる。
        """
        for spot in raw.get("spots", []):
            mapper.register("spot", spot["id"])
            interior = spot.get("interior", {})
            for obj in interior.get("objects", []):
                mapper.register("object", obj["id"])
            for sub in interior.get("sub_locations", []):
                mapper.register("sub_location", sub["id"])
        for conn in raw.get("connections", []):
            mapper.register("connection", conn["id"])
            if conn.get("is_bidirectional", True):
                mapper.register("connection", conn["id"] + "__reverse")
        for player in raw.get("players", []):
            mapper.register("player", player["id"])

    def _parse_consume_effect(
        self, raw: Any, sid: str,
    ) -> Optional[ItemEffect]:
        """JSON の consume_effect (単一 dict or list) を ItemEffect に変換する。

        対応形式:
        - None / 未指定 → None (使えないアイテム)
        - 単一 dict: `{"type": "heal_hp", "amount": 5}`
        - list: `[{"type": "heal_hp", "amount": 5}, {"type": "satisfy_need", ...}]`
          → CompositeItemEffect でまとめる (1 要素なら単一として返す)
        """
        if raw is None:
            return None
        # 統一して list に正規化
        entries = raw if isinstance(raw, list) else [raw]
        if not entries:
            return None
        parsed = [self._parse_single_consume_effect(e, sid) for e in entries]
        if len(parsed) == 1:
            return parsed[0]
        return CompositeItemEffect(effects=tuple(parsed))

    def _parse_single_consume_effect(
        self, entry: Dict[str, Any], sid: str,
    ) -> ItemEffect:
        """1 つの effect dict を ItemEffect サブクラスに変換する。"""
        if not isinstance(entry, dict):
            raise ValueError(
                f"item '{sid}': consume_effect entry must be a dict, got {type(entry).__name__}"
            )
        etype = entry.get("type")
        if not etype:
            raise ValueError(f"item '{sid}': consume_effect entry missing 'type'")
        if etype == "heal_hp":
            return HealEffect(amount=int(entry["amount"]))
        if etype == "damage_hp":
            return DamageHpEffect(amount=int(entry["amount"]))
        if etype == "recover_mp":
            return RecoverMpEffect(amount=int(entry["amount"]))
        if etype == "gold":
            return GoldEffect(amount=int(entry["amount"]))
        if etype == "exp":
            return ExpEffect(amount=int(entry["amount"]))
        if etype == "satisfy_need":
            need = entry.get("need_type") or entry.get("need_type_name")
            if not need:
                raise ValueError(
                    f"item '{sid}': satisfy_need requires 'need_type' (e.g. 'HUNGER')"
                )
            return SatisfyNeedEffect(
                need_type_name=str(need), amount=int(entry["amount"]),
            )
        if etype == "revive":
            # Issue #621 Phase 3a: ダウン player を蘇生する効果。
            # hp_rate は max_hp に対する比率 (0.0-1.0)。範囲 validation は
            # ReviveEffect.__post_init__ が ItemEffectValidationException で行う。
            if "hp_rate" not in entry:
                raise ValueError(
                    f"item '{sid}': revive requires 'hp_rate' (e.g. 0.4)"
                )
            return ReviveEffect(hp_rate=float(entry["hp_rate"]))
        raise ValueError(
            f"item '{sid}': unknown consume_effect type '{etype}' "
            "(expected: heal_hp / damage_hp / recover_mp / gold / exp / satisfy_need / revive)"
        )

    def _parse_item_specs(
        self, items_raw: List[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> List[ItemSpecDefinition]:
        defs: List[ItemSpecDefinition] = []
        for item in items_raw:
            sid = item["id"]
            numeric = mapper.register("item_spec", sid)
            spoils_raw = item.get("spoils_after_ticks")
            spoils_after_ticks: Optional[int] = None
            if spoils_raw is not None:
                # 不正値はシナリオ作家ミスとして boundary で弾く。ItemSpec の
                # __post_init__ でも弾かれるが、ここで明示しておくと loader 段で
                # 早期 fail し、エラー位置が JSON 単位で分かりやすい。
                spoils_after_ticks = int(spoils_raw)
                if spoils_after_ticks <= 0:
                    raise ValueError(
                        f"item '{sid}': spoils_after_ticks must be positive, got {spoils_after_ticks}"
                    )
            consume_effect = self._parse_consume_effect(
                item.get("consume_effect"), sid,
            )
            fatigue_recovery_raw = item.get("fatigue_recovery", 0)
            try:
                fatigue_recovery = int(fatigue_recovery_raw)
            except (TypeError, ValueError):
                raise ValueError(
                    f"item '{sid}': fatigue_recovery must be int, got {fatigue_recovery_raw!r}"
                )
            if fatigue_recovery < 0:
                raise ValueError(
                    f"item '{sid}': fatigue_recovery must be non-negative, got {fatigue_recovery}"
                )
            defs.append(ItemSpecDefinition(
                string_id=sid,
                spec_id=ItemSpecId.create(numeric),
                name=item["name"],
                description=item.get("description", ""),
                category=item.get("category", "GENERAL"),
                is_light_source=item.get("is_light_source", False),
                spoils_after_ticks=spoils_after_ticks,
                consume_effect=consume_effect,
                fatigue_recovery=fatigue_recovery,
            ))
        return defs

    def _parse_spots_and_graph(
        self, raw: Dict[str, Any], mapper: ScenarioIdMapper,
    ) -> Tuple[SpotGraphAggregate, Dict[SpotId, SpotInterior]]:
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        interiors: Dict[SpotId, SpotInterior] = {}

        for spot_raw in raw.get("spots", []):
            sid_str = spot_raw["id"]
            spot_int = mapper.register("spot", sid_str)
            spot_id = SpotId.create(spot_int)

            atmosphere = self._parse_atmosphere(spot_raw.get("atmosphere"))
            parent_str = spot_raw.get("parent_id")
            parent_id = SpotId.create(mapper.get_int("spot", parent_str)) if parent_str else None
            category = SpotCategoryEnum[spot_raw.get("category", "OTHER")]
            position = self._parse_spot_position(sid_str, spot_raw.get("position"))
            area_id = self._parse_spot_area_id(sid_str, spot_raw.get("area_id"))

            node = SpotNode(
                spot_id=spot_id,
                name=spot_raw["name"],
                description=spot_raw["description"],
                category=category,
                parent_id=parent_id,
                interior=None,
                atmosphere=atmosphere,
                is_outdoor=bool(spot_raw.get("is_outdoor", False)),
                position=position,
                area_id=area_id,
            )
            graph.add_spot(node)

            interior_raw = spot_raw.get("interior")
            if interior_raw:
                interiors[spot_id] = self._parse_interior(interior_raw, mapper)
            else:
                interiors[spot_id] = SpotInterior.empty()

        graph.clear_events()
        return graph, interiors

    def _parse_spot_position(self, spot_id: str, raw: Any) -> Optional[SpotPosition]:
        if raw is None:
            return None
        path = f"spots[{spot_id}].position"
        if not isinstance(raw, Mapping):
            raise ScenarioLoadError(f"{path} must be an object with numeric x/y")
        unknown_keys = set(raw) - {"x", "y"}
        if unknown_keys:
            raise ScenarioLoadError(
                f"{path} has unsupported keys: {sorted(unknown_keys)}"
            )
        x = self._parse_position_number(raw.get("x"), f"{path}.x")
        y = self._parse_position_number(raw.get("y"), f"{path}.y")
        return SpotPosition(x=x, y=y)

    def _parse_position_number(self, raw: Any, path: str) -> float:
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ScenarioLoadError(f"{path} must be a number")
        value = float(raw)
        if not isfinite(value):
            raise ScenarioLoadError(f"{path} must be a finite number")
        return value

    def _parse_spot_area_id(self, spot_id: str, raw: Any) -> Optional[str]:
        if raw is None:
            return None
        if not isinstance(raw, str) or not raw.strip():
            raise ScenarioLoadError(f"spots[{spot_id}].area_id must be a non-empty string")
        return raw.strip()

    def _parse_areas(
        self,
        areas_raw: Any,
        spots_raw: Any,
    ) -> Tuple[AreaDef, ...]:
        if areas_raw is None:
            return ()
        if not isinstance(areas_raw, Sequence) or isinstance(areas_raw, (str, bytes)):
            raise ScenarioLoadError("areas must be a list")

        spot_positions_by_area = self._spot_positions_by_area(spots_raw)
        out: List[AreaDef] = []
        seen: set[str] = set()
        for index, raw_area in enumerate(areas_raw):
            if not isinstance(raw_area, Mapping):
                raise ScenarioLoadError(f"areas[{index}] must be an object")
            area_id = raw_area.get("id")
            if not isinstance(area_id, str) or not area_id.strip():
                raise ScenarioLoadError(f"areas[{index}].id must be a non-empty string")
            area_id = area_id.strip()
            if area_id in seen:
                raise ScenarioLoadError(f"areas[{area_id}].id is duplicated")
            seen.add(area_id)

            name = raw_area.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ScenarioLoadError(f"areas[{area_id}].name must be a non-empty string")
            visible_name = raw_area.get("visible_name")
            if not isinstance(visible_name, str) or not visible_name.strip():
                raise ScenarioLoadError(
                    f"areas[{area_id}].visible_name must be a non-empty string"
                )
            prominence = self._parse_prominence(
                raw_area.get("prominence"), f"areas[{area_id}].prominence"
            )

            declared_position = self._parse_area_position(area_id, raw_area.get("position"))
            if declared_position is not None:
                position = declared_position
                position_source = "declared"
            else:
                position = self._area_centroid(spot_positions_by_area.get(area_id, ()))
                position_source = "centroid" if position is not None else None

            distant_descriptions = raw_area.get("distant_descriptions", {})
            if distant_descriptions is None:
                distant_descriptions = {}
            if not isinstance(distant_descriptions, Mapping):
                raise ScenarioLoadError(
                    f"areas[{area_id}].distant_descriptions must be an object"
                )
            out.append(
                AreaDef(
                    area_id=area_id,
                    name=name.strip(),
                    visible_name=visible_name.strip(),
                    prominence=prominence,
                    position=position,
                    position_source=position_source,
                    description=str(raw_area.get("description", "") or ""),
                    distant_descriptions={
                        str(k): str(v) for k, v in distant_descriptions.items()
                    },
                )
            )
        return tuple(out)

    def _parse_area_position(self, area_id: str, raw: Any) -> Optional[SpotPosition]:
        if raw is None:
            return None
        path = f"areas[{area_id}].position"
        if not isinstance(raw, Mapping):
            raise ScenarioLoadError(f"{path} must be an object with numeric x/y")
        unknown_keys = set(raw) - {"x", "y"}
        if unknown_keys:
            raise ScenarioLoadError(
                f"{path} has unsupported keys: {sorted(unknown_keys)}"
            )
        x = self._parse_position_number(raw.get("x"), f"{path}.x")
        y = self._parse_position_number(raw.get("y"), f"{path}.y")
        return SpotPosition(x=x, y=y)

    def _parse_prominence(self, raw: Any, path: str) -> float:
        value = self._parse_position_number(raw, path)
        if not 0.0 <= value <= 1.0:
            raise ScenarioLoadError(f"{path} must be in [0.0, 1.0]")
        return value

    def _parse_distant_cues(
        self,
        raw: Any,
        mapper: ScenarioIdMapper,
        area_ids: set[str],
    ) -> Tuple[DistantCueDef, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ScenarioLoadError("distant_cues must be a list")

        out: List[DistantCueDef] = []
        seen: set[str] = set()
        for index, raw_cue in enumerate(raw):
            if not isinstance(raw_cue, Mapping):
                raise ScenarioLoadError(f"distant_cues[{index}] must be an object")
            cue_id = raw_cue.get("id")
            if not isinstance(cue_id, str) or not cue_id.strip():
                raise ScenarioLoadError(
                    f"distant_cues[{index}].id must be a non-empty string"
                )
            cue_id = cue_id.strip()
            if cue_id in seen:
                raise ScenarioLoadError(f"distant_cues[{cue_id}].id is duplicated")
            seen.add(cue_id)

            source = self._parse_distant_cue_source(cue_id, raw_cue.get("source"), mapper)
            origin_area_id = self._parse_distant_cue_origin_area_id(
                cue_id, raw_cue.get("origin"), area_ids
            )

            visible_name = raw_cue.get("visible_name")
            if not isinstance(visible_name, str) or not visible_name.strip():
                raise ScenarioLoadError(
                    f"distant_cues[{cue_id}].visible_name must be a non-empty string"
                )
            prominence = self._parse_prominence(
                raw_cue.get("prominence"), f"distant_cues[{cue_id}].prominence"
            )
            ambient_descriptions = raw_cue.get("ambient_descriptions", {})
            if ambient_descriptions is None:
                ambient_descriptions = {}
            if not isinstance(ambient_descriptions, Mapping):
                raise ScenarioLoadError(
                    f"distant_cues[{cue_id}].ambient_descriptions must be an object"
                )
            appear_event = self._parse_distant_cue_appear_event(
                cue_id, raw_cue.get("appear_event")
            )

            out.append(
                DistantCueDef(
                    cue_id=cue_id,
                    source=source,
                    origin_area_id=origin_area_id,
                    visible_name=visible_name.strip(),
                    prominence=prominence,
                    ambient_descriptions={
                        str(k): str(v) for k, v in ambient_descriptions.items()
                    },
                    appear_event=appear_event,
                )
            )
        return tuple(out)

    def _parse_distant_cue_appear_event(
        self,
        cue_id: str,
        raw: Any,
    ) -> Optional[DistantCueAppearEventDef]:
        path = f"distant_cues[{cue_id}].appear_event"
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ScenarioLoadError(f"{path} must be an object")
        message = raw.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ScenarioLoadError(f"{path}.message must be a non-empty string")
        schedules_turn = raw.get("schedules_turn")
        if not isinstance(schedules_turn, bool):
            raise ScenarioLoadError(f"{path}.schedules_turn must be bool")
        return DistantCueAppearEventDef(
            message=message.strip(),
            schedules_turn=schedules_turn,
        )

    def _parse_distant_cue_source(
        self,
        cue_id: str,
        raw: Any,
        mapper: ScenarioIdMapper,
    ) -> DistantCueSourceDef:
        path = f"distant_cues[{cue_id}].source"
        if not isinstance(raw, Mapping):
            raise ScenarioLoadError(f"{path} must be an object")
        kind = raw.get("kind")
        if kind != "object_state":
            raise ScenarioLoadError(f"{path}.kind must be object_state")
        object_id_raw = raw.get("object_id")
        if not isinstance(object_id_raw, str) or not object_id_raw.strip():
            raise ScenarioLoadError(f"{path}.object_id must be a non-empty string")
        object_sid = object_id_raw.strip()
        try:
            object_id = SpotObjectId.create(mapper.get_int("object", object_sid))
        except ScenarioIdMappingError as exc:
            raise ScenarioLoadError(
                f"{path}.object_id references unknown object: {object_sid}"
            ) from exc
        state_key = raw.get("state_key")
        if not isinstance(state_key, str) or not state_key.strip():
            raise ScenarioLoadError(f"{path}.state_key must be a non-empty string")
        if "equals" not in raw:
            raise ScenarioLoadError(f"{path}.equals is required")
        equals = raw["equals"]
        if not self._is_json_primitive(equals):
            raise ScenarioLoadError(f"{path}.equals must be a JSON primitive")
        return DistantCueSourceDef(
            kind="object_state",
            object_id=object_id,
            state_key=state_key.strip(),
            equals=equals,
        )

    def _parse_distant_cue_origin_area_id(
        self,
        cue_id: str,
        raw: Any,
        area_ids: set[str],
    ) -> str:
        path = f"distant_cues[{cue_id}].origin"
        if not isinstance(raw, Mapping):
            raise ScenarioLoadError(f"{path} must be an object")
        area_id = raw.get("area_id")
        if not isinstance(area_id, str) or not area_id.strip():
            raise ScenarioLoadError(f"{path}.area_id must be a non-empty string")
        area_id = area_id.strip()
        if area_id not in area_ids:
            raise ScenarioLoadError(f"{path}.area_id references unknown area: {area_id}")
        return area_id

    @staticmethod
    def _is_json_primitive(value: Any) -> bool:
        if value is None or isinstance(value, (str, bool)):
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return isfinite(value)
        return False

    def _spot_positions_by_area(
        self,
        spots_raw: Any,
    ) -> Dict[str, Tuple[SpotPosition, ...]]:
        grouped: Dict[str, List[SpotPosition]] = {}
        if not isinstance(spots_raw, Sequence) or isinstance(spots_raw, (str, bytes)):
            return {}
        for spot in spots_raw:
            if not isinstance(spot, Mapping):
                continue
            area_id = spot.get("area_id")
            if not isinstance(area_id, str) or not area_id.strip():
                continue
            position = self._parse_spot_position(
                str(spot.get("id", "<unknown>")),
                spot.get("position"),
            )
            if position is None:
                continue
            grouped.setdefault(area_id.strip(), []).append(position)
        return {area_id: tuple(positions) for area_id, positions in grouped.items()}

    @staticmethod
    def _area_centroid(positions: Sequence[SpotPosition]) -> Optional[SpotPosition]:
        if not positions:
            return None
        return SpotPosition(
            x=sum(p.x for p in positions) / len(positions),
            y=sum(p.y for p in positions) / len(positions),
        )

    def _parse_atmosphere(self, raw: Optional[Dict[str, Any]]) -> Optional[SpotAtmosphere]:
        if not raw:
            return None
        return SpotAtmosphere(
            lighting=LightingEnum[raw.get("lighting", "BRIGHT")],
            sound_ambient=raw.get("sound_ambient"),
            temperature=TemperatureEnum[raw.get("temperature", "NORMAL")],
            smell=raw.get("smell"),
        )

    def _parse_interior(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> SpotInterior:
        sub_locs = tuple(
            self._parse_sub_location(s, mapper)
            for s in raw.get("sub_locations", [])
        )
        objects = tuple(
            self._parse_spot_object(o, mapper)
            for o in raw.get("objects", [])
        )
        ground_items = ()  # ground_items は runtime で発生するため、シナリオ定義では空
        discoverables = tuple(
            self._parse_discoverable_item(d, mapper)
            for d in raw.get("discoverable_items", [])
        )
        return SpotInterior(
            sub_locations=sub_locs,
            objects=objects,
            ground_items=ground_items,
            discoverable_items=discoverables,
        )

    def _parse_sub_location(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> SubLocation:
        sid = mapper.register("sub_location", raw["id"])
        obj_ids = tuple(
            SpotObjectId.create(mapper.get_int("object", oid))
            for oid in raw.get("accessible_object_ids", [])
            if mapper.contains("object", oid)
        )
        dc = self._parse_discovery_condition(raw.get("discovery_condition"), mapper) if raw.get("discovery_condition") else None
        return SubLocation(
            sub_location_id=SubLocationId.create(sid),
            name=raw["name"],
            description=raw["description"],
            accessible_object_ids=obj_ids,
            is_hidden=bool(raw.get("is_hidden", False)),
            discovery_condition=dc,
        )

    def _parse_spot_object(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> SpotObject:
        oid = mapper.register("object", raw["id"])
        interactions = tuple(
            self._parse_interaction_def(i, mapper) for i in raw.get("interactions", [])
        )
        variants = tuple(
            ObjectDescriptionVariant(
                description=str(v.get("description", "")),
                required_state=v.get("required_state"),
                required_flag=v.get("required_flag"),
            )
            for v in raw.get("description_variants", [])
        )
        unavailable_hint = raw.get("unavailable_hint")
        if unavailable_hint is not None:
            if not isinstance(unavailable_hint, str) or not unavailable_hint.strip():
                raise ScenarioLoadError(
                    f"object {raw.get('id')}.unavailable_hint must be a non-empty string"
                )
        return SpotObject(
            object_id=SpotObjectId.create(oid),
            name=raw["name"],
            description=raw["description"],
            object_type=SpotObjectTypeEnum[raw.get("object_type", "OTHER")],
            state=dict(raw.get("state", {})),
            interactions=interactions,
            description_variants=variants,
            is_visible=bool(raw.get("is_visible", True)),
            unavailable_hint=unavailable_hint,
        )

    def _parse_interaction_def(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionDef:
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy

        preconds = tuple(
            self._parse_interaction_condition(c, mapper)
            for c in raw.get("preconditions", [])
        )
        effects = tuple(
            self._parse_interaction_effect(e, mapper) for e in raw.get("effects", [])
        )
        on_failure_observation = raw.get("on_failure_observation")
        witness_observation_message = raw.get("witness_observation_message")
        if (
            witness_observation_message is not None
            and not isinstance(witness_observation_message, str)
        ):
            raise ScenarioLoadError(
                f"interaction[{raw.get('action_name')!r}].witness_observation_message "
                f"must be a string, got {type(witness_observation_message).__name__}"
            )
        # Phase G #1: witness_policy はオプション、デフォルト SAME_SPOT。
        # JSON で "ACTOR_ONLY" 等を文字列指定 → WitnessPolicy enum に変換。
        # 未知値は ScenarioLoadError で boundary fail (typo を早期検知)。
        witness_policy_raw = raw.get("witness_policy")
        if witness_policy_raw is None:
            witness_policy = WitnessPolicy.SAME_SPOT
        else:
            if not isinstance(witness_policy_raw, str):
                raise ScenarioLoadError(
                    f"interaction[{raw.get('action_name')!r}].witness_policy must be a string, "
                    f"got {type(witness_policy_raw).__name__}"
                )
            try:
                witness_policy = WitnessPolicy(witness_policy_raw)
            except ValueError as exc:
                valid = ", ".join(p.value for p in WitnessPolicy)
                raise ScenarioLoadError(
                    f"interaction[{raw.get('action_name')!r}].witness_policy "
                    f"must be one of {{{valid}}}, got {witness_policy_raw!r}"
                ) from exc
        return InteractionDef(
            action_name=raw["action_name"],
            display_label=raw["display_label"],
            preconditions=preconds,
            effects=effects,
            on_failure_observation=on_failure_observation,
            witness_observation_message=witness_observation_message,
            witness_policy=witness_policy,
        )

    def _parse_interaction_condition(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionCondition:
        item_sid = raw.get("required_item")
        item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
        obj_sid = raw.get("target_object")
        obj_id = SpotObjectId.create(mapper.get_int("object", obj_sid)) if obj_sid else None
        # 脱出ゲーム拡張フィールド
        required_items_raw = raw.get("required_items")
        required_item_spec_ids = None
        if required_items_raw:
            required_item_spec_ids = tuple(
                ItemSpecId.create(mapper.get_int("item_spec", s)) for s in required_items_raw
            )
        return InteractionCondition(
            condition_type=InteractionConditionTypeEnum[raw["condition_type"]],
            target_item_spec_id=item_spec_id,
            target_object_id=obj_id,
            required_state=raw.get("required_state"),
            flag_name=raw.get("flag_name"),
            failure_message=raw.get("failure_message", ""),
            required_player_count=raw.get("required_player_count"),
            prepared_action_id=raw.get("prepared_action_id"),
            puzzle_input_key=raw.get("puzzle_input_key"),
            required_item_spec_ids=required_item_spec_ids,
            required_quantity=self._parse_required_quantity(raw),
            need_type=self._parse_need_type(raw),
            need_threshold=raw.get("need_threshold"),
            hp_ratio=self._parse_hp_ratio(raw),
            # PR4: TIME_OF_DAY_IS{_NOT} / WEATHER_IS{_NOT} 用フィールド。
            # phase / weather_type は単純な文字列で受け取り、ランタイムで
            # 現在値と比較する。boundary 検証は別 PR で (現状 day_night の
            # phase 名はシナリオ宣言依存のため固定値リストを持たない)。
            required_time_of_day_phase=raw.get("required_time_of_day_phase"),
            required_weather_type=raw.get("required_weather_type"),
        )

    @staticmethod
    def _parse_need_type(raw: Dict[str, Any]) -> Optional[str]:
        """`need_type` が指定されていれば NeedType に存在する名前か load 時に検証する。

        ランタイムまで silent に間違いを引きずると「interaction が永久に
        発火しない」silent failure になるので boundary で弾く。
        """
        from ai_rpg_world.domain.player.value_object.agent_need import NeedType

        value = raw.get("need_type")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ScenarioLoadError(
                f"need_type must be a string (got {type(value).__name__})"
            )
        try:
            NeedType(value)
        except ValueError as exc:
            valid = sorted(t.value for t in NeedType)
            raise ScenarioLoadError(
                f"need_type {value!r} is not a known NeedType. Valid values: {valid}"
            ) from exc
        return value

    @staticmethod
    def _parse_hp_ratio(raw: Dict[str, Any]) -> Optional[float]:
        """`hp_ratio` を 0.0..1.0 の範囲で検証する。範囲外は load 時に拒否。"""
        value = raw.get("hp_ratio")
        if value is None:
            return None
        try:
            f = float(value)
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"hp_ratio must be a number (got {value!r})"
            ) from exc
        if not (0.0 <= f <= 1.0):
            raise ScenarioLoadError(
                f"hp_ratio must be in [0.0, 1.0] (got {f})"
            )
        return f

    @staticmethod
    def _parse_required_quantity(raw: Dict[str, Any]) -> int:
        """`required_quantity` を読みつつ `<= 0` は明確に拒否する。

        domain 側で max(1, ...) する設計だが、scenario 作家が `0` を
        書いた場合に「条件無し」と勘違いするのを防ぐため、loader 側で
        早期に弾く。
        """
        if "required_quantity" not in raw:
            return 1
        try:
            value = int(raw["required_quantity"])
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"required_quantity must be a positive integer (got {raw['required_quantity']!r})"
            ) from exc
        if value <= 0:
            raise ScenarioLoadError(
                f"required_quantity must be >= 1 (got {value})"
            )
        return value

    def _parse_interaction_effect(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> InteractionEffect:
        params = dict(raw.get("parameters", {}))
        effect_type_str = raw.get("effect_type", "")
        # Phase 4-E: visibility は parameters dict ではなく first-class 属性で
        # 持つ。トップレベル "visibility" を優先し、過渡期サポートとして
        # parameters["visibility"] からも吸い上げる。両方あったら top-level 優先。
        visibility_raw = raw.get("visibility")
        if visibility_raw is None and "visibility" in params:
            visibility_raw = params.pop("visibility")
        else:
            params.pop("visibility", None)
        visibility: Optional[EffectVisibility] = None
        if isinstance(visibility_raw, EffectVisibility):
            visibility = visibility_raw
        elif isinstance(visibility_raw, str) and visibility_raw:
            try:
                visibility = EffectVisibility(visibility_raw)
            except ValueError:
                # 値の妥当性は runtime 側でも警告ログを出すが、
                # ここは「読み込めなかった」状態を残さず None に倒し
                # 既定値が使われるようにする。
                visibility = None
        # CHANGE_OBJECT_STATE は state_updates を正式名とする。
        # 過去シナリオ互換で new_state が来た場合は正規化して受け入れる。
        # 他の effect (CHANGE_PASSAGE_STATE 等) では new_state は別の意味で
        # 使われるため、CHANGE_OBJECT_STATE 限定で正規化する。
        if (
            effect_type_str == "CHANGE_OBJECT_STATE"
            and "state_updates" not in params
            and "new_state" in params
        ):
            params["state_updates"] = params.pop("new_state")
        if "item_spec" in params:
            params["item_spec_id"] = mapper.get_int("item_spec", params.pop("item_spec"))
        if "target_object" in params:
            params["object_id"] = mapper.get_int("object", params.pop("target_object"))
        if "target_sub_location" in params:
            params["sub_location_id"] = mapper.get_int("sub_location", params.pop("target_sub_location"))
        if "target_connection" in params:
            params["connection_id"] = mapper.get_int("connection", params.pop("target_connection"))
        if "target_spot" in params:
            params["spot_id"] = mapper.get_int("spot", params.pop("target_spot"))
        if "loot_table" in params:
            # PR #1: "loot_table" 文字列 id → numeric loot_table_id へ正規化
            params["loot_table_id"] = mapper.get_int(
                "loot_table", params.pop("loot_table"),
            )
        return InteractionEffect(
            effect_type=InteractionEffectTypeEnum[raw["effect_type"]],
            parameters=params,
            visibility=visibility,
        )

    def _parse_scenario_events(
        self,
        events_raw: Sequence[Dict[str, Any]],
        mapper: ScenarioIdMapper,
    ) -> Tuple[ScenarioEventDef, ...]:
        parsed: list[ScenarioEventDef] = []
        for raw in events_raw:
            observation = raw.get("observation", {})
            if not isinstance(observation, dict):
                observation = {}
            event_id = raw.get("id", "<unnamed>")
            conditions = tuple(
                self._parse_scenario_event_condition(
                    c, mapper, path=f"scenario_event[{event_id}].conditions[{i}]",
                )
                for i, c in enumerate(raw.get("conditions", []))
            )
            effects = tuple(
                self._parse_interaction_effect(e, mapper)
                for e in raw.get("effects", [])
            )
            parsed.append(
                ScenarioEventDef(
                    event_id=str(raw["id"]),
                    trigger=str(raw.get("trigger", "ON_TICK")),
                    once=bool(raw.get("once", True)),
                    conditions=conditions,
                    effects=effects,
                    observation_category=str(observation.get("category", "environment")),
                    recipients=str(observation.get("recipients", "all_players")),
                    target_spot_id=self._optional_spot_id(observation.get("target_spot"), mapper),
                    schedules_turn=bool(observation.get("schedules_turn", True)),
                    breaks_movement=bool(observation.get("breaks_movement", False)),
                    next_event_id=raw.get("next_event_id"),
                    delay_ticks=int(raw.get("delay_ticks", 0)),
                )
            )
        return tuple(parsed)

    def _optional_spot_id(self, value: Any, mapper: ScenarioIdMapper) -> Optional[int]:
        if not value:
            return None
        return mapper.get_int("spot", str(value))

    # 合成条件の糖衣記法: ネストの深い `condition_type: AND/OR/NOT + children`
    # を `all_of` / `any_of` / `not_` のフラットなキーで書けるようにする。
    # 内部 AST (ScenarioEventCondition) は変更しない — load 時に元の形へ
    # 正規化して通常経路に流す。
    _COMPOSITE_SUGAR: Dict[str, str] = {
        "all_of": "AND",
        "any_of": "OR",
        "not_": "NOT",
    }

    def _parse_scenario_event_condition(
        self,
        raw: Dict[str, Any],
        mapper: ScenarioIdMapper,
        *,
        path: str = "condition",
    ) -> ScenarioEventCondition:
        # ---- 糖衣記法を従来形に正規化 ----
        # `all_of: [...]` / `any_of: [...]` / `not_: <cond>` の
        # いずれかが存在すれば `condition_type` + `children` 形に変換する。
        # `condition_type` と糖衣記法が同時にあるのは作家ミスとして拒否。
        sugar_keys = [k for k in self._COMPOSITE_SUGAR if k in raw]
        if sugar_keys:
            if len(sugar_keys) > 1:
                raise ScenarioLoadError(
                    f"{path}: multiple composite shortcuts found "
                    f"({sorted(sugar_keys)}); use only one of all_of/any_of/not_"
                )
            if "condition_type" in raw:
                raise ScenarioLoadError(
                    f"{path}: cannot mix 'condition_type' with composite "
                    f"shortcut '{sugar_keys[0]}'"
                )
            shortcut = sugar_keys[0]
            target_type = self._COMPOSITE_SUGAR[shortcut]
            payload = raw[shortcut]
            if shortcut == "not_":
                # not_ は単一条件を取る。list で書いても 1 要素まで許容するか
                # 迷うところだが、AST が 1 child 想定なので明確に dict 限定。
                if not isinstance(payload, dict):
                    raise ScenarioLoadError(
                        f"{path}: not_ must be a single condition object "
                        f"(got {type(payload).__name__})"
                    )
                children_list = [payload]
            else:
                if not isinstance(payload, list):
                    raise ScenarioLoadError(
                        f"{path}: {shortcut} must be a list "
                        f"(got {type(payload).__name__})"
                    )
                # list 内の各要素も dict であることを保証する。null や文字列が
                # 紛れ込むと再帰呼び出し先で raw KeyError になりエラーが
                # 不親切になるため、ここで早期に shortcut の path 付きで弾く。
                for i, item in enumerate(payload):
                    if not isinstance(item, dict):
                        raise ScenarioLoadError(
                            f"{path}.{shortcut}[{i}] must be a condition object "
                            f"(got {type(item).__name__})"
                        )
                children_list = payload
            children = tuple(
                self._parse_scenario_event_condition(
                    c, mapper, path=f"{path}.{shortcut}[{i}]",
                )
                for i, c in enumerate(children_list)
            )
            return ScenarioEventCondition(condition_type=target_type, children=children)

        ctype = str(raw["condition_type"])
        # 合成条件 (NOT / AND / OR): children を再帰パース
        if ctype in {"NOT", "AND", "OR"}:
            children_raw = raw.get("children", [])
            if not isinstance(children_raw, list):
                raise ScenarioLoadError(
                    f"{path}: {ctype} condition.children must be a list "
                    f"(got {type(children_raw).__name__})"
                )
            children = tuple(
                self._parse_scenario_event_condition(
                    c, mapper, path=f"{path}.children[{i}]",
                )
                for i, c in enumerate(children_raw)
            )
            return ScenarioEventCondition(condition_type=ctype, children=children)
        # leaf 条件
        spot_id = None
        if raw.get("target_spot"):
            spot_id = mapper.get_int("spot", raw["target_spot"])
        object_id = None
        if raw.get("target_object"):
            object_id = mapper.get_int("object", raw["target_object"])
        item_spec_id = None
        if raw.get("required_item"):
            item_spec_id = mapper.get_int("item_spec", raw["required_item"])
        return ScenarioEventCondition(
            condition_type=ctype,
            tick=raw.get("tick"),
            tick_start=raw.get("tick_start"),
            tick_end=raw.get("tick_end"),
            flag_name=raw.get("flag_name"),
            spot_id=spot_id,
            object_id=object_id,
            required_state=raw.get("required_state"),
            item_spec_id=item_spec_id,
            tick_modulo=raw.get("tick_modulo"),
            tick_phase=raw.get("tick_phase"),
            weather_type=raw.get("weather_type"),
            state_key=raw.get("state_key"),
            ticks_offset=raw.get("ticks_offset"),
            # JSON の `true` / `false` 以外（数値の 1 / 文字列 "true" など）は
            # 暗黙の coercion を避けて作家ミスとして弾く。
            treat_missing_as_passed=raw.get("treat_missing_as_passed", False) is True,
            # Phase D-1: PROBABILITY 用。None 許容で他 condition_type では無視
            # される。範囲チェックは ScenarioEventCondition.__post_init__ に任せる。
            probability=(
                float(raw["probability"]) if raw.get("probability") is not None else None
            ),
        )

    def _parse_reactive_passage_bindings(
        self, raw: Dict[str, Any], mapper: ScenarioIdMapper,
    ) -> Tuple[ReactivePassageBinding, ...]:
        """`reactive_bindings.passages` を Passage 用 binding にパースする。

        スキーマ:
          "reactive_bindings": {
            "passages": [
              {
                "target": "<connection_string_id>",
                "predicate": <ScenarioEventCondition tree>,
                "on_true_state": "OPEN",
                "on_false_state": "LOCKED"
              }
            ]
          }
        """
        if not isinstance(raw, dict):
            return ()
        passages_raw = raw.get("passages", [])
        if not isinstance(passages_raw, list):
            raise ScenarioLoadError(
                f"reactive_bindings.passages must be a list "
                f"(got {type(passages_raw).__name__})"
            )
        bindings: list[ReactivePassageBinding] = []
        for i, b in enumerate(passages_raw):
            target = b.get("target")
            if not target:
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].target is required"
                )
            cid = mapper.get_int("connection", target)
            predicate_raw = b.get("predicate")
            if not isinstance(predicate_raw, dict):
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].predicate must be an object"
                )
            predicate = self._parse_scenario_event_condition(
                predicate_raw, mapper,
                path=f"reactive_bindings.passages[{i}].predicate",
            )
            on_true = b.get("on_true_state")
            on_false = b.get("on_false_state")
            if not on_true:
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].on_true_state is required"
                )
            if not on_false:
                raise ScenarioLoadError(
                    f"reactive_bindings.passages[{i}].on_false_state is required"
                )
            apply_to_reverse = bool(b.get("apply_to_reverse", True))
            bindings.append(
                ReactivePassageBinding(
                    target_connection_id=ConnectionId.create(cid),
                    predicate=predicate,
                    on_true_state=str(on_true),
                    on_false_state=str(on_false),
                )
            )
            # bidirectional 接続には自動で逆方向 binding を生やす（既定）。
            # 一方通行で良い場合は apply_to_reverse=false を明示する。
            reverse_str = f"{target}__reverse"
            if apply_to_reverse and mapper.contains("connection", reverse_str):
                rev_cid = mapper.get_int("connection", reverse_str)
                bindings.append(
                    ReactivePassageBinding(
                        target_connection_id=ConnectionId.create(rev_cid),
                        predicate=predicate,
                        on_true_state=str(on_true),
                        on_false_state=str(on_false),
                    )
                )
        return tuple(bindings)

    def _parse_reactive_object_state_bindings(
        self, raw: Dict[str, Any], mapper: ScenarioIdMapper,
    ) -> Tuple[ReactiveObjectStateBinding, ...]:
        """`reactive_bindings.objects` を ReactiveObjectStateBinding にパース。

        スキーマ:
          "reactive_bindings": {
            "objects": [
              {
                "target": "<object_string_id>",
                "predicate": <ScenarioEventCondition tree>,
                "on_true_state_updates": {"k": v, ...},
                "on_false_state_updates": {"k": v, ...}
              }
            ]
          }
        """
        if not isinstance(raw, dict):
            return ()
        objects_raw = raw.get("objects", [])
        if not isinstance(objects_raw, list):
            raise ScenarioLoadError(
                f"reactive_bindings.objects must be a list "
                f"(got {type(objects_raw).__name__})"
            )
        out: list[ReactiveObjectStateBinding] = []
        for i, b in enumerate(objects_raw):
            target = b.get("target")
            if not target:
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].target is required"
                )
            oid = mapper.get_int("object", target)
            predicate_raw = b.get("predicate")
            if not isinstance(predicate_raw, dict):
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].predicate must be an object"
                )
            predicate = self._parse_scenario_event_condition(
                predicate_raw, mapper,
                path=f"reactive_bindings.objects[{i}].predicate",
            )
            on_true = b.get("on_true_state_updates", {})
            on_false = b.get("on_false_state_updates", {})
            if not isinstance(on_true, dict) or not isinstance(on_false, dict):
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].on_true/false_state_updates must be objects"
                )
            # 著者が宣言した観測 narrative (オプショナル)。flip 方向ごとに別文。
            # 例: 採取資源 cooldown reset (false→true) には narrative_on_true=
            # "ベリーの茂みに新しい実が生っている" を渡す。
            narrative_on_true = b.get("narrative_on_true")
            narrative_on_false = b.get("narrative_on_false")
            if narrative_on_true is not None and not isinstance(narrative_on_true, str):
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].narrative_on_true must be a string"
                )
            if narrative_on_false is not None and not isinstance(narrative_on_false, str):
                raise ScenarioLoadError(
                    f"reactive_bindings.objects[{i}].narrative_on_false must be a string"
                )
            out.append(
                ReactiveObjectStateBinding(
                    target_object_id=SpotObjectId.create(oid),
                    predicate=predicate,
                    on_true_state_updates=tuple((k, v) for k, v in on_true.items()),
                    on_false_state_updates=tuple((k, v) for k, v in on_false.items()),
                    narrative_on_true=narrative_on_true,
                    narrative_on_false=narrative_on_false,
                )
            )
        return tuple(out)

    def _parse_synchronized_action_groups(
        self, raw: Any, mapper: ScenarioIdMapper,
    ) -> Tuple[SynchronizedActionGroup, ...]:
        """`synchronized_action_groups` を SynchronizedActionGroup 値オブジェクト
        の tuple にパースする。

        スキーマ:
          [
            {
              "id": "vault_unlock",
              "required_action_ids": ["pull_lever_left", "pull_lever_right"],
              "window_ticks": 2,
              "on_complete": [<InteractionEffect>...],
              "on_timeout": [<InteractionEffect>...],
              "on_prepare_observation_message": "..."
            }
          ]
        """
        if not isinstance(raw, list):
            return ()
        out: list[SynchronizedActionGroup] = []
        for i, g in enumerate(raw):
            if not isinstance(g, dict):
                raise ScenarioLoadError(
                    f"synchronized_action_groups[{i}] must be an object"
                )
            gid = g.get("id")
            if not gid:
                raise ScenarioLoadError(
                    f"synchronized_action_groups[{i}].id is required"
                )
            req = g.get("required_action_ids", [])
            if not isinstance(req, list):
                raise ScenarioLoadError(
                    f"synchronized_action_groups[{i}].required_action_ids must be a list"
                )
            on_complete = tuple(
                self._parse_interaction_effect(e, mapper)
                for e in g.get("on_complete", [])
            )
            on_timeout = tuple(
                self._parse_interaction_effect(e, mapper)
                for e in g.get("on_timeout", [])
            )
            out.append(
                SynchronizedActionGroup(
                    group_id=str(gid),
                    required_action_ids=tuple(str(x) for x in req),
                    window_ticks=int(g.get("window_ticks", 1)),
                    on_complete=on_complete,
                    on_timeout=on_timeout,
                    on_prepare_observation_message=g.get("on_prepare_observation_message"),
                )
            )
        return tuple(out)

    def _parse_outcome_resolution_config(
        self,
        raw: Any,
        mapper: ScenarioIdMapper,
    ) -> Optional[ScenarioOutcomeResolutionConfig]:
        """`outcome_resolution` block を解析する (Phase E-3b)。

        block 未指定なら None を返す (= 個別 outcome を使わない既存挙動を維持)。

        期待形式:
            "outcome_resolution": {
              "rescue_at_ticks": [80, 130],
              "stranded_at_tick": 140,
              "summit_spot": "summit",
              "signal_fire_flag": "signal_fire_lit"
            }
        """
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"outcome_resolution must be an object, got {type(raw).__name__}"
            )
        rescue_ticks_raw = raw.get("rescue_at_ticks", [])
        if not isinstance(rescue_ticks_raw, list):
            raise ScenarioLoadError(
                "outcome_resolution.rescue_at_ticks must be a list of integers"
            )
        # 重複と順序の正規化: int 化して sorted unique。同 tick 2 回宣言は無意味。
        rescue_ticks = tuple(sorted({int(t) for t in rescue_ticks_raw}))
        stranded_raw = raw.get("stranded_at_tick")
        if not isinstance(stranded_raw, int):
            raise ScenarioLoadError(
                "outcome_resolution.stranded_at_tick must be an integer"
            )
        summit_sid = raw.get("summit_spot")
        if not isinstance(summit_sid, str) or not summit_sid:
            raise ScenarioLoadError(
                "outcome_resolution.summit_spot must be a non-empty string spot id"
            )
        summit_spot_id = SpotId.create(mapper.get_int("spot", summit_sid))
        signal_flag = raw.get("signal_fire_flag")
        if not isinstance(signal_flag, str) or not signal_flag:
            raise ScenarioLoadError(
                "outcome_resolution.signal_fire_flag must be a non-empty string"
            )
        # 救助 tick はすべて stranded_at_tick より厳密に小さい必要がある
        # (timeout 後に救助が走るのは矛盾)
        for t in rescue_ticks:
            if t >= stranded_raw:
                raise ScenarioLoadError(
                    f"outcome_resolution.rescue_at_ticks[{t}] must be strictly "
                    f"less than stranded_at_tick ({stranded_raw})"
                )
        # 飢餓ダメージ (オプショナル、既定 1)。負値は不正。
        starv_raw = raw.get("starvation_damage_per_tick", 1)
        if not isinstance(starv_raw, int) or starv_raw < 0:
            raise ScenarioLoadError(
                "outcome_resolution.starvation_damage_per_tick must be a non-negative integer"
            )
        return ScenarioOutcomeResolutionConfig(
            rescue_at_ticks=rescue_ticks,
            stranded_at_tick=stranded_raw,
            summit_spot_id=summit_spot_id,
            signal_fire_flag=signal_flag,
            starvation_damage_per_tick=starv_raw,
        )

    def _parse_day_night_config(
        self, raw: Dict[str, Any],
    ) -> Optional[ScenarioDayNightConfig]:
        """`environment.day_night` を読んで DayNightCycleDef を組み立てる。

        JSON 形式 (シナリオ作家向け契約):
        ```
        "environment": {
            "day_night": {
                "enabled": true,
                "ticks_per_day": 24,
                "starting_tick_in_day": 0,
                "announce_changes": true,
                "phases": [
                    {"name": "morning", "start_ratio": 0.0,  "display_text": "朝",   "ambient_light": 0.9, "is_dark": false},
                    {"name": "noon",    "start_ratio": 0.25, "display_text": "昼",   "ambient_light": 1.0, "is_dark": false},
                    {"name": "evening", "start_ratio": 0.5,  "display_text": "夕暮れ","ambient_light": 0.5, "is_dark": false},
                    {"name": "night",   "start_ratio": 0.66, "display_text": "夜",   "ambient_light": 0.1, "is_dark": true}
                ]
            }
        }
        ```

        - `enabled: false` または `day_night` セクション自体が無い場合は None を返し、
          runtime は昼夜サイクルを動かさない (常に時刻表示なし)
        - フェーズ列の昇順性などのバリデーションは DayNightCycleDef.__post_init__
          に任せる (作家ミスは boundary で弾く)
        """
        day_night = raw.get("day_night") if isinstance(raw, dict) else None
        if not isinstance(day_night, dict):
            return None
        if not bool(day_night.get("enabled", False)):
            return None

        # 漂流島 v2 で導入された「1 tick = 1 時間」スケールに合わせ default=24
        # (旧 default=12 は monster_behavior_world_port:196 の hardcode=24 と
        # 不整合で、ticks_per_day を省略したシナリオの day_night phase 判定が
        # 2 倍速で進む silent failure を生んでいた)
        ticks_per_day = int(day_night.get("ticks_per_day", 24))
        starting_tick = int(day_night.get("starting_tick_in_day", 0))
        announce = bool(day_night.get("announce_changes", True))
        phases_raw = day_night.get("phases", [])
        if not isinstance(phases_raw, list) or not phases_raw:
            raise ScenarioLoadError(
                "environment.day_night.phases must be a non-empty list"
            )
        required_keys = ("name", "start_ratio", "display_text", "ambient_light", "is_dark")
        phases_list: list[DayNightPhaseDef] = []
        for i, p in enumerate(phases_raw):
            # boundary 検証: 各要素が dict で必須キーを持っているかを scenario_loader
            # 層で弾く。これを怠ると未定義キーで KeyError が ScenarioLoadError を
            # 経由せず素通りし、作家へのエラーメッセージが分かりにくくなる。
            if not isinstance(p, dict):
                raise ScenarioLoadError(
                    f"environment.day_night.phases[{i}] must be an object, "
                    f"got {type(p).__name__}"
                )
            missing = [k for k in required_keys if k not in p]
            if missing:
                raise ScenarioLoadError(
                    f"environment.day_night.phases[{i}] is missing required keys: {missing}"
                )
            phases_list.append(
                DayNightPhaseDef(
                    name=str(p["name"]),
                    start_ratio=float(p["start_ratio"]),
                    display_text=str(p["display_text"]),
                    ambient_light=float(p["ambient_light"]),
                    is_dark=bool(p["is_dark"]),
                )
            )
        phases = tuple(phases_list)
        cycle = DayNightCycleDef(
            ticks_per_day=ticks_per_day,
            starting_tick_in_day=starting_tick,
            phases=phases,
        )
        return ScenarioDayNightConfig(cycle=cycle, announce_changes=announce)

    def _parse_monsters_block(
        self, raw: Optional[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> Tuple[Tuple[ScenarioMonsterTemplate, ...], Tuple[ScenarioMonsterPlacement, ...]]:
        """`monsters.templates` と `monsters.initial_placements` を読み込む (Phase B-2a)。

        JSON 形式:
        ```
        "monsters": {
          "templates": [
            {
              "id": "wild_dog",
              "name": "野犬",
              "description": "...",
              "race": "WOLF",                  // Race enum 名
              "faction": "ENEMY",              // MonsterFactionEnum 名
              "base_stats": {                  // 必須キー全部
                "max_hp": 30, "max_mp": 0, "attack": 8, "defense": 4,
                "speed": 6, "critical_rate": 0.05, "evasion_rate": 0.1
              },
              "reward": {"exp": 10, "gold": 0},
              "respawn": {"interval_ticks": 50, "auto": true},
              "vision_range": 4,
              "flee_threshold": 0.2
            }
          ],
          "initial_placements": [
            {"template": "wild_dog", "spot": "deep_forest", "coordinate": {"x": 0, "y": 0}}
          ]
        }
        ```

        Phase B-2a では initial_placements は static (シナリオ起動時のみ配置)。
        spawn_condition による動的 spawn は Phase B-2b で扱う。
        """
        if not isinstance(raw, dict):
            return ((), ())
        templates_raw = raw.get("templates", [])
        placements_raw = raw.get("initial_placements", [])
        if not isinstance(templates_raw, list):
            raise ScenarioLoadError("monsters.templates must be a list")
        if not isinstance(placements_raw, list):
            raise ScenarioLoadError("monsters.initial_placements must be a list")

        templates = tuple(
            self._parse_monster_template(t, mapper, i)
            for i, t in enumerate(templates_raw)
        )
        placements = tuple(
            self._parse_monster_placement(p, i)
            for i, p in enumerate(placements_raw)
        )
        return templates, placements

    def _parse_monster_template(
        self, raw: Any, mapper: ScenarioIdMapper, index: int,
    ) -> ScenarioMonsterTemplate:
        """1 monster template を MonsterTemplate に変換する。"""
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"monsters.templates[{index}] must be an object, got {type(raw).__name__}"
            )
        string_id = raw.get("id")
        if not isinstance(string_id, str) or not string_id:
            raise ScenarioLoadError(
                f"monsters.templates[{index}].id must be a non-empty string"
            )
        # 文字列 ID → 連番 int を id_mapper に登録 (将来 cross-reference する場面用)
        template_int_id = mapper.register("monster_template", string_id)

        base = raw.get("base_stats", {})
        if not isinstance(base, dict):
            raise ScenarioLoadError(
                f"monsters.templates[{index}].base_stats must be an object"
            )
        try:
            base_stats = BaseStats(
                max_hp=int(base.get("max_hp", 30)),
                max_mp=int(base.get("max_mp", 0)),
                attack=int(base.get("attack", 5)),
                defense=int(base.get("defense", 3)),
                speed=int(base.get("speed", 5)),
                critical_rate=float(base.get("critical_rate", 0.05)),
                evasion_rate=float(base.get("evasion_rate", 0.05)),
            )
        except (TypeError, ValueError) as e:
            raise ScenarioLoadError(
                f"monsters.templates[{index}].base_stats parse error: {e}"
            ) from e

        reward_raw = raw.get("reward", {})
        reward = RewardInfo(
            exp=int(reward_raw.get("exp", 0)),
            gold=int(reward_raw.get("gold", 0)),
        )
        respawn_raw = raw.get("respawn", {})
        respawn = RespawnInfo(
            respawn_interval_ticks=int(respawn_raw.get("interval_ticks", 50)),
            is_auto_respawn=bool(respawn_raw.get("auto", True)),
        )

        race_name = str(raw.get("race", "WOLF"))
        try:
            race = Race[race_name]
        except KeyError as e:
            valid = [r.name for r in Race]
            raise ScenarioLoadError(
                f"monsters.templates[{index}].race must be one of {valid}, got {race_name}"
            ) from e
        faction_name = str(raw.get("faction", "ENEMY"))
        try:
            faction = MonsterFactionEnum[faction_name]
        except KeyError as e:
            valid = [f.name for f in MonsterFactionEnum]
            raise ScenarioLoadError(
                f"monsters.templates[{index}].faction must be one of {valid}, got {faction_name}"
            ) from e

        template = MonsterTemplate(
            template_id=MonsterTemplateId(template_int_id),
            name=str(raw.get("name", string_id)),
            base_stats=base_stats,
            reward_info=reward,
            respawn_info=respawn,
            race=race,
            faction=faction,
            description=str(raw.get("description", "")),
            skill_ids=[],  # Phase B-2a ではスキル無し
            vision_range=int(raw.get("vision_range", 5)),
            flee_threshold=float(raw.get("flee_threshold", 0.2)),
        )
        return ScenarioMonsterTemplate(string_id=string_id, template=template)

    def _parse_monster_placement(
        self, raw: Any, index: int,
    ) -> ScenarioMonsterPlacement:
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"monsters.initial_placements[{index}] must be an object"
            )
        template_id = raw.get("template")
        spot_id = raw.get("spot")
        if not isinstance(template_id, str) or not template_id:
            raise ScenarioLoadError(
                f"monsters.initial_placements[{index}].template must be a non-empty string"
            )
        if not isinstance(spot_id, str) or not spot_id:
            raise ScenarioLoadError(
                f"monsters.initial_placements[{index}].spot must be a non-empty string"
            )
        coord = raw.get("coordinate", {})
        if not isinstance(coord, dict):
            coord = {}
        spawn_condition = self._parse_monster_spawn_condition(
            raw.get("spawn_condition"), index,
        )
        return ScenarioMonsterPlacement(
            template_string_id=template_id,
            spot_string_id=spot_id,
            coordinate_x=int(coord.get("x", 0)),
            coordinate_y=int(coord.get("y", 0)),
            coordinate_z=int(coord.get("z", 0)),
            spawn_condition=spawn_condition,
        )

    def _parse_monster_spawn_condition(
        self, raw: Any, placement_index: int,
    ) -> Optional[ScenarioMonsterSpawnCondition]:
        """placement の spawn_condition ブロックを ScenarioMonsterSpawnCondition に変換。

        JSON 形式:
        ```
        "spawn_condition": {
          "day_night_phases": ["night"],
          "required_flags": ["high_tide"],
          "forbidden_flags": [],
          "weather_types": ["STORM"]
        }
        ```
        いずれか 1 つでも軸が指定されれば条件付き。すべて空 / セクション欠落
        なら null を返し、placement は常時 spawn (static) 扱い。

        WeatherTypeEnum 名は boundary で検証する (作家ミスを早期に弾く)。
        day_night_phases は scenario 内で自由命名できるので事前検証しない。
        """
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"monsters.initial_placements[{placement_index}].spawn_condition "
                f"must be an object, got {type(raw).__name__}"
            )

        def _as_str_tuple(value: Any, key: str) -> Tuple[str, ...]:
            if value is None:
                return ()
            if not isinstance(value, list):
                raise ScenarioLoadError(
                    f"monsters.initial_placements[{placement_index}]."
                    f"spawn_condition.{key} must be a list of strings"
                )
            return tuple(str(v) for v in value)

        phases = _as_str_tuple(raw.get("day_night_phases"), "day_night_phases")
        required_flags = _as_str_tuple(raw.get("required_flags"), "required_flags")
        forbidden_flags = _as_str_tuple(raw.get("forbidden_flags"), "forbidden_flags")
        weathers = _as_str_tuple(raw.get("weather_types"), "weather_types")

        # WeatherTypeEnum 名は事前検証する。作家ミスは boundary で弾く。
        for w in weathers:
            try:
                WeatherTypeEnum[w]
            except KeyError as e:
                valid = [x.name for x in WeatherTypeEnum]
                raise ScenarioLoadError(
                    f"monsters.initial_placements[{placement_index}]."
                    f"spawn_condition.weather_types contains invalid value {w!r}. "
                    f"Valid values: {valid}"
                ) from e

        return ScenarioMonsterSpawnCondition(
            day_night_phase_names=phases,
            required_flags=required_flags,
            forbidden_flags=forbidden_flags,
            weather_type_names=weathers,
        )

    def _parse_weather_config(self, raw: Dict[str, Any]) -> Optional[ScenarioWeatherConfig]:
        weather = raw.get("weather") if isinstance(raw, dict) else None
        if not isinstance(weather, dict):
            return None
        enabled = bool(weather.get("enabled", False))
        initial = weather.get("initial", {})
        if not isinstance(initial, dict):
            initial = {}
        weather_type = WeatherTypeEnum[str(initial.get("weather_type", "FOG"))]
        intensity = float(initial.get("intensity", 0.6))
        return ScenarioWeatherConfig(
            enabled=enabled,
            initial_state=WeatherState(weather_type=weather_type, intensity=intensity),
            update_interval_ticks=int(weather.get("update_interval_ticks", 6)),
            announce_changes=bool(weather.get("announce_changes", True)),
        )

    def _parse_discoverable_item(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> DiscoverableItem:
        item_sid = raw["item_spec"]
        dc = self._parse_discovery_condition(raw.get("discovery_condition", {}), mapper)
        return DiscoverableItem(
            item_spec_id=ItemSpecId.create(mapper.get_int("item_spec", item_sid)),
            discovery_condition=dc,
            is_discovered=False,
            description=raw.get("description", ""),
        )

    def _parse_discovery_condition(self, raw: Optional[Dict[str, Any]], mapper: ScenarioIdMapper) -> DiscoveryCondition:
        if not raw:
            return DiscoveryCondition(condition_type=DiscoveryConditionTypeEnum.ALWAYS)
        item_sid = raw.get("required_item")
        item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
        return DiscoveryCondition(
            condition_type=DiscoveryConditionTypeEnum[raw.get("condition_type", "ALWAYS")],
            required_search_count=int(raw.get("required_search_count", 1)),
            required_item_spec_id=item_spec_id,
            flag_name=raw.get("flag_name"),
        )

    def _parse_passage_condition(self, raw: Dict[str, Any], mapper: ScenarioIdMapper) -> PassageCondition:
        item_sid = raw.get("required_item")
        item_spec_id = ItemSpecId.create(mapper.get_int("item_spec", item_sid)) if item_sid else None
        return PassageCondition(
            condition_type=PassageConditionTypeEnum[raw["condition_type"]],
            item_spec_id=item_spec_id,
            flag_name=raw.get("flag_name"),
            consume_item=bool(raw.get("consume_item", False)),
            failure_message=raw.get("failure_message", ""),
        )

    def _parse_connections(
        self, conns_raw: List[Dict[str, Any]], graph: SpotGraphAggregate, mapper: ScenarioIdMapper,
    ) -> None:
        for c in conns_raw:
            cid = mapper.register("connection", c["id"])
            from_sid = mapper.get_int("spot", c["from"])
            to_sid = mapper.get_int("spot", c["to"])
            conditions = [self._parse_passage_condition(p, mapper) for p in c.get("passage_conditions", [])]
            is_bidir = bool(c.get("is_bidirectional", True))
            # passage が無いシナリオは「開口部 (OPEN)」扱い。`initially_passable` /
            # 接続レベルの `sound_permeability` は廃止された旧スキーマのキーで、
            # 万一残っていれば作家への明示エラーにする。
            for legacy_key in ("initially_passable", "sound_permeability"):
                if legacy_key in c:
                    raise ScenarioLoadError(
                        f"Connection '{c['id']}' uses obsolete key '{legacy_key}'. "
                        f"Use `passage` block instead."
                    )
            passage = Passage.from_dict(c.get("passage"))

            conn = SpotConnection(
                connection_id=ConnectionId.create(cid),
                from_spot_id=SpotId.create(from_sid),
                to_spot_id=SpotId.create(to_sid),
                name=c["name"],
                description=c.get("description", ""),
                travel_ticks=int(c.get("travel_ticks", 1)),
                is_bidirectional=is_bidir,
                passage_conditions=conditions,
                passage=passage,
            )

            reverse_id: Optional[ConnectionId] = None
            if is_bidir:
                rev_str = c["id"] + "__reverse"
                rev_int = mapper.register("connection", rev_str)
                reverse_id = ConnectionId.create(rev_int)

            graph.add_connection(conn, reverse_connection_id=reverse_id)

        graph.clear_events()

    def _parse_players(
        self, players_raw: List[Dict[str, Any]], mapper: ScenarioIdMapper,
    ) -> List[PlayerSpawnConfig]:
        spawns: List[PlayerSpawnConfig] = []
        for p in players_raw:
            pid = mapper.register("player", p["id"])
            spot_sid = p["spawn_spot"]
            spot_id = SpotId.create(mapper.get_int("spot", spot_sid))
            items = tuple(
                self._parse_initial_item(raw, mapper, owner_id=p["id"])
                for raw in p.get("initial_items", [])
            )
            initial_state = self._parse_player_initial_state(
                p.get("initial_state", {}), owner_id=p["id"],
            )
            persona_raw = p.get("persona_prompt")
            persona_prompt: Optional[str] = None
            if persona_raw is not None:
                if not isinstance(persona_raw, str):
                    raise ValueError(
                        f"player '{p['id']}': persona_prompt must be a string, "
                        f"got {type(persona_raw).__name__}"
                    )
                # 前後 whitespace を削るが内側の改行は保持する (多行プロンプトを許容)
                stripped = persona_raw.strip()
                persona_prompt = stripped if stripped else None
            spawns.append(PlayerSpawnConfig(
                string_id=p["id"],
                player_id=pid,
                name=p["name"],
                spawn_spot_id=spot_id,
                initial_items=items,
                initial_state=initial_state,
                persona_prompt=persona_prompt,
            ))
        return spawns

    @staticmethod
    def _parse_player_initial_state(
        raw: Any, *, owner_id: str,
    ) -> Dict[str, Any]:
        """`players[].initial_state` を JSON プリミティブの flat dict に正規化。

        `PlayerStatusAggregate.state` の制約 (str / int / float / bool / None) に
        合わない値はシナリオ load 時点で `ScenarioLoadError` として弾く。
        domain 層側でも `PlayerStateValidationException` として再検証されるが、
        load 時点で落とせば「実行直前まで気付かない」事故が減る。
        """
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_state must be an object "
                f"(got {type(raw).__name__})"
            )
        allowed = (str, int, float, bool, type(None))
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_state key must be string "
                    f"(got {type(key).__name__}: {key!r})"
                )
            if not isinstance(value, allowed):
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_state[{key!r}] must be a JSON primitive "
                    f"(str / int / float / bool / null), got {type(value).__name__}"
                )
        return dict(raw)

    def _parse_initial_item(
        self,
        raw: Any,
        mapper: ScenarioIdMapper,
        *,
        owner_id: str,
    ) -> InitialItemSpec:
        """`initial_items` の 1 要素を `InitialItemSpec` にパース。

        受け付ける形式は 2 つ:
          - `"spec_string_id"` (state なし、Phase 4-A 以前のシナリオと互換)
          - `{"spec": "spec_string_id", "state": {...}}` (state を仕込める Phase 4-D 形式)
        どちらも 1 つの InitialItemSpec に正規化される。
        """
        if isinstance(raw, str):
            spec_id = ItemSpecId.create(mapper.get_int("item_spec", raw))
            return InitialItemSpec(spec_id=spec_id, state={})
        if isinstance(raw, dict):
            spec_string = raw.get("spec")
            if not isinstance(spec_string, str) or not spec_string:
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_items[*].spec is required "
                    f"(got {spec_string!r})"
                )
            spec_id = ItemSpecId.create(mapper.get_int("item_spec", spec_string))
            state_raw = raw.get("state", {})
            if not isinstance(state_raw, dict):
                raise ScenarioLoadError(
                    f"players[{owner_id}].initial_items[*].state must be an object "
                    f"(got {type(state_raw).__name__})"
                )
            return InitialItemSpec(spec_id=spec_id, state=dict(state_raw))
        raise ScenarioLoadError(
            f"players[{owner_id}].initial_items[*] must be a string or object "
            f"(got {type(raw).__name__})"
        )

    def _parse_end_conditions(
        self,
        raw: Any,
        mapper: ScenarioIdMapper,
    ) -> List[GameEndCondition]:
        if not raw:
            return []
        items = raw if isinstance(raw, list) else [raw]
        conditions: List[GameEndCondition] = []
        for item in items:
            ctype = GameEndConditionTypeEnum[item["type"]]
            target_spot = None
            if "target_spot" in item:
                target_spot = SpotId.create(mapper.get_int("spot", item["target_spot"]))
            conditions.append(GameEndCondition(
                condition_type=ctype,
                target_spot_id=target_spot,
                target_flag=item.get("target_flag"),
                tick_limit=item.get("tick_limit"),
            ))
        return conditions
