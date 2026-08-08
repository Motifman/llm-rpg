"""episodic 記憶を無効にした実験でも prompt dataset を最初の呼び出しから保存する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCaptureSink,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.demos._world_runtime_helpers import create_world_runtime_session


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "station_drill.json"
)


def _config(*, capture_enabled: bool) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.for_tests(
        episodic_enabled=False,
        prompt_dataset_capture_enabled=capture_enabled,
        prompt_dataset_capture_failure_policy="warn",
    )


class TestPromptCaptureWithoutEpisodicMemory:
    """記憶機能ではなく記録機能の要件として Being 配線を確立する。"""

    def test_runtime_provisions_beings_when_capture_is_enabled(self) -> None:
        """capture 有効なら episodic 無効でも全参加者の being_id を起動時に解決できる。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_config(capture_enabled=True))

        assert runtime.aux_being_resolver is not None
        assert runtime.aux_being_default_world_id is not None
        for spawn in runtime.scenario.player_spawns:
            being_id = runtime.aux_being_resolver.resolve_being_id(
                runtime.aux_being_default_world_id,
                PlayerId(int(spawn.player_id)),
            )
            assert being_id is not None

    def test_first_llm_call_captures_the_provisioned_being_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """実 runtime の最初の LLM 呼び出しは resolver 由来の being_id を保存する。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "wait",
                "arguments": {
                    "inner_thought": "まず周囲の動きを見る。",
                    "expected_result": "少し待って状況が変わる。",
                },
            }
        )
        state = create_world_runtime_session(
            monkeypatch,
            tmp_path,
            stub,
            world_id="station_drill",
            runtime_config=_config(capture_enabled=True),
        )
        sink = PromptDatasetCaptureSink(
            run_dir=tmp_path,
            run_id="capture-without-episodic",
            run_metadata={"profile": "test"},
            failure_policy="warn",
        )
        state.llm_wiring.prompt_dataset_sink = sink
        player_id = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))

        state.llm_wiring.run_turn(player_id)

        row = json.loads(
            (tmp_path / "prompt_dataset" / "calls.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        expected = state.runtime.aux_being_resolver.resolve_being_id(
            state.runtime.aux_being_default_world_id,
            player_id,
        )
        assert expected is not None
        assert row["being_id"] == str(expected.value)

    def test_capture_disabled_does_not_wire_beings_early(self) -> None:
        """capture と episodic がともに無効なら従来どおり補助 Being 配線を遅延する。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_config(capture_enabled=False),
        )

        assert runtime.aux_being_resolver is None
        assert runtime.aux_being_default_world_id is None

    def test_capture_does_not_change_exposed_tools(self) -> None:
        """記録の有効化は同じ player に提示する tool 名を増減させない。"""
        without_capture = create_world_runtime(
            _SCENARIO_PATH,
            config=_config(capture_enabled=False),
        )
        with_capture = create_world_runtime(
            _SCENARIO_PATH,
            config=_config(capture_enabled=True),
        )
        player_id = PlayerId(int(with_capture.scenario.player_spawns[0].player_id))

        names_without = {
            definition.name
            for definition in without_capture.get_tool_definitions(player_id=player_id)
        }
        names_with = {
            definition.name
            for definition in with_capture.get_tool_definitions(player_id=player_id)
        }

        assert names_with == names_without
