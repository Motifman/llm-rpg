"""spot-graph 専用のモンスター動的 spawn ステージサービス (Phase B-2b)。

タイルマップ時代の `MonsterSpawnSlotService` は physical_map_repository に
依存しており、escape_game / spot-graph 世界 (physical_map_repository=None)
では発火しない。本サービスは physical_map に一切触れず、spot_graph_repository
だけで完結する spawn / despawn 経路を提供する。

挙動:
- placement.spawn_condition が None または `is_always` → 何もしない
  (B-2a の static 配置経路で起動時に置かれている前提)
- spawn_condition が条件付きの場合、tick 毎に条件を評価:
    - 満たす かつ instance 未配置 → spawn
    - 満たさない かつ instance 配置済み → despawn

despawn 時はモンスターを graph と repository から削除する (death ではなく
「いなくなる」)。プレイヤーには observation pipeline を通じて
`MonsterLeftSpotEvent` (既存) で「気配が消えた」を通知する経路があるが、
本 PR では event 発火経路までは整備せず、graph レベルの状態整合のみ保つ
(observation 統合は次イテレーション)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillLoadoutRepository,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonsterSpawnSlot:
    """1 つの動的 placement に対応する spawn スロット定義。

    scenario_loader の ScenarioMonsterPlacement と等価な情報を持つが、ドメイン
    依存を解いた純粋な値オブジェクトとして本サービス内に閉じる。runtime が
    placement から構築する責務を持つ。
    """

    slot_key: str  # 一意識別子 (例: "wild_dog@deep_forest#0")
    template: MonsterTemplate
    spot_id: SpotId
    coordinate: Coordinate
    # 軸: ANY 軸が指定されていれば AND で評価される。空 tuple は「制約なし」。
    day_night_phase_names: Tuple[str, ...]
    required_flags: Tuple[str, ...]
    forbidden_flags: Tuple[str, ...]
    weather_type_names: Tuple[str, ...]


# 評価用の provider 関数群 (runtime が runtime 内のものを渡す)
TimeOfDayProvider = Callable[[], Optional[TimeOfDay]]
FlagsProvider = Callable[[], frozenset]
WeatherTypeNameProvider = Callable[[], Optional[str]]  # WeatherTypeEnum.name


class SpotGraphMonsterSpawnStageService:
    """spot-graph 用の monster spawn ステージ。

    SimulationApplicationService の tick stage として `run(current_tick)` を
    呼ばれる前提 (Protocol 適合)。monster_behavior_stage より**前**に走らせる
    ことで、その tick で spawn したモンスターが同 tick の behavior に乗る。
    """

    def __init__(
        self,
        *,
        slots: Tuple[MonsterSpawnSlot, ...],
        monster_repository: MonsterRepository,
        skill_loadout_repository: SkillLoadoutRepository,
        spot_graph_repository: ISpotGraphRepository,
        time_of_day_provider: Optional[TimeOfDayProvider] = None,
        flags_provider: Optional[FlagsProvider] = None,
        weather_type_provider: Optional[WeatherTypeNameProvider] = None,
        monster_id_factory: Optional[Callable[[], int]] = None,
        loadout_id_factory: Optional[Callable[[], int]] = None,
        world_object_id_factory: Optional[Callable[[], int]] = None,
    ) -> None:
        self._slots = slots
        self._monster_repository = monster_repository
        self._skill_loadout_repository = skill_loadout_repository
        self._spot_graph_repository = spot_graph_repository
        self._time_of_day_provider = time_of_day_provider
        self._flags_provider = flags_provider
        self._weather_type_provider = weather_type_provider

        # 採番: runtime が in-memory counter を注入する。本サービスは数字さえ
        # 取得できれば良いので factory パターンに分離する (テスト容易性)。
        self._next_monster_id = monster_id_factory or self._default_counter(10_000)
        self._next_loadout_id = loadout_id_factory or self._default_counter(20_000)
        self._next_world_object_id = world_object_id_factory or self._default_counter(2_000_000)

        # slot_key → 現在 spawn 中の MonsterId。None なら未配置。
        self._slot_to_monster: Dict[str, Optional[MonsterId]] = {
            slot.slot_key: None for slot in slots
        }

    @staticmethod
    def _default_counter(start: int) -> Callable[[], int]:
        """internal use: 単純 incrementing counter。"""
        state = {"n": start}

        def _next() -> int:
            state["n"] += 1
            return state["n"]
        return _next

    def run(self, current_tick: WorldTick) -> None:
        """tick stage Protocol。条件評価して spawn / despawn する。"""
        for slot in self._slots:
            try:
                satisfied = self._evaluate(slot)
            except Exception:
                _logger.warning(
                    "monster spawn condition evaluation failed for slot=%s; skipping this tick",
                    slot.slot_key,
                    exc_info=True,
                )
                continue
            current = self._slot_to_monster[slot.slot_key]
            if satisfied and current is None:
                self._spawn(slot, current_tick)
            elif not satisfied and current is not None:
                self._despawn(slot.slot_key, current)

    def _evaluate(self, slot: MonsterSpawnSlot) -> bool:
        """slot の条件を現在の world state で評価する。"""
        if slot.day_night_phase_names:
            if self._time_of_day_provider is None:
                # cycle が宣言されていない世界では時間帯軸を要求するスロットは
                # 永遠に spawn しない。シナリオ設計上のミスなので warning。
                _logger.warning(
                    "spawn slot %s requires day_night phase but no provider is wired",
                    slot.slot_key,
                )
                return False
            tod = self._time_of_day_provider()
            if tod is None or tod.phase_name not in slot.day_night_phase_names:
                return False

        if slot.required_flags or slot.forbidden_flags:
            flags = self._flags_provider() if self._flags_provider else frozenset()
            for required in slot.required_flags:
                if required not in flags:
                    return False
            for forbidden in slot.forbidden_flags:
                if forbidden in flags:
                    return False

        if slot.weather_type_names:
            current_weather = (
                self._weather_type_provider() if self._weather_type_provider else None
            )
            if current_weather is None or current_weather not in slot.weather_type_names:
                return False

        return True

    def _spawn(self, slot: MonsterSpawnSlot, current_tick: WorldTick) -> None:
        """monster_repository と graph に 1 体追加する。"""
        monster_id = MonsterId(self._next_monster_id())
        world_object_id = WorldObjectId(self._next_world_object_id())
        loadout = SkillLoadoutAggregate.create(
            loadout_id=SkillLoadoutId(self._next_loadout_id()),
            owner_id=monster_id.value,
            normal_capacity=0,
            awakened_capacity=0,
        )
        self._skill_loadout_repository.save(loadout)
        monster = MonsterAggregate.reconstitute(
            monster_id=monster_id,
            template=slot.template,
            world_object_id=world_object_id,
            skill_loadout=loadout,
            coordinate=slot.coordinate,
            spot_id=slot.spot_id,
            current_tick=current_tick,
        )
        self._monster_repository.save(monster)
        graph = self._spot_graph_repository.find_graph()
        graph.place_monster(monster_id, slot.spot_id)
        self._spot_graph_repository.save(graph)
        self._slot_to_monster[slot.slot_key] = monster_id

    def _despawn(self, slot_key: str, monster_id: MonsterId) -> None:
        """配置を取り消す。今は graph state のみ整理 (observation 連動は別 PR)。"""
        graph = self._spot_graph_repository.find_graph()
        try:
            graph.unplace_monster(monster_id)
        except Exception:
            # 既に死亡 / 別経路で削除済みのレース。silent ではなく warning で
            # ログを残す (silent-failure-hunter の指摘パターン回避)。
            _logger.warning(
                "despawn failed for monster_id=%s slot=%s; graph state may be inconsistent",
                monster_id.value, slot_key, exc_info=True,
            )
        else:
            self._spot_graph_repository.save(graph)
        self._slot_to_monster[slot_key] = None

    def active_slot_keys(self) -> List[str]:
        """現在 spawn 中のスロットキー一覧 (テスト / 観測用)。"""
        return [k for k, m in self._slot_to_monster.items() if m is not None]
