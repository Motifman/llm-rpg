"""二人で合わせる操作は、interact から「自分の側を受け持つ」登録になる。

別ツール (prepare_action) に用意した入口は 13 run で一度も選ばれず、run 003 では
弁を触った 5 回が全部 interact だった。世界は「レバーに手をかけた」と返しながら
何も登録しておらず、燃料が失われた。対象行に出ている名前を interact に渡す形が
エージェントの自然な言い方なので、そこに登録層を繋ぐ。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = (
    Path(__file__).resolve().parents[5] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _SENA, _KUZE = (PlayerId(i) for i in (1, 2, 3))
_RESTORED = "レバーが噛み合い、配管に熱が戻る音がした。"


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_DRILL)
    rt.do_interact_with_item(
        _KUZE,
        ItemSpecId.create(rt.id_mapper.get_int("item_spec", "control_terminal")),
        "freeze_fuel",
    )
    _move(rt, _MORI, "fuel_bay")
    _move(rt, _SENA, "machine_room")
    return rt


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.teleport_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _executor(runtime) -> SpotGraphToolExecutor:
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
        sync_action_registry=(
            runtime._simulation_service._sync_action_resolver_stage._registry
        ),
        prepare_action_command_scope_factory=(
            runtime._prepare_action_command_scope_factory
        ),
        speech_service=runtime._speech_service,
        runtime=runtime,
    )


def _interact(runtime, executor, player_id: PlayerId, object_str_id: str, action: str, **extra):
    return executor._interact(
        player_id.value,
        {
            "object_id": runtime.id_mapper.get_int("object", object_str_id),
            "action_name": action,
            "inner_thought": "弁を受け持つ",
            **extra,
        },
    )


def _flags(runtime) -> set[str]:
    return set(runtime._world_flag_state.as_frozen_set())


def _prose(runtime, player_id: PlayerId) -> list[str]:
    return [e.output.prose for e in runtime._obs_buffer.get_observations(player_id)]


class TestInteractRegistersTheListenerSide:
    """同期操作の名前を interact に渡すと、効果ではなく準備の登録になる。"""

    def test_interacting_with_a_valve_registers_a_preparation(self, runtime) -> None:
        """弁を interact すると sync_prep と prepared の両フラグが立ち、結果文は「まだ動いていない」と言う。"""
        result = _interact(runtime, _executor(runtime), _MORI, "fuel_thaw_valve", "open_thaw_valve")

        assert result.success is True
        assert "まだ動いていない" in result.message
        flags = _flags(runtime)
        assert any(f.startswith("sync_prep:open_thaw_valve:1:") for f in flags)
        assert "prepared:open_thaw_valve:1" in flags

    def test_two_listeners_interacting_in_the_same_tick_restore_the_fuel(self, runtime) -> None:
        """別々の 2 人が同 tick に両方の弁を interact すると、tick の終わりに凍結が解ける。

        run 003 の tick 11 と同じ場面。当時は 5 回とも登録されず燃料が失われた。
        """
        executor = _executor(runtime)
        _interact(runtime, executor, _MORI, "fuel_thaw_valve", "open_thaw_valve")
        _interact(runtime, executor, _SENA, "oil_feed_valve", "open_oil_feed_valve")

        runtime.advance_tick()

        assert "fuel_frozen" not in _flags(runtime)
        assert "fuel_restored" in _flags(runtime)
        assert any(_RESTORED in text for text in _prose(runtime, _MORI))

    def test_one_listener_cannot_take_both_sides_through_interact(self, runtime) -> None:
        """同じ人が両方の弁を interact しても、2 つ目は拒否され 1 人では完成しない。"""
        executor = _executor(runtime)
        _move(runtime, _MORI, "fuel_bay")
        _interact(runtime, executor, _MORI, "fuel_thaw_valve", "open_thaw_valve")
        _move(runtime, _MORI, "machine_room")

        second = _interact(runtime, executor, _MORI, "oil_feed_valve", "open_oil_feed_valve")

        assert second.success is False
        assert second.error_code == "INTERACTION_PRECONDITION_FAILED"
        runtime.advance_tick()
        assert "fuel_frozen" in _flags(runtime)

    def test_say_inline_still_reaches_the_room_when_a_valve_is_taken(self, runtime) -> None:
        """弁を受け持ちながらの一言 (say_inline) は、通常の interact と同じく同室者へ届く。"""
        _move(runtime, _KUZE, "fuel_bay")
        executor = _executor(runtime)

        _interact(
            runtime, executor, _MORI, "fuel_thaw_valve", "open_thaw_valve",
            say_inline="解氷弁は俺が持つ。",
        )

        assert any("解氷弁は俺が持つ。" in text for text in _prose(runtime, _KUZE))

    def test_an_ordinary_interaction_still_runs_its_effects(self, runtime) -> None:
        """同期グループに属さない操作は、これまでどおり効果が走る (**正の対照**)。"""
        _move(runtime, _MORI, "hall")
        executor = _executor(runtime)

        result = _interact(runtime, executor, _MORI, "duty_board", "read_board")

        assert result.success is True
        assert "点検" in result.message
        assert not any(f.startswith("sync_prep:") for f in _flags(runtime))


class TestNoSeparateToolRemains:
    """準備のための別ツールは世界に無い。"""

    def test_prepare_action_is_not_in_the_tool_list_of_a_world_with_sync_groups(self, runtime) -> None:
        """同期グループを宣言した世界でも、ツール一覧に prepare_action は無い。"""
        names = {d.name for d in runtime.get_tool_definitions(for_every_player=True)}

        assert "prepare_action" not in names
        assert "interact" in names
