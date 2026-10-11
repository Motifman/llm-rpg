"""出力の上限トークン数を設定で決め、主ターンの呼び出しに top-level の max_tokens として送り、prompt dataset の request に残すことを保証する (Issue #1595)。

thinking のトークン数は出力の上限に数えられる。mine_v1_005 では thinking のトークン数と
呼び出しの時間の相関が 0.96 で、長く考えた回が 95 秒の上限で止まった。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCallContext,
    PromptDatasetCaptureSink,
)
from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_config,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

_COMPLETION = "ai_rpg_world.infrastructure.llm.litellm_client.litellm.completion"
_MODEL = "openrouter/deepseek/deepseek-v4.1-flash"


@pytest.fixture(autouse=True)
def isolate_litellm_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(
        "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
        lambda: None,
    )



def _model_response():
    import litellm

    return litellm.ModelResponse(
        choices=[
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "wait", "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    )


def _sent_kwargs(client: LiteLLMClient, **invoke_kwargs) -> dict:
    with patch(_COMPLETION) as mock_completion:
        mock_completion.return_value = _model_response()
        client.invoke(messages=[{"role": "user", "content": "x"}], tools=[], **invoke_kwargs)
    return mock_completion.call_args.kwargs


class TestClientSendsTheOutputCap:
    """LiteLLMClient が出力の上限を送るかどうか。"""

    def test_configured_cap_is_sent_as_max_tokens(self) -> None:
        """max_output_tokens=4096 で作ったクライアントは、主ターンの呼び出しに max_tokens=4096 を送る。"""
        client = LiteLLMClient(
            model=_MODEL, api_key="sk-x", reasoning_effort="minimal", max_output_tokens=4096
        )

        kwargs = _sent_kwargs(client)

        assert kwargs["max_tokens"] == 4096

    def test_cap_is_not_sent_when_unset(self) -> None:
        """max_output_tokens を渡さないと、max_tokens の欄を送らない。従来の run と同じ要求になる。"""
        client = LiteLLMClient(model=_MODEL, api_key="sk-x", reasoning_effort="minimal")

        kwargs = _sent_kwargs(client)

        assert "max_tokens" not in kwargs

    def test_cap_does_not_replace_the_reasoning_effort(self) -> None:
        """上限を送っても、reasoning の effort は extra_body にそのまま載る。effort と同時に送れない reasoning.max_tokens は使わない。"""
        client = LiteLLMClient(
            model=_MODEL, api_key="sk-x", reasoning_effort="minimal", max_output_tokens=4096
        )

        kwargs = _sent_kwargs(client)

        assert kwargs["extra_body"]["reasoning"] == {"effort": "minimal"}

    def test_cap_passes_litellm_param_check_for_unlisted_model(self) -> None:
        """LiteLLM のモデル表に無いモデルでも、max_tokens は送信前の引数検査を通り、送る値に残る。"""
        from litellm.utils import get_optional_params

        client = LiteLLMClient(
            model=_MODEL, api_key="sk-x", reasoning_effort="minimal", max_output_tokens=4096
        )
        kwargs = _sent_kwargs(client)

        optional_params = get_optional_params(
            model="deepseek/deepseek-v4.1-flash",
            custom_llm_provider="openrouter",
            max_tokens=kwargs["max_tokens"],
        )

        assert optional_params["max_tokens"] == 4096

    @pytest.mark.parametrize("value", [0, -1])
    def test_non_positive_cap_is_rejected(self, value: int) -> None:
        """1 未満の上限は作る時点で ValueError にする。0 を「送らない」と読むと、設定の誤りが静かに消える。"""
        with pytest.raises(ValueError, match="max_output_tokens"):
            LiteLLMClient(model=_MODEL, api_key="sk-x", max_output_tokens=value)


class TestPromptDatasetKeepsTheCap:
    """送った上限が prompt dataset の request に残るか。"""

    def test_calls_jsonl_request_has_the_sent_cap(self, tmp_path) -> None:
        """上限を送った呼び出しは、calls.jsonl の request.kwargs に max_tokens の値が残る。"""
        sink = PromptDatasetCaptureSink(run_dir=tmp_path, run_id="run1", run_metadata={})
        context = PromptDatasetCallContext(
            llm_call_id="call-1",
            run_id="run1",
            world_id=1,
            being_id="being_w1_p1",
            player_id=1,
            persona_id="persona:sha256:test",
            character_name="ハル",
            turn_index=1,
            world_tick=1,
            phase="one_step",
        )
        client = LiteLLMClient(
            model=_MODEL, api_key="sk-x", reasoning_effort="minimal", max_output_tokens=4096
        )

        _sent_kwargs(
            client, prompt_capture_context=SimpleNamespace(sink=sink, context=context)
        )

        rows = [
            json.loads(line)
            for line in (tmp_path / "prompt_dataset" / "calls.jsonl").read_text().splitlines()
        ]
        assert rows[0]["request"]["kwargs"]["max_tokens"] == 4096


class TestRuntimeConfigCarriesTheCap:
    """profile の runtime_config の LLM_MAX_OUTPUT_TOKENS が、クライアントまで届くか。"""

    def test_key_resolves_to_the_config(self) -> None:
        """LLM_MAX_OUTPUT_TOKENS="4096" は llm_max_output_tokens=4096 に解決される。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_MAX_OUTPUT_TOKENS": "4096"})

        assert cfg.llm_max_output_tokens == 4096

    def test_unset_key_resolves_to_none(self) -> None:
        """LLM_MAX_OUTPUT_TOKENS を書かない profile は llm_max_output_tokens=None になり、上限を送らない。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})

        assert cfg.llm_max_output_tokens is None

    @pytest.mark.parametrize("raw", ["0", "-5", "many"])
    def test_invalid_key_fails_fast(self, raw: str) -> None:
        """1 未満や整数でない値は、run を始める前に ValueError で止める (design_decisions #10)。"""
        with pytest.raises(ValueError, match="LLM_MAX_OUTPUT_TOKENS="):
            ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_MAX_OUTPUT_TOKENS": raw})

    def test_factory_passes_the_cap_to_the_litellm_client(self) -> None:
        """litellm のクライアントを組むとき、設定の上限がクライアントに渡り、呼び出しで送られる。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "LLM_CLIENT": "litellm",
                "LLM_MODEL": _MODEL,
                "LLM_MAX_OUTPUT_TOKENS": "4096",
            }
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-x"}):
            client = create_llm_client_from_config(cfg)

            kwargs = _sent_kwargs(client)

        assert kwargs["max_tokens"] == 4096
