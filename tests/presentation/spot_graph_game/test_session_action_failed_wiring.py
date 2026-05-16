"""脱出セッション作成時に ActionFailed 観測 wiring が機能することのテスト。

Issue #154 デモ実走で DoD #5 が Fail だった (failure_observer が
spot_graph_wiring から auto-wire されていなかった) のを解消する変更の
回帰防止。

検証:
- create_session で組み立てた wiring に ``action_failed_emitter`` /
  ``intent_id_generator`` が注入される
- LLM が無効なラベルを指定したとき、当該プレイヤーへ ``type: action_failed``
  観測が届く
- LLM API レベルの失敗 (NO_TOOL_CALL 等) は観測化されない (emitter の
  既存挙動)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import (
    StubLlmClient,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


def _scenario_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "scenarios"


def _action_failed_observations(obs_buffer, player_id: PlayerId) -> list:
    entries = list(obs_buffer.get_observations(player_id))
    return [
        e
        for e in entries
        if (getattr(getattr(e, "output"), "structured") or {}).get("type")
        == "action_failed"
    ]


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
        CharacterCreateRequest(name="ActionFailed 配線確認用キャラクター")
    )
    summary = mgr.create_session(
        SessionCreateRequest(
            world_id="relay_puzzle_demo", character_ids=[char.id]
        ),
    )
    state = mgr._sessions[summary.session_id]
    # llm_wiring の LLM client を Stub に差し替え
    state.llm_wiring.llm_client = stub
    return state


class TestSessionActionFailedWiring:
    """``create_session`` が ActionFailed wire を組み立てる挙動。"""

    def test_emitter_and_id_generator_are_wired_on_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """セッションの llm_wiring に emitter と id_generator が注入される。"""
        state = _create_session_with_stub(
            monkeypatch, tmp_path, StubLlmClient()
        )
        wiring = state.llm_wiring
        assert wiring.action_failed_emitter is not None
        assert wiring.intent_id_generator is not None

    def test_invalid_destination_label_emits_action_failed_observation(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """spot_graph_travel_to に未知ラベルを指定した失敗が観測になる。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "存在しない扉"},
            }
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime
        player_ids = runtime.get_player_ids()
        assert len(player_ids) >= 1
        target_pid = player_ids[0]

        # run_turn を直接呼ぶ (LLM 呼び出しは Stub で固定)
        result = state.llm_wiring.run_turn(target_pid)
        assert result.success is False
        assert result.error_code == "INVALID_DESTINATION_LABEL"

        # action_failed 観測が当該プレイヤーへ届く
        observed = _action_failed_observations(runtime._obs_buffer, target_pid)
        assert len(observed) == 1
        structured = observed[0].output.structured
        assert structured["error_code"] == "INVALID_DESTINATION_LABEL"
        assert structured["tool_name"] == "spot_graph_travel_to"
        assert "intent_id" in structured

    def test_other_player_does_not_receive_action_failed_observation(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """ActionFailed 観測は失敗プレイヤー本人のみに届き、他プレイヤーには届かない。

        bystander には事前に無関係な観測を 1 件投入し、buffer のキーが正しく
        プレイヤーごとに分かれていることまで検証する (空 buffer を返すだけの
        実装でも通る weak test を避ける)。
        """
        from datetime import datetime, timezone

        from ai_rpg_world.application.observation.contracts.dtos import (
            ObservationEntry,
            ObservationOutput,
        )

        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "存在しない扉"},
            }
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime
        player_ids = runtime.get_player_ids()
        assert len(player_ids) >= 2

        actor = player_ids[0]
        bystander = player_ids[1]

        # bystander に "noise" な観測を事前に入れて、buffer のキー分離を確認
        noise = ObservationEntry(
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            output=ObservationOutput(
                prose="(bystander baseline)",
                structured={"type": "noise"},
            ),
        )
        runtime._obs_buffer.append(bystander, noise)

        state.llm_wiring.run_turn(actor)

        # actor: action_failed 観測 1 件
        assert len(_action_failed_observations(runtime._obs_buffer, actor)) == 1
        # bystander: action_failed は届かない (noise は残る → 空 buffer の偽 pass を排除)
        assert _action_failed_observations(runtime._obs_buffer, bystander) == []
        bystander_entries = list(
            runtime._obs_buffer.get_observations(bystander)
        )
        assert any(
            (e.output.structured or {}).get("type") == "noise"
            for e in bystander_entries
        )

    def test_no_tool_call_failure_is_not_emitted(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """LLM が tool を返さなかった (NO_TOOL_CALL) ケースは観測化しない。

        LLM API レベルの失敗は emitter の除外リスト (_NON_ACTION_FAILURE_CODES)
        に含まれるため observation 化されない。
        """
        stub = StubLlmClient(tool_call_to_return=None)  # invoke は None を返す
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime
        target_pid = runtime.get_player_ids()[0]

        result = state.llm_wiring.run_turn(target_pid)
        assert result.success is False
        assert result.error_code == "NO_TOOL_CALL"
        # action_failed は届かない
        assert _action_failed_observations(runtime._obs_buffer, target_pid) == []

    def test_successful_tool_call_does_not_emit_action_failed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """success=True の DTO に対しては action_failed が emit されない。

        失敗パスだけ覆って ``if not result.success:`` ガードが消えるリグレッ
        ションを防ぐため、成功パスのベースラインも明示的にテストする。
        """
        # spot_graph_explore は引数不要で必ず success を返す (探索結果が空でも
        # success=True、message="新しい発見はなかった")
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_explore",
                "arguments": {},
            }
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime
        target_pid = runtime.get_player_ids()[0]

        result = state.llm_wiring.run_turn(target_pid)
        assert result.success is True
        # action_failed observation は届かない
        assert (
            _action_failed_observations(runtime._obs_buffer, target_pid) == []
        )

    def test_empty_tool_name_skips_action_failed_emission(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """LLM が空 tool_name (``{"name": ""}``) を返した失敗は emit しない。

        Intent VO は非空 str を要求する。empty を ``"unknown"`` で穴埋めすると
        観測の tool_name が偽情報になるので、emission をスキップ + warning ログ
        の方針。
        """
        stub = StubLlmClient(
            tool_call_to_return={"name": "", "arguments": {}}
        )
        state = _create_session_with_stub(monkeypatch, tmp_path, stub)
        runtime = state.runtime
        target_pid = runtime.get_player_ids()[0]

        result = state.llm_wiring.run_turn(target_pid)
        # tool_name 空 → _execute_tool で「未対応のツール」DTO が返る
        assert result.success is False
        # action_failed は届かない (skip)
        assert (
            _action_failed_observations(runtime._obs_buffer, target_pid) == []
        )
