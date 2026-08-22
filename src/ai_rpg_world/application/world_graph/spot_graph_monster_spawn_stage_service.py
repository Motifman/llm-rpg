"""spot-graph 専用のモンスター動的 spawn ステージサービス (Phase B-2b)。

タイルマップ時代の `MonsterSpawnSlotService` は physical_map_repository に
依存しており、world_runtime / spot-graph 世界 (physical_map_repository=None)
では発火しない。本サービスは physical_map に一切触れず、spot_graph_repository
だけで完結する spawn / despawn 経路を提供する。

挙動:
- placement.spawn_condition が None または `is_always` → 何もしない
  (B-2a の static 配置経路で起動時に置かれている前提)
- spawn_condition が条件付きの場合、tick 毎に条件を評価:
    - 満たす かつ instance 未配置 → spawn
    - 満たさない かつ instance 配置済み → despawn

despawn 時はモンスターを graph から除去する (death ではなく「いなくなる」)。
spawn / despawn が確定した後、graph の domain event を observation pipeline へ
引き渡す。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple, TYPE_CHECKING

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
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    MonsterNotInGraphException,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.service.scenario_predicate_evaluator import (
    ScenarioPredicateEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    WeatherTypePredicateContext,
    WorldFlagPredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    FlagSetPredicate,
    WeatherTypeIsPredicate,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandContext
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.monster_spawn_command_repository_provider import (
        MonsterSpawnCommandRepositoryProviderPort,
    )


_logger = logging.getLogger(__name__)


class _CommandContextEventPublisher:
    """graph eventをspawn commandの収集口へ適合させる。"""

    def __init__(self, context: "CommandContext") -> None:
        self._context = context

    def publish_all(self, events: Tuple[Any, ...]) -> None:
        self._context.collect_all(events)


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
FlagsProvider = Callable[[], FrozenSet[str]]
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
        predicate_evaluator: Optional[ScenarioPredicateEvaluator] = None,
        monster_id_factory: Optional[Callable[[], int]] = None,
        loadout_id_factory: Optional[Callable[[], int]] = None,
        world_object_id_factory: Optional[Callable[[], int]] = None,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[MonsterSpawnCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        self._slots = slots
        self._monster_repository = monster_repository
        self._skill_loadout_repository = skill_loadout_repository
        self._spot_graph_repository = spot_graph_repository
        self._time_of_day_provider = time_of_day_provider
        self._flags_provider = flags_provider
        self._weather_type_provider = weather_type_provider
        self._predicate_evaluator = predicate_evaluator or ScenarioPredicateEvaluator()

        # 採番: runtime が in-memory counter を注入する。本サービスは数字さえ
        # 取得できれば良いので factory パターンに分離する (テスト容易性)。
        self._monster_id_factory = monster_id_factory
        self._loadout_id_factory = loadout_id_factory
        self._world_object_id_factory = world_object_id_factory
        self._next_monster_id_value = 10_000
        self._next_loadout_id_value = 20_000
        self._next_world_object_id_value = 2_000_000

        # slot_key → 現在 spawn 中の MonsterId。None なら未配置。
        self._slot_to_monster: Dict[str, Optional[MonsterId]] = {
            slot.slot_key: None for slot in slots
        }
        self._command_scope_factory = command_scope_factory
        self._validate_scope_counter_contract()

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[MonsterSpawnCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageをslot 1件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory
        self._validate_scope_counter_contract()

    def _validate_scope_counter_contract(self) -> None:
        if self._command_scope_factory is None:
            return
        if any(
            factory is not None
            for factory in (
                self._monster_id_factory,
                self._loadout_id_factory,
                self._world_object_id_factory,
            )
        ):
            raise ValueError(
                "CommandScopeを使うmonster spawnでは外部ID factoryを使用できません"
            )

    def rollback_snapshot(
        self,
    ) -> tuple[Dict[str, Optional[MonsterId]], int, int, int]:
        """slot対応と内部採番をrollback用に複製する。"""
        return (
            dict(self._slot_to_monster),
            self._next_monster_id_value,
            self._next_loadout_id_value,
            self._next_world_object_id_value,
        )

    def restore_rollback_snapshot(
        self,
        snapshot: tuple[Dict[str, Optional[MonsterId]], int, int, int],
    ) -> None:
        """失敗commandのslot対応と採番を開始前へ戻す。"""
        slots, monster_id, loadout_id, world_object_id = snapshot
        self._slot_to_monster = dict(slots)
        self._next_monster_id_value = monster_id
        self._next_loadout_id_value = loadout_id
        self._next_world_object_id_value = world_object_id

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
                self._run_slot_command(slot, current_tick, spawn=True)
            elif not satisfied and current is not None:
                self._run_slot_command(
                    slot,
                    current_tick,
                    spawn=False,
                    monster_id=current,
                )

    def _run_slot_command(
        self,
        slot: MonsterSpawnSlot,
        current_tick: WorldTick,
        *,
        spawn: bool,
        monster_id: MonsterId | None = None,
    ) -> None:
        """slot 1件のspawnまたはdespawnを一つのscopeで確定する。"""
        if self._command_scope_factory is None:
            if spawn:
                self._spawn(
                    slot,
                    current_tick,
                    monster_repository=self._monster_repository,
                    skill_loadout_repository=self._skill_loadout_repository,
                    spot_graph_repository=self._spot_graph_repository,
                    event_publisher=None,
                )
            elif monster_id is not None:
                self._despawn(
                    slot.slot_key,
                    monster_id,
                    spot_graph_repository=self._spot_graph_repository,
                    event_publisher=None,
                )
            return

        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            event_publisher = _CommandContextEventPublisher(context)
            if spawn:
                self._spawn(
                    slot,
                    current_tick,
                    monster_repository=repositories.monsters,
                    skill_loadout_repository=repositories.skill_loadouts,
                    spot_graph_repository=repositories.spot_graph,
                    event_publisher=event_publisher,
                )
            elif monster_id is not None:
                self._despawn(
                    slot.slot_key,
                    monster_id,
                    spot_graph_repository=repositories.spot_graph,
                    event_publisher=event_publisher,
                )

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
            context = WorldFlagPredicateContext(flags)
            for required in slot.required_flags:
                result = self._predicate_evaluator.evaluate(
                    FlagSetPredicate(required), context,
                )
                if not ScenarioPredicateEvaluator.require_satisfaction(result):
                    return False
            for forbidden in slot.forbidden_flags:
                result = self._predicate_evaluator.evaluate(
                    FlagSetPredicate(forbidden), context,
                )
                if ScenarioPredicateEvaluator.require_satisfaction(result):
                    return False

        if slot.weather_type_names:
            current_weather = (
                self._weather_type_provider() if self._weather_type_provider else None
            )
            if current_weather is None:
                return False
            try:
                current_weather_type = WeatherTypeEnum(current_weather)
            except (TypeError, ValueError):
                # loaderを迂回した未知値は、共通化前と同じ完全一致で判定する。
                return current_weather in slot.weather_type_names
            context = WeatherTypePredicateContext(current_weather_type)
            for weather_name in slot.weather_type_names:
                try:
                    required_weather_type = WeatherTypeEnum(weather_name)
                except (TypeError, ValueError):
                    if current_weather == weather_name:
                        return True
                    continue
                result = self._predicate_evaluator.evaluate(
                    WeatherTypeIsPredicate(required_weather_type), context,
                )
                if ScenarioPredicateEvaluator.require_satisfaction(result):
                    return True
            return False

        return True

    def _spawn(
        self,
        slot: MonsterSpawnSlot,
        current_tick: WorldTick,
        *,
        monster_repository: MonsterRepository,
        skill_loadout_repository: SkillLoadoutRepository,
        spot_graph_repository: ISpotGraphRepository,
        event_publisher: Any | None,
    ) -> None:
        """monster、loadout、graph、slot対応を一括更新する。"""
        monster_id = MonsterId(self._allocate_monster_id())
        world_object_id = WorldObjectId(self._allocate_world_object_id())
        loadout = SkillLoadoutAggregate.create(
            loadout_id=SkillLoadoutId(self._allocate_loadout_id()),
            owner_id=monster_id.value,
            normal_capacity=0,
            awakened_capacity=0,
        )
        skill_loadout_repository.save(loadout)
        monster = MonsterAggregate.reconstitute(
            monster_id=monster_id,
            template=slot.template,
            world_object_id=world_object_id,
            skill_loadout=loadout,
            coordinate=slot.coordinate,
            spot_id=slot.spot_id,
            current_tick=current_tick,
        )
        monster_repository.save(monster)
        graph = spot_graph_repository.find_graph()
        graph.place_monster(monster_id, slot.spot_id)
        self._save_graph_and_collect_events(
            graph,
            spot_graph_repository=spot_graph_repository,
            event_publisher=event_publisher,
        )
        self._slot_to_monster[slot.slot_key] = monster_id

    def _despawn(
        self,
        slot_key: str,
        monster_id: MonsterId,
        *,
        spot_graph_repository: ISpotGraphRepository,
        event_publisher: Any | None,
    ) -> None:
        """配置とslot対応を同じ確定境界で取り消す。"""
        graph = spot_graph_repository.find_graph()
        try:
            graph.unplace_monster(monster_id)
        except MonsterNotInGraphException:
            # 既に死亡・撤去済みならslotを空にして次のspawnを許可する。
            self._slot_to_monster[slot_key] = None
            return
        self._save_graph_and_collect_events(
            graph,
            spot_graph_repository=spot_graph_repository,
            event_publisher=event_publisher,
        )
        self._slot_to_monster[slot_key] = None

    def _save_graph_and_collect_events(
        self,
        graph: Any,
        *,
        spot_graph_repository: ISpotGraphRepository,
        event_publisher: Any | None,
    ) -> None:
        events: Tuple[Any, ...] = ()
        if event_publisher is not None:
            events = tuple(graph.get_events())
            graph.clear_events()
        spot_graph_repository.save(graph)
        if events and event_publisher is not None:
            event_publisher.publish_all(events)

    def _allocate_monster_id(self) -> int:
        if self._monster_id_factory is not None:
            return self._monster_id_factory()
        self._next_monster_id_value += 1
        return self._next_monster_id_value

    def _allocate_loadout_id(self) -> int:
        if self._loadout_id_factory is not None:
            return self._loadout_id_factory()
        self._next_loadout_id_value += 1
        return self._next_loadout_id_value

    def _allocate_world_object_id(self) -> int:
        if self._world_object_id_factory is not None:
            return self._world_object_id_factory()
        self._next_world_object_id_value += 1
        return self._next_world_object_id_value

    def active_slot_keys(self) -> List[str]:
        """現在 spawn 中のスロットキー一覧 (テスト / 観測用)。"""
        return [k for k, m in self._slot_to_monster.items() if m is not None]
