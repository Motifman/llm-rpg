"""interactionが直接変更するrepository外資源のrollback参加adapter。"""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, Callable, Generic, Optional, TypeVar

from ai_rpg_world.application.common.command_scope import RollbackParticipantPort
from ai_rpg_world.application.common.exceptions import (
    PoisonedRollbackParticipantException,
)
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
    SpotMonsterBehaviorTickService,
)
from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    InteractionCooldownStore,
)
from ai_rpg_world.application.world_graph.spot_graph_day_night_stage_service import (
    SpotGraphDayNightStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_environment_stage_service import (
    SpotGraphEnvironmentStageService,
)
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagChange,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.spot_graph_monster_spawn_stage_service import (
    SpotGraphMonsterSpawnStageService,
)
from ai_rpg_world.application.trade.services.in_memory_pending_trade_offer_store import (
    InMemoryPendingTradeOfferStore,
)
from ai_rpg_world.application.trade.services.in_memory_market_board_store import (
    InMemoryMarketBoardStore,
)
from ai_rpg_world.domain.player.service.player_outcome_registry import PlayerOutcomeRegistry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)

SnapshotT = TypeVar("SnapshotT")


class SnapshotRollbackParticipant(Generic[SnapshotT]):
    """snapshot取得・復元関数を持つ資源を占有つき参加資源へ適合させる。"""

    def __init__(
        self,
        resource: object,
        *,
        take_snapshot: Callable[[], SnapshotT],
        restore_snapshot: Callable[[SnapshotT], None],
    ) -> None:
        self._resource = resource
        self._take_snapshot = take_snapshot
        self._restore_snapshot = restore_snapshot
        self._ownership_lock = Lock()
        self._poison_error: BaseException | None = None

    @property
    def rollback_resource(self) -> object:
        return self._resource

    def acquire_rollback_ownership(self) -> None:
        self._ownership_lock.acquire()
        if self._poison_error is None:
            return
        poison_error = self._poison_error
        self._ownership_lock.release()
        raise PoisonedRollbackParticipantException(
            poison_error=poison_error
        ) from poison_error

    def release_rollback_ownership(self) -> None:
        self._ownership_lock.release()

    def take_rollback_snapshot(self) -> SnapshotT:
        return self._take_snapshot()

    def restore_rollback_snapshot(self, snapshot: SnapshotT) -> None:
        self._restore_snapshot(snapshot)

    def poison_after_rollback_failure(self, error: BaseException) -> None:
        self._poison_error = error


class WorldFlagRollbackParticipant:
    """world flagの状態とcommit前通知を同じrollback境界へ参加させる。"""

    def __init__(self, state: MutableWorldFlagState) -> None:
        self._state = state
        self._ownership_lock = Lock()
        self._poison_error: BaseException | None = None
        self._original_callback: Optional[Callable[[WorldFlagChange], None]] = None
        self._buffered_changes: list[WorldFlagChange] = []
        self._was_restored = False

    @property
    def rollback_resource(self) -> object:
        return self._state

    def acquire_rollback_ownership(self) -> None:
        self._ownership_lock.acquire()
        if self._poison_error is not None:
            poison_error = self._poison_error
            self._ownership_lock.release()
            raise PoisonedRollbackParticipantException(
                poison_error=poison_error
            ) from poison_error
        self._buffered_changes = []
        self._was_restored = False
        self._original_callback = self._state.exchange_change_callback(
            self._buffered_changes.append
        )

    def release_rollback_ownership(self) -> None:
        callback = self._original_callback
        self._state.exchange_change_callback(callback)
        buffered_changes = tuple(self._buffered_changes)
        was_restored = self._was_restored
        self._original_callback = None
        self._buffered_changes = []
        self._was_restored = False
        try:
            if callback is not None and not was_restored:
                for change in buffered_changes:
                    callback(change)
        except BaseException as error:
            # callback失敗を観測してからadapterがpoisonするまでの間に、別commandが
            # 同じ資源を取得できないよう、lock解放前に使用不能へ遷移させる。
            self._poison_error = error
            raise
        finally:
            self._ownership_lock.release()

    def take_rollback_snapshot(self) -> frozenset[str]:
        return self._state.as_frozen_set()

    def restore_rollback_snapshot(self, snapshot: frozenset[str]) -> None:
        self._was_restored = True
        self._state.replace_from_interaction(
            snapshot,
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SNAPSHOT_RESTORE,
                actor_player_id=None,
            ),
        )

    def poison_after_rollback_failure(self, error: BaseException) -> None:
        self._poison_error = error


def build_interaction_rollback_participants(
    *,
    world_flags: MutableWorldFlagState,
    cooldowns: InteractionCooldownStore,
    departed_positions: DepartedPositionStore,
    spot_graph: InMemorySpotGraphRepository,
) -> tuple[RollbackParticipantPort, ...]:
    """runtimeのinteractionが直接変更する4資源を固定順で組み立てる。"""
    return (
        WorldFlagRollbackParticipant(world_flags),
        _cooldown_participant(cooldowns),
        SnapshotRollbackParticipant(
            departed_positions,
            take_snapshot=departed_positions.snapshot,
            restore_snapshot=departed_positions.replace_all,
        ),
        SnapshotRollbackParticipant(
            spot_graph,
            take_snapshot=lambda: deepcopy(spot_graph.find_graph()),
            restore_snapshot=lambda snapshot: spot_graph.save(deepcopy(snapshot)),
        ),
    )


def build_meeting_rollback_participants(
    *,
    game_phases: GamePhaseStore,
    spot_graph: InMemorySpotGraphRepository,
    world_flags: MutableWorldFlagState,
    player_outcomes: PlayerOutcomeRegistry,
    fallen_bodies: FallenBodyRegistry,
) -> tuple[RollbackParticipantPort, ...]:
    """会議commandが変更する状態と通知を同じ境界へ載せる。"""
    return (
        SnapshotRollbackParticipant(
            game_phases,
            take_snapshot=game_phases.rollback_snapshot,
            restore_snapshot=game_phases.restore_rollback_snapshot,
        ),
        _spot_graph_participant(spot_graph),
        WorldFlagRollbackParticipant(world_flags),
        SnapshotRollbackParticipant(
            player_outcomes,
            take_snapshot=player_outcomes.snapshot,
            restore_snapshot=lambda snapshot: player_outcomes.replace_all(
                {
                    PlayerId(player_id): outcome
                    for player_id, outcome in snapshot.items()
                }
            ),
        ),
        SnapshotRollbackParticipant(
            fallen_bodies,
            take_snapshot=fallen_bodies.snapshot,
            restore_snapshot=fallen_bodies.replace_all,
        ),
    )


def build_movement_rollback_participants(
    *,
    departed_positions: DepartedPositionStore,
    spot_graph: InMemorySpotGraphRepository,
) -> tuple[RollbackParticipantPort, ...]:
    """移動が直接変更する退場者位置とgraphを同じ境界へ載せる。"""
    return (
        SnapshotRollbackParticipant(
            departed_positions,
            take_snapshot=departed_positions.snapshot,
            restore_snapshot=departed_positions.replace_all,
        ),
        _spot_graph_participant(spot_graph),
    )


def build_scenario_event_rollback_participants(
    *,
    world_flags: MutableWorldFlagState,
    spot_graph: InMemorySpotGraphRepository,
    progress: InMemorySpotGraphScenarioEventProgressStore,
) -> tuple[RollbackParticipantPort, ...]:
    """scenario eventが直接変更する3資源を同じ境界へ載せる。"""
    return (
        WorldFlagRollbackParticipant(world_flags),
        _spot_graph_participant(spot_graph),
        SnapshotRollbackParticipant(
            progress,
            take_snapshot=progress.rollback_snapshot,
            restore_snapshot=progress.restore_rollback_snapshot,
        ),
    )


def build_reactive_rollback_participants(
    *,
    spot_graph: InMemorySpotGraphRepository,
    condition_evaluator: ScenarioConditionEvaluator,
) -> tuple[RollbackParticipantPort, ...]:
    """reactive stageが変更するgraphと確率条件の乱数列を同じ境界へ載せる。"""
    return (
        _spot_graph_participant(spot_graph),
        SnapshotRollbackParticipant(
            condition_evaluator,
            take_snapshot=condition_evaluator.rollback_snapshot,
            restore_snapshot=condition_evaluator.restore_rollback_snapshot,
        ),
    )


def build_synchronized_action_rollback_participants(
    *,
    world_flags: MutableWorldFlagState,
    spot_graph: InMemorySpotGraphRepository,
) -> tuple[RollbackParticipantPort, ...]:
    """同期操作groupのprepare・効果flagとgraphを同じ境界へ載せる。"""
    return (
        WorldFlagRollbackParticipant(world_flags),
        _spot_graph_participant(spot_graph),
    )


def build_weather_rollback_participants(
    *,
    stage: SpotGraphEnvironmentStageService,
) -> tuple[RollbackParticipantPort, ...]:
    """天候状態と専用乱数列を一つの遷移境界へ載せる。"""
    return (
        SnapshotRollbackParticipant(
            stage,
            take_snapshot=stage.rollback_snapshot,
            restore_snapshot=stage.restore_rollback_snapshot,
        ),
    )


def build_day_night_rollback_participants(
    *,
    stage: SpotGraphDayNightStageService,
) -> tuple[RollbackParticipantPort, ...]:
    """現在の昼夜位置を一つの遷移境界へ載せる。"""
    return (
        SnapshotRollbackParticipant(
            stage,
            take_snapshot=stage.rollback_snapshot,
            restore_snapshot=stage.restore_rollback_snapshot,
        ),
    )


def build_monster_spawn_rollback_participants(
    *,
    spot_graph: InMemorySpotGraphRepository,
    stage: SpotGraphMonsterSpawnStageService,
) -> tuple[RollbackParticipantPort, ...]:
    """spawn slot対応・採番とgraphを同じ境界へ載せる。"""
    return (
        _spot_graph_participant(spot_graph),
        SnapshotRollbackParticipant(
            stage,
            take_snapshot=stage.rollback_snapshot,
            restore_snapshot=stage.restore_rollback_snapshot,
        ),
    )


def build_monster_behavior_rollback_participants(
    *,
    spot_graph: InMemorySpotGraphRepository,
    service: SpotMonsterBehaviorTickService,
) -> tuple[RollbackParticipantPort, ...]:
    """monster行動が変更するgraphと乱数列を同じ境界へ載せる。"""
    return (
        _spot_graph_participant(spot_graph),
        SnapshotRollbackParticipant(
            service,
            take_snapshot=service.rollback_snapshot,
            restore_snapshot=service.restore_rollback_snapshot,
        ),
    )


def build_trade_offer_expiry_rollback_participants(
    *,
    pending_trade_offers: InMemoryPendingTradeOfferStore,
) -> tuple[RollbackParticipantPort, ...]:
    """期限切れ処理が削除するpending offer storeをrollback境界へ載せる。"""
    return (
        SnapshotRollbackParticipant(
            pending_trade_offers,
            take_snapshot=pending_trade_offers.rollback_snapshot,
            restore_snapshot=pending_trade_offers.restore_rollback_snapshot,
        ),
    )


def build_market_order_expiry_rollback_participants(
    *,
    market_board: InMemoryMarketBoardStore,
) -> tuple[RollbackParticipantPort, ...]:
    """期限切れ返却が更新する板と採番をrollback境界へ載せる。"""
    return (
        SnapshotRollbackParticipant(
            market_board,
            take_snapshot=market_board.rollback_snapshot,
            restore_snapshot=market_board.restore_rollback_snapshot,
        ),
    )


def build_player_outcome_rule_rollback_participants(
    *,
    player_outcomes: PlayerOutcomeRegistry,
    progress: InMemorySpotGraphScenarioEventProgressStore,
    condition_evaluator: ScenarioConditionEvaluator,
) -> tuple[RollbackParticipantPort, ...]:
    """outcome ruleの結果・発火進捗・確率乱数を同じ境界へ載せる。"""
    return (
        SnapshotRollbackParticipant(
            player_outcomes,
            take_snapshot=player_outcomes.snapshot,
            restore_snapshot=lambda snapshot: player_outcomes.replace_all(
                {
                    PlayerId(player_id): outcome
                    for player_id, outcome in snapshot.items()
                }
            ),
        ),
        SnapshotRollbackParticipant(
            progress,
            take_snapshot=progress.rollback_snapshot,
            restore_snapshot=progress.restore_rollback_snapshot,
        ),
        SnapshotRollbackParticipant(
            condition_evaluator,
            take_snapshot=condition_evaluator.rollback_snapshot,
            restore_snapshot=condition_evaluator.restore_rollback_snapshot,
        ),
    )


def _spot_graph_participant(
    spot_graph: InMemorySpotGraphRepository,
) -> SnapshotRollbackParticipant[Any]:
    return SnapshotRollbackParticipant(
        spot_graph,
        take_snapshot=lambda: deepcopy(spot_graph.find_graph()),
        restore_snapshot=lambda snapshot: spot_graph.save(deepcopy(snapshot)),
    )


def _cooldown_participant(
    store: InteractionCooldownStore,
) -> SnapshotRollbackParticipant[Any]:
    def restore(snapshot: Any) -> None:
        actor_entries, world_entries = snapshot
        store.replace_all(
            (
                (player_id, action_name, tick)
                for player_id, actions in actor_entries.items()
                for action_name, tick in actions.items()
            ),
            world_entries.items(),
        )

    return SnapshotRollbackParticipant(
        store,
        take_snapshot=store.snapshot,
        restore_snapshot=restore,
    )


__all__ = [
    "SnapshotRollbackParticipant",
    "WorldFlagRollbackParticipant",
    "build_day_night_rollback_participants",
    "build_interaction_rollback_participants",
    "build_market_order_expiry_rollback_participants",
    "build_player_outcome_rule_rollback_participants",
    "build_monster_behavior_rollback_participants",
    "build_monster_spawn_rollback_participants",
    "build_reactive_rollback_participants",
    "build_scenario_event_rollback_participants",
    "build_synchronized_action_rollback_participants",
    "build_trade_offer_expiry_rollback_participants",
    "build_weather_rollback_participants",
    "build_meeting_rollback_participants",
    "build_movement_rollback_participants",
]
