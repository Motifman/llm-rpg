"""busy 中の "heavy tool" で travel が中断されることの検証。

free tool (speech / memo / listen / wait / explore) は通常通り通る。
heavy tool (interact / use_item / attack / travel_to / give / pickup / drop)
が来ると travel をキャンセルして current_spot で at_rest に戻す。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId


def _put_player_traveling(
    runtime, player_id_value: int, current_spot: int = 1
) -> None:
    """runtime の player_status_repo に traveling 状態のプレイヤーを書き込む。"""
    pid = PlayerId(player_id_value)
    status = runtime._player_status_repo.find_by_id(pid)
    assert status is not None, "session の player が存在しません"
    status.set_spot_navigation_state(
        PlayerSpotNavigationState.begin_travel(
            route=(SpotId(current_spot), SpotId(99)),
            leg_connection_ids=(ConnectionId.create(1),),
            leg_travel_ticks=(3,),
        )
    )
    runtime._player_status_repo.save(status)


class TestBusyInterruptCategorization:
    """_BUSY_FREE_TOOLS の境界を検証する (構造的テスト)。"""

    def test_BUSY_FREE_TOOLS_に_想定の_tool_が含まれる(self) -> None:
        from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
            _WorldLlmWiring,
        )
        free = _WorldLlmWiring._BUSY_FREE_TOOLS
        assert TOOL_NAME_SPEECH in free
        assert TOOL_NAME_SPOT_GRAPH_LISTEN in free
        assert TOOL_NAME_SPOT_GRAPH_WAIT in free

    def test_重い_tool_は_BUSY_FREE_TOOLS_に_含まれない(self) -> None:
        from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
            _WorldLlmWiring,
        )
        free = _WorldLlmWiring._BUSY_FREE_TOOLS
        for tool in (
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
        ):
            assert tool not in free


class TestMaybeInterruptBusy:
    """_maybe_interrupt_busy の挙動。"""

    def test_traveling_中に_heavy_tool_で_中断される(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        runtime = state.runtime
        wiring = state.llm_wiring
        player_id_value = int(runtime.scenario.player_spawns[0].player_id)
        _put_player_traveling(runtime, player_id_value)

        # 中断発火 (interact = heavy)
        was_interrupted, snapshot = wiring._maybe_interrupt_busy(
            PlayerId(player_id_value), TOOL_NAME_SPOT_GRAPH_INTERACT
        )
        assert was_interrupted is True
        assert snapshot is not None
        assert snapshot.is_traveling is True
        status = runtime._player_status_repo.find_by_id(PlayerId(player_id_value))
        assert status.spot_navigation_state.is_traveling is False

    def test_traveling_中に_free_tool_は_中断されない(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        runtime = state.runtime
        wiring = state.llm_wiring
        player_id_value = int(runtime.scenario.player_spawns[0].player_id)
        _put_player_traveling(runtime, player_id_value)

        # 発話で中断しない (free tool)
        was_interrupted, snapshot = wiring._maybe_interrupt_busy(
            PlayerId(player_id_value), TOOL_NAME_SPEECH
        )
        assert was_interrupted is False
        assert snapshot is None
        status = runtime._player_status_repo.find_by_id(PlayerId(player_id_value))
        assert status.spot_navigation_state.is_traveling is True

    def test_traveling_でない_なら_何もしない(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        runtime = state.runtime
        wiring = state.llm_wiring
        player_id_value = int(runtime.scenario.player_spawns[0].player_id)
        # traveling 設定なし

        was_interrupted, snapshot = wiring._maybe_interrupt_busy(
            PlayerId(player_id_value), TOOL_NAME_SPOT_GRAPH_INTERACT
        )
        assert was_interrupted is False
        assert snapshot is None


class TestRestoreNavStateOnFailure:
    """Review HIGH 1 対応: tool が失敗したら travel を復元する。"""

    def test_traveling_中に_travel_to_でも_中断される(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """別の travel_to が来たら現在の travel を中断する。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        runtime = state.runtime
        wiring = state.llm_wiring
        player_id_value = int(runtime.scenario.player_spawns[0].player_id)
        _put_player_traveling(runtime, player_id_value)

        was_interrupted, snapshot = wiring._maybe_interrupt_busy(
            PlayerId(player_id_value), TOOL_NAME_SPOT_GRAPH_TRAVEL_TO
        )
        assert was_interrupted is True
        assert snapshot is not None and snapshot.is_traveling is True

    def test_restore_nav_state_で_travel_状態が_復元される(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        runtime = state.runtime
        wiring = state.llm_wiring
        player_id_value = int(runtime.scenario.player_spawns[0].player_id)
        _put_player_traveling(runtime, player_id_value)

        # 中断 → ロールバック
        _, snapshot = wiring._maybe_interrupt_busy(
            PlayerId(player_id_value), TOOL_NAME_SPOT_GRAPH_INTERACT
        )
        assert snapshot is not None
        # 中断直後は at_rest
        status = runtime._player_status_repo.find_by_id(PlayerId(player_id_value))
        assert status.spot_navigation_state.is_traveling is False
        # 復元
        wiring._restore_nav_state(PlayerId(player_id_value), snapshot)
        status = runtime._player_status_repo.find_by_id(PlayerId(player_id_value))
        assert status.spot_navigation_state.is_traveling is True
        assert status.spot_navigation_state.route == snapshot.route
