"""create_world_runtime が組んだ記憶の部品の LLM クライアントが、呼び出しを runtime の trace へ aux_llm_call として届けることを保証する (#1617)。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from tests.runtime_config_helpers import runtime_config

from ai_rpg_world.application.trace import TraceEventKind

_REPO = Path(__file__).resolve().parents[3]
_SCENARIO = _REPO / "data" / "scenarios" / "forbidden_library_demo.json"
_FACTORIES = frozenset(
    {"create_llm_client_from_config", "create_typed_judgment_port_from_config"}
)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
        lambda: None,
    )


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None:
        self.events.append((kind, payload))


def _runtime_with_recorder() -> tuple[Any, _Recorder]:
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    config = runtime_config(
        llm_client_kind="litellm",
        llm_api_key="sk-test",
    )
    runtime = create_world_runtime(_SCENARIO, config=config)
    recorder = _Recorder()
    runtime.set_trace_recorder(recorder)
    return runtime, recorder


def _json_response() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, cost=0.0001),
    )


def _aux_components(recorder: _Recorder) -> list[str]:
    return [p["component"] for kind, p in recorder.events if kind == TraceEventKind.AUX_LLM_CALL]


class TestNewMemoryComponentsReachTheRuntimeTrace:
    """新しい記憶の部品 (短期記憶の要約、エピソードの書き起こし) の呼び出しが runtime の trace に届くことを保証する。"""

    def test_rolling_summary_call_is_traced_as_short_term_summary(self) -> None:
        """rolling_summary の要約が LLM を呼ぶと、runtime の recorder に component=short_term_summary の aux_llm_call が 1 件届く。"""
        runtime, recorder = _runtime_with_recorder()
        port = runtime._short_term_memory._service._port

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _json_response()
            port.complete_short_term_summary_json([{"role": "user", "content": "x"}])

        assert _aux_components(recorder) == ["short_term_summary"]

    def test_episode_writing_call_is_traced_as_episode_writing(self) -> None:
        """エピソードの書き起こしが LLM を呼ぶと、runtime の recorder に component=episode_writing の aux_llm_call が 1 件届く。"""
        runtime, recorder = _runtime_with_recorder()
        completion = runtime._player_episode_writing._writer._completion

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _json_response()
            completion.complete_episode_writing_json([{"role": "user", "content": "x"}])

        assert _aux_components(recorder) == ["episode_writing"]


class TestEveryProductionClientIsGivenTheSink:
    """src の中で LLM クライアントと Jev を組む箇所が、記録先を渡し忘れていないことを保証する。"""

    def test_every_factory_call_in_src_passes_aux_call_sink(self) -> None:
        """src 配下の create_llm_client_from_config / create_typed_judgment_port_from_config の呼び出しはすべて aux_call_sink= を渡す。"""
        calls: list[str] = []
        missing: list[str] = []
        for path in sorted((_REPO / "src").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name not in _FACTORIES:
                    continue
                where = f"{path.relative_to(_REPO)}:{node.lineno}"
                calls.append(where)
                if not any(k.arg == "aux_call_sink" for k in node.keywords):
                    missing.append(where)

        assert len(calls) >= 6
        assert missing == []
