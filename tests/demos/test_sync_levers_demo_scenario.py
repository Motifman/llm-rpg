"""協力ギミック #13 (同時操作パズル) の最小デモシナリオの end-to-end 検証。

`tests/fixtures/scenarios/sync_levers_demo.json` を読み込み、registry + resolver stage
が tick 単位で正しく完成 / タイムアウトを判定し、passage 状態が遷移すること
を確認する。LLM ツール呼び出しは経由せず、registry に直接 prepare を投入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.synchronized_action_resolver_stage_service import (
    SynchronizedActionResolverStageService,
)
from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "scenarios"
    / "sync_levers_demo.json"
)


@dataclass
class _Harness:
    loaded: object
    spot_graph_repo: InMemorySpotGraphRepository
    registry: SynchronizedActionRegistry
    stage: SynchronizedActionResolverStageService
    world_flags: MutableWorldFlagState
    delivered_messages: list[tuple[str, str, tuple[int, ...], str]]


@pytest.fixture
def sync_levers() -> _Harness:
    loaded = ScenarioLoader().load_from_file(SCENARIO_PATH)
    graph = loaded.graph
    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    for sid, interior in loaded.interiors.items():
        interior_repo.save(sid, interior)
    flags = MutableWorldFlagState()
    registry = SynchronizedActionRegistry(flags)
    delivered_messages: list[tuple[str, str, tuple[int, ...], str]] = []
    stage = SynchronizedActionResolverStageService(
        groups=loaded.synchronized_action_groups,
        registry=registry,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        world_flag_state=flags,
        on_message=lambda group_id, outcome, recipients, message: delivered_messages.append(
            (group_id, outcome, recipients, message)
        ),
    )
    return _Harness(
        loaded=loaded,
        spot_graph_repo=spot_graph_repo,
        registry=registry,
        stage=stage,
        world_flags=flags,
        delivered_messages=delivered_messages,
    )


def _vault_door_cid(loaded) -> ConnectionId:
    return ConnectionId.create(loaded.id_mapper.get_int("connection", "lever_to_vault"))


class TestSyncLeversDemoScenario:
    """sync_levers_demo.json が #13 仕様通りに動く。"""

    def test_loads_one_synchronized_group(self, sync_levers: _Harness) -> None:
        """シナリオから 1 つの sync group が読み込まれる。"""
        groups = sync_levers.loaded.synchronized_action_groups
        assert len(groups) == 1
        assert groups[0].group_id == "vault_unlock"
        assert groups[0].window_ticks == 2
        assert groups[0].on_prepare_observation_message is not None

    def test_two_prepares_in_same_tick_unlock_vault(self, sync_levers: _Harness) -> None:
        """同 tick に両 prepare が揃えば次の resolver run で扉が OPEN になる。"""
        sync_levers.registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=3)
        sync_levers.registry.prepare(action_id="pull_lever_right", player_id=2, current_tick=3)

        sync_levers.stage.run(WorldTick(3))
        cid = _vault_door_cid(sync_levers.loaded)
        assert sync_levers.spot_graph_repo.find_graph().get_connection(cid).passage.state == "OPEN"
        assert "vault_unlocked" in sync_levers.world_flags.as_frozen_set()

    def test_partial_prepare_times_out_after_window(self, sync_levers: _Harness) -> None:
        """A だけ prepare して B が来ないと、window=2 経過で reset される。"""
        sync_levers.registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=3)
        # window_ticks=2 なので tick=3 から (3+2)=5 以降で timeout
        sync_levers.stage.run(WorldTick(4))  # まだ pending
        cid = _vault_door_cid(sync_levers.loaded)
        assert sync_levers.spot_graph_repo.find_graph().get_connection(cid).passage.state == "LOCKED"
        assert sync_levers.registry.entries_for("pull_lever_left") != []

        sync_levers.stage.run(WorldTick(5))  # timeout
        # passage は LOCKED のまま、prepare はクリアされる
        assert sync_levers.spot_graph_repo.find_graph().get_connection(cid).passage.state == "LOCKED"
        assert sync_levers.registry.entries_for("pull_lever_left") == []
        assert sync_levers.delivered_messages == [
            (
                "vault_unlock",
                "timed_out",
                (1,),
                "レバーが元の位置に戻る音がした。タイミングを合わせ直す必要がある。",
            )
        ]

    def test_one_tick_offset_still_within_window(self, sync_levers: _Harness) -> None:
        """tick 3 と tick 4 の prepare は window=2 内なので完成する。"""
        sync_levers.registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=3)
        sync_levers.registry.prepare(action_id="pull_lever_right", player_id=2, current_tick=4)

        sync_levers.stage.run(WorldTick(4))
        assert "vault_unlocked" in sync_levers.world_flags.as_frozen_set()


class TestSyncLeverMessagesReachRuntimeObservations:
    """同期操作の SHOW_MESSAGE が実 runtime の参加者観測へ届くことを保証する。"""

    @staticmethod
    def _result_messages(runtime, player_id: PlayerId) -> list[str]:
        return [
            entry.output.prose
            for entry in runtime._obs_buffer.get_observations(player_id)
            if entry.output.structured.get("type") == "synchronized_action_result"
        ]

    def test_completion_message_reaches_all_prepared_players(self) -> None:
        """完成文は、準備した二人の観測へ同じ一件として届く。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        stage = runtime._simulation_service._sync_action_resolver_stage
        stage._registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=0)
        stage._registry.prepare(action_id="pull_lever_right", player_id=2, current_tick=0)

        runtime.advance_tick()

        expected = "二つのレバーが噛み合い、金庫扉の錠が外れた。"
        assert self._result_messages(runtime, PlayerId(1)) == [expected]
        assert self._result_messages(runtime, PlayerId(2)) == [expected]

    def test_timeout_message_reaches_the_partial_participant_only(self) -> None:
        """時間切れ文は、準備しなかった相手でなく部分参加者だけへ届く。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        stage = runtime._simulation_service._sync_action_resolver_stage
        stage._registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=0)

        runtime.advance_tick()
        runtime.advance_tick()

        expected = "レバーが元の位置に戻る音がした。タイミングを合わせ直す必要がある。"
        assert self._result_messages(runtime, PlayerId(1)) == [expected]
        assert self._result_messages(runtime, PlayerId(2)) == []


def _runtime_executor(runtime) -> SpotGraphToolExecutor:
    """実 runtime と同じ service 群を使う prepare_action executor を組み立てる。"""
    services = SpotGraphWorldServices(
        interaction=runtime._interaction_service,
        exploration=runtime._exploration_service,
        world_flags=runtime._world_flag_state,
        game_end_evaluator=GameEndConditionEvaluator(),
        exploration_progress=runtime._exploration_progress,
        movement=runtime._movement_service,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        event_publisher=runtime._speech_event_publisher,
        sync_action_groups=runtime.scenario.synchronized_action_groups,
        time_provider=runtime._time_provider,
        spot_graph_repository=runtime._spot_graph_repo,
        sync_action_registry=runtime._simulation_service._sync_action_resolver_stage._registry,
    )


class TestPrepareActionValidatesParticipantsAndTheDeclaredInteraction:
    """prepare_action が通常操作と同じ空間・対象・前提条件を満たす者だけを登録する。"""

    def test_two_players_prepare_different_actions_and_complete(self) -> None:
        """異なる二人が別々の操作を準備すると、同期グループが完成する。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        executor = _runtime_executor(runtime)

        left = executor._prepare_action(1, {"action_name": "pull_lever_left"})
        right = executor._prepare_action(2, {"action_name": "pull_lever_right"})
        runtime.advance_tick()

        assert left.success is True
        assert right.success is True
        assert "vault_unlocked" in runtime._world_flag_state.as_frozen_set()

    def test_one_player_cannot_fill_two_required_roles(self) -> None:
        """一人が二つ目を準備すると理由つきで拒否され、完成人数には数えない。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        executor = _runtime_executor(runtime)

        first = executor._prepare_action(1, {"action_name": "pull_lever_left"})
        second = executor._prepare_action(1, {"action_name": "pull_lever_right"})
        runtime.advance_tick()

        assert first.success is True
        assert second.success is False
        assert second.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "別の参加者" in second.message
        assert "vault_unlocked" not in runtime._world_flag_state.as_frozen_set()

    def test_prepare_is_rejected_when_the_target_object_is_not_here(self) -> None:
        """操作を持つ対象物が現在地に無ければ、存在しない準備として拒否する。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        graph = runtime._spot_graph_repo.find_graph()
        vault_id = runtime.id_mapper.get_int("spot", "vault")
        graph.teleport_entity(EntityId.create(1), SpotId.create(vault_id))
        executor = _runtime_executor(runtime)

        result = executor._prepare_action(1, {"action_name": "pull_lever_left"})

        assert result.success is False
        assert result.error_code == "INTERACTION_ACTION_NOT_FOUND"
        assert "現在地" in result.message

    def test_prepare_uses_the_interaction_precondition_at_the_current_spot(self) -> None:
        """対象物が見つかっても AT_SPOT_IS が不成立なら、通常操作と同じ理由で拒否する。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        lever_room_id = SpotId.create(runtime.id_mapper.get_int("spot", "lever_room"))
        vault_id = SpotId.create(runtime.id_mapper.get_int("spot", "vault"))
        lever_interior = runtime._spot_interior_repo.find_by_spot_id(lever_room_id)
        vault_interior = runtime._spot_interior_repo.find_by_spot_id(vault_id)
        assert lever_interior is not None
        assert vault_interior is not None
        runtime._spot_interior_repo.save(
            vault_id,
            type(vault_interior)(
                sub_locations=vault_interior.sub_locations,
                objects=(lever_interior.objects[0],),
                ground_items=vault_interior.ground_items,
                discoverable_items=vault_interior.discoverable_items,
            ),
        )
        runtime._spot_graph_repo.find_graph().teleport_entity(
            EntityId.create(1), vault_id
        )
        executor = _runtime_executor(runtime)

        result = executor._prepare_action(1, {"action_name": "pull_lever_left"})

        assert result.success is False
        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "左レバーの前" in result.message
