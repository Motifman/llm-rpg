"""脱出セッションでの ``spot_graph_listen`` dispatch のテスト (N1)。

Issue #154 のデモ実走で ``spot_graph_listen`` が常に ``UNSUPPORTED_TOOL`` を
返してループを引き起こしていた配線漏れの修正。LLM の tools リストに
``LISTEN_DEFINITION`` が存在するのに ``_EscapeGameLlmWiring._execute_tool``
に dispatch case が無く、毎回 fallback の "未対応のツール" 応答になっていた。

本テストでは:
- listen が UNSUPPORTED_TOOL ではなく success DTO を返すこと
- runtime.do_listen が呼ばれること
- success message が件数ベースで構築されること

を保証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import (
    StubLlmClient,
)
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


def _scenario_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "scenarios"


def _create_session_with_stub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stub: StubLlmClient
):
    """tick loop を無効化し、StubLlmClient を使うセッションを作る。"""
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=_scenario_dir(),
        characters_path=tmp_path / "characters.json",
    )
    char = mgr.create_character(
        CharacterCreateRequest(name="listen 配線テスト用キャラクター")
    )
    summary = mgr.create_session(
        SessionCreateRequest(
            world_id="relay_puzzle_demo", character_ids=[char.id]
        ),
    )
    state = mgr._sessions[summary.session_id]
    state.llm_wiring.llm_client = stub
    return state


class TestSessionListenWiring:
    """``spot_graph_listen`` ツールが正しく dispatch される挙動。"""

    def test_listen_does_not_return_unsupported_tool(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """spot_graph_listen が success=True で返り、UNSUPPORTED_TOOL にならない。

        Issue #154 デモで観測された配線漏れ (`UNSUPPORTED_TOOL`) の回帰防止。
        """
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_listen",
                "arguments": {"inner_thought": "耳を澄ます"},
            }
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime
        target_pid = runtime.get_player_ids()[0]

        result = state.llm_wiring.run_turn(target_pid)

        # UNSUPPORTED_TOOL でないことを assert (主目的)
        assert result.error_code != "UNSUPPORTED_TOOL", (
            f"spot_graph_listen が UNSUPPORTED_TOOL に化けている (配線漏れ): "
            f"{result.message}"
        )
        # 成功 DTO で返る
        assert result.success is True
        # 件数ベースのメッセージのいずれか
        assert (
            "聞こえなかった" in result.message
            or "観測として届いた" in result.message
        )

    def test_listen_success_message_when_no_sound(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """``relay_puzzle_demo`` の制御室は SILENT なので「聞こえなかった」メッセージ。

        scenario JSON で sound_intensity を明示していないスポットは SILENT 扱い。
        """
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_listen",
                "arguments": {"inner_thought": "耳を澄ます"},
            }
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]

        result = state.llm_wiring.run_turn(target_pid)
        assert result.success is True
        assert "聞こえなかった" in result.message

    def test_listen_event_count_isolates_new_events_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """事前に stale event が graph に積まれていても、listen の戻りは
        新規 event 差分だけをカウントする (review HIGH-1 回帰防止)。

        graph.event queue は他経路 (tick 内 stage / 並行 do_* 等) が
        積んだ stale event を持ちうる。snapshot 差分で正しく分離する。
        """
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_listen",
                "arguments": {"inner_thought": "耳を澄ます"},
            }
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime

        # 事前に stale event を 1 件積む (他経路の混入を模倣)
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            SpotExploredEvent,
        )
        from ai_rpg_world.domain.world_graph.value_object.entity_id import (
            EntityId,
        )

        graph = runtime._spot_graph_repo.find_graph()
        target_pid = runtime.get_player_ids()[0]
        eid = EntityId.create(int(target_pid))
        spot_id = graph.get_entity_spot(eid)
        stale_event = SpotExploredEvent.create(
            aggregate_id=graph._graph_id,
            aggregate_type="SpotGraphAggregate",
            entity_id=eid,
            spot_id=spot_id,
            discoveries=(),
        )
        graph.add_event(stale_event)
        runtime._spot_graph_repo.save(graph)

        # listen は stale event を含めない差分だけを数える: silent spot
        # でも「N 箇所からの音が観測として届いた」にならず「聞こえなかった」
        result = state.llm_wiring.run_turn(target_pid)
        assert result.success is True
        assert "聞こえなかった" in result.message

    def test_listen_does_not_emit_action_failed_observation(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """成功 listen は action_failed 観測を生成しない (success path の確認)。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_listen",
                "arguments": {"inner_thought": "耳を澄ます"},
            }
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime
        target_pid = runtime.get_player_ids()[0]
        state.llm_wiring.run_turn(target_pid)

        # observation buffer に action_failed 観測が無いこと
        entries = list(runtime._obs_buffer.get_observations(target_pid))
        action_failed = [
            e
            for e in entries
            if (e.output.structured or {}).get("type") == "action_failed"
        ]
        assert action_failed == []
