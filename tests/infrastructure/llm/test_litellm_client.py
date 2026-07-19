"""LiteLLMClient のテスト（正常・境界・例外・初期化）"""

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolate_litellm_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """開発者の .env / OPENAI_API_BASE / OPENROUTER_* がテスト混入しないようにする"""
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    # OpenRouter routing 系: 開発者のシェルで設定されていてもテスト挙動を汚さない
    monkeypatch.delenv("OPENROUTER_PROVIDER", raising=False)
    monkeypatch.delenv("OPENROUTER_QUANTIZATION", raising=False)
    monkeypatch.delenv("OPENROUTER_REQUIRE_PARAMS", raising=False)
    # reasoning effort: 開発者シェルの LLM_REASONING_EFFORT がテストに混入すると
    # 既定 "none" 前提のアサーションが揺れるので隔離する。
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(
        "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
        lambda: None,
    )


from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient


def _make_tool_call_response(name: str, arguments: dict):
    """litellm.completion が返す response のモックを組み立てる。"""
    func = MagicMock()
    func.name = name
    func.arguments = json.dumps(arguments) if arguments else "{}"
    tc = MagicMock()
    tc.function = func
    msg = MagicMock()
    msg.tool_calls = [tc]
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_json_content_response(content: str):
    """tools なし completion が返す message.content response を組み立てる。"""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


class TestLiteLLMClientInvoke:
    """invoke の正常・境界ケース"""

    @pytest.fixture
    def client(self):
        """API key を渡したクライアント。"""
        return LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-dummy")

    def test_invoke_returns_tool_call_when_litellm_returns_one(self, client):
        """litellm が 1 件の tool_call を返すとき、その name と arguments が返る"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response(
                "world_no_op", {}
            )
            result = client.invoke(
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "world_no_op", "parameters": {}}}],
                tool_choice="required",
            )
        assert result is not None
        assert result["name"] == "world_no_op"
        assert result["arguments"] == {}

    def test_invoke_returns_first_tool_call_when_multiple(self, client):
        """複数 tool_call がある場合は先頭のみ返す"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            func1 = MagicMock()
            func1.name = "first_tool"
            func1.arguments = '{"a": 1}'
            func2 = MagicMock()
            func2.name = "second_tool"
            func2.arguments = "{}"
            tc1 = MagicMock()
            tc1.function = func1
            tc2 = MagicMock()
            tc2.function = func2
            msg = MagicMock()
            msg.tool_calls = [tc1, tc2]
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            m_litellm.completion.return_value = resp

            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert result is not None
        assert result["name"] == "first_tool"
        assert result["arguments"] == {"a": 1}

    def test_invoke_returns_none_when_no_tool_calls(self, client):
        """tool_calls が空のとき None を返す"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            msg = MagicMock()
            msg.tool_calls = []
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            m_litellm.completion.return_value = resp

            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert result is None

    def test_invoke_returns_none_when_choices_empty(self, client):
        """choices が空のとき None を返す"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            resp = MagicMock()
            resp.choices = []
            m_litellm.completion.return_value = resp

            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert result is None

    def test_invoke_passes_messages_tools_tool_choice_to_litellm(self, client):
        """messages, tools, tool_choice がそのまま litellm.completion に渡る"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("tool_a", {"k": "v"})
            msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}]
            tools = [{"type": "function", "function": {"name": "tool_a", "parameters": {}}}]

            client.invoke(messages=msgs, tools=tools, tool_choice="required")

            m_litellm.completion.assert_called_once()
            call_kw = m_litellm.completion.call_args[1]
            assert call_kw["messages"] == msgs
            assert call_kw["tools"] == tools
            assert call_kw["tool_choice"] == "required"
            assert call_kw["model"] == "openai/gpt-5-mini"
            assert call_kw["api_key"] == "sk-dummy"
            assert "api_base" not in call_kw

    def test_invoke_parses_invalid_json_arguments_as_empty_dict(self, client):
        """arguments が不正 JSON のときは arguments を {} として返す"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            func = MagicMock()
            func.name = "t"
            func.arguments = "not json"
            tc = MagicMock()
            tc.function = func
            msg = MagicMock()
            msg.tool_calls = [tc]
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            m_litellm.completion.return_value = resp

            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert result is not None
        assert result["name"] == "t"
        assert result["arguments"] == {}


class TestLiteLLMClientInvokeApiKey:
    """API key まわりの境界・例外"""

    def test_invoke_raises_when_api_key_not_set(self):
        """api_key が空のとき LlmApiCallException（LLM_API_KEY_MISSING）"""
        client_empty = LiteLLMClient(model="openai/gpt-5-mini", api_key="")
        with pytest.raises(LlmApiCallException) as exc_info:
            client_empty.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert exc_info.value.error_code == "LLM_API_KEY_MISSING"
        assert "OPENAI_API_KEY" in exc_info.value.message or "api_key" in exc_info.value.message.lower()

    def test_invoke_uses_env_var_when_api_key_none(self):
        """api_key が None のとき環境変数 OPENAI_API_KEY を使う"""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-from-env"}, clear=False):
            client = LiteLLMClient(model="openai/gpt-5-mini", api_key=None)
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("x", {})
            client.invoke(messages=[], tools=[], tool_choice="required")
            call_kw = m_litellm.completion.call_args[1]
            assert call_kw["api_key"] == "sk-from-env"


class TestLiteLLMClientOpenAiCompatibleApiBase:
    """OPENAI_API_BASE を使うローカル vLLM / OpenAI 互換ルート"""

    def test_invoke_uses_explicit_api_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """api_base は環境変数ではなく解決済み引数から受け取る。"""
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
            lambda: None,
        )
        client = LiteLLMClient(
            model="openai/from-env-base",
            api_key="k",
            api_base="http://127.0.0.1:9999/v1",
        )
        assert client._api_base == "http://127.0.0.1:9999/v1"

    def test_invoke_sends_api_base_and_placeholder_key_when_key_empty(self):
        """api_base が指定され OPENAI_API_KEY が空でも litellm に api_base と EMPTY を渡す"""
        client = LiteLLMClient(
            model="openai/test-model",
            api_key="",
            api_base="http://127.0.0.1:9876/v1",
        )
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("x", {})
            client.invoke(messages=[{"role": "user", "content": "h"}], tools=[], tool_choice="required")
            kw = m_litellm.completion.call_args[1]
            assert kw["api_base"] == "http://127.0.0.1:9876/v1"
            assert kw["api_key"] == "EMPTY"

    def test_invoke_prefers_explicit_api_key_when_api_base_set(self):
        """api_base がある場合も明示的 api_key があればその値を優先する"""
        client = LiteLLMClient(
            model="openai/test-model",
            api_key="sk-local-secret",
            api_base="http://127.0.0.1:9876/v1",
        )
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("x", {})
            client.invoke(messages=[], tools=[], tool_choice="required")
            assert m_litellm.completion.call_args[1]["api_key"] == "sk-local-secret"

    def test_completion_base_kwargs_includes_api_base(self):
        """completion_base_kwargs に api_base が含まれる"""
        client = LiteLLMClient(
            model="openai/z",
            api_key="EMPTY",
            api_base="http://localhost:11434/v1",
        )
        kw = client.completion_base_kwargs()
        assert kw["api_base"] == "http://localhost:11434/v1"
        assert kw["api_key"] == "EMPTY"


class TestLiteLLMClientMaxRetriesZero:
    """OpenAI SDK default の max_retries=2 を明示的に 0 に固定する挙動を保証。

    背景: litellm 1.44 + openai SDK 1.x は max_retries 未指定だと
    DEFAULT_MAX_RETRIES=2 を黙って注入し、httpx.TimeoutException で exponential
    backoff retry (0.5s → 8s + jitter) する。timeout=90s でも 90+0.5+90+1+成功
    ≈ 222s に wall_time が膨らむ outlier が C run v3 で実機観測された。
    completion_base_kwargs() と invoke() の両方で max_retries=0 を渡すことを
    構造的に固定する。
    """

    def test_completion_base_kwargs_includes_max_retries_zero(self) -> None:
        """completion_base_kwargs の戻りに max_retries=0 が必ず含まれる。"""
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        kw = client.completion_base_kwargs()
        assert "max_retries" in kw, "max_retries key must be present to override SDK default"
        assert kw["max_retries"] == 0

    def test_invoke_passes_max_retries_zero_to_litellm(self) -> None:
        """invoke が litellm.completion を呼ぶとき max_retries=0 を渡す。"""
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("t", {})
            client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
            call_kw = m_litellm.completion.call_args[1]
            assert "max_retries" in call_kw
            assert call_kw["max_retries"] == 0


class TestLiteLLMClientSelectiveRetry:
    """RateLimit / 一時 5xx だけアプリ層で backoff retry し、それ以外は即失敗する挙動を保証。

    背景: PR #454 で max_retries=0 を入れて SDK 透過 retry を全切りした (timeout
    outlier 対策)。しかしこれは副作用として 429/5xx も即失敗にしてしまい、
    実機で「ほぼ全 LLM call が 429 で死ぬ」状況が発生 (D run 第 1 回 14/148
    成功、9% 成功率)。本クラスは「timeout / auth は retry しない、RateLimit /
    5xx は短い backoff で retry する」二面性を構造的に保証する。
    """

    def test_rate_limit_error_is_retried_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RateLimitError 1 回 → 2 回目で成功する場合、結果が返る。"""
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client.time.sleep",
            lambda _s: None,
        )
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        import litellm as _ll

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.RateLimitError = _ll.RateLimitError
            m_litellm.InternalServerError = _ll.InternalServerError
            m_litellm.ServiceUnavailableError = _ll.ServiceUnavailableError
            m_litellm.completion.side_effect = [
                _ll.RateLimitError("rate limited", "openai", "gpt-5-mini"),
                _make_tool_call_response("ok_tool", {"k": 1}),
            ]
            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert result is not None
        assert result["name"] == "ok_tool"
        assert m_litellm.completion.call_count == 2

    def test_rate_limit_exhausted_raises_llm_api_call_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """全 retry 失敗 (default 3 回) で LlmApiCallException(error_code=LLM_RATE_LIMIT) を投げる。"""
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client.time.sleep",
            lambda _s: None,
        )
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        import litellm as _ll

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.RateLimitError = _ll.RateLimitError
            m_litellm.InternalServerError = _ll.InternalServerError
            m_litellm.ServiceUnavailableError = _ll.ServiceUnavailableError
            m_litellm.completion.side_effect = _ll.RateLimitError(
                "rate limited", "openai", "gpt-5-mini"
            )
            with pytest.raises(LlmApiCallException) as exc_info:
                client.invoke(
                    messages=[{"role": "user", "content": "x"}],
                    tools=[],
                    tool_choice="required",
                )
        # default 3 attempts → 1 + 3 = 4 回 call (最初 1 回 + retry 3 回)
        assert m_litellm.completion.call_count == 4
        assert exc_info.value.error_code == "LLM_RATE_LIMIT"

    def test_timeout_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """litellm.Timeout (= httpx.TimeoutException 由来) は retry されず即 raise。

        PR #454 の意図: timeout を retry すると wall_time が 3 倍まで膨らむ。
        次ターンで recover するのが正解で、SDK レベルでも app レベルでも
        retry してはならない。
        """
        slept: list[float] = []
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client.time.sleep",
            lambda s: slept.append(s),
        )
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        import litellm as _ll

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.RateLimitError = _ll.RateLimitError
            m_litellm.InternalServerError = _ll.InternalServerError
            m_litellm.ServiceUnavailableError = _ll.ServiceUnavailableError
            m_litellm.completion.side_effect = _ll.Timeout(
                "timeout", "openai", "gpt-5-mini"
            )
            with pytest.raises(LlmApiCallException):
                client.invoke(
                    messages=[{"role": "user", "content": "x"}],
                    tools=[],
                    tool_choice="required",
                )
        # retry されないので 1 回だけ呼ばれ、sleep も発生しない
        assert m_litellm.completion.call_count == 1
        assert slept == []

    def test_authentication_error_is_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """認証エラーは retry しても直らないので即失敗。"""
        slept: list[float] = []
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client.time.sleep",
            lambda s: slept.append(s),
        )
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        import litellm as _ll

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.RateLimitError = _ll.RateLimitError
            m_litellm.InternalServerError = _ll.InternalServerError
            m_litellm.ServiceUnavailableError = _ll.ServiceUnavailableError
            m_litellm.completion.side_effect = _ll.AuthenticationError(
                "bad key", "openai", "gpt-5-mini"
            )
            with pytest.raises(LlmApiCallException) as exc_info:
                client.invoke(
                    messages=[{"role": "user", "content": "x"}],
                    tools=[],
                    tool_choice="required",
                )
        assert m_litellm.completion.call_count == 1
        assert slept == []
        assert exc_info.value.error_code == "LLM_AUTHENTICATION_ERROR"

    def test_retry_attempts_constructor_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """retry 回数は解決済み引数で上書きできる。"""
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client.time.sleep",
            lambda _s: None,
        )
        client = LiteLLMClient(
            model="openai/gpt-5-mini",
            api_key="sk-x",
            rate_limit_retry_attempts=1,
        )
        import litellm as _ll

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.RateLimitError = _ll.RateLimitError
            m_litellm.InternalServerError = _ll.InternalServerError
            m_litellm.ServiceUnavailableError = _ll.ServiceUnavailableError
            m_litellm.completion.side_effect = _ll.RateLimitError(
                "rate limited", "openai", "gpt-5-mini"
            )
            with pytest.raises(LlmApiCallException):
                client.invoke(
                    messages=[{"role": "user", "content": "x"}],
                    tools=[],
                    tool_choice="required",
                )
        # attempts=1 → 1 + 1 = 2 回 call
        assert m_litellm.completion.call_count == 2

    def test_internal_server_error_is_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """500 系の一時的サーバエラーも retry 対象。"""
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client.time.sleep",
            lambda _s: None,
        )
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        import litellm as _ll

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.RateLimitError = _ll.RateLimitError
            m_litellm.InternalServerError = _ll.InternalServerError
            m_litellm.ServiceUnavailableError = _ll.ServiceUnavailableError
            m_litellm.completion.side_effect = [
                _ll.InternalServerError("500", "openai", "gpt-5-mini"),
                _make_tool_call_response("ok", {}),
            ]
            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert result is not None
        assert m_litellm.completion.call_count == 2


class TestLiteLLMClientInvokeExceptions:
    """invoke 時の LiteLLM 例外を LlmApiCallException に包む"""

    @pytest.fixture
    def client(self):
        return LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-dummy")

    def test_litellm_authentication_error_raises_with_auth_code(self, client):
        """litellm.AuthenticationError のとき error_code が LLM_AUTHENTICATION_ERROR"""
        import litellm
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.side_effect = litellm.AuthenticationError("invalid key", "openai", "gpt-5-mini")
            with pytest.raises(LlmApiCallException) as exc_info:
                client.invoke(messages=[], tools=[], tool_choice="required")
        assert exc_info.value.error_code == "LLM_AUTHENTICATION_ERROR"
        assert exc_info.value.cause is not None

    def test_litellm_rate_limit_error_raises_with_rate_limit_code(self, client):
        """litellm.RateLimitError のとき error_code が LLM_RATE_LIMIT"""
        import litellm
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.side_effect = litellm.RateLimitError("rate limited", "openai", "gpt-5-mini")
            with pytest.raises(LlmApiCallException) as exc_info:
                client.invoke(messages=[], tools=[], tool_choice="required")
        assert exc_info.value.error_code == "LLM_RATE_LIMIT"
        assert exc_info.value.cause is not None

    def test_generic_exception_raises_with_api_call_failed_code(self, client):
        """その他の例外のとき error_code が LLM_API_CALL_FAILED"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.side_effect = RuntimeError("network error")
            with pytest.raises(LlmApiCallException) as exc_info:
                client.invoke(messages=[], tools=[], tool_choice="required")
        assert exc_info.value.error_code == "LLM_API_CALL_FAILED"
        assert exc_info.value.cause is not None
        assert isinstance(exc_info.value.cause, RuntimeError)

    def test_失敗時のmetricsにerror_detailとreasoning_effortが載る(self, client):
        """API 失敗時、sink に流す metrics に例外本文 (error_detail) と、その呼び出しで
        指定した reasoning_effort / tool_choice が載る。

        実 run v3coop_stagnation_002 で「Thinking mode does not support this tool_choice」
        という provider 400 本文がログにしか残らず trace から診断できなかった穴を塞ぐ。
        """
        sink = _RecordingSink()
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.side_effect = RuntimeError(
                "Thinking mode does not support this tool_choice"
            )
            with pytest.raises(LlmApiCallException):
                client.invoke(
                    messages=[], tools=[], tool_choice="required",
                    metrics_sink=sink, reasoning_effort="low",
                )
        assert len(sink.records) == 1
        m = sink.records[0]
        assert m.success is False
        assert m.error_code == "LLM_API_CALL_FAILED"
        assert "Thinking mode does not support this tool_choice" in m.error_detail
        assert m.reasoning_effort == "low"
        assert m.tool_choice == "required"

    def test_成功時のmetricsにもreasoning_effortとtool_choiceが載る(self, client):
        """成功時も、その呼び出しの reasoning_effort / tool_choice を metrics に残す
        (熟考ターンか通常ターンかを trace で区別できるようにする)。error_detail は空。"""
        sink = _RecordingSink()
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("wait", {})
            client.invoke(
                messages=[{"role": "user", "content": "x"}], tools=[],
                tool_choice="required", metrics_sink=sink, reasoning_effort="low",
            )
        assert len(sink.records) == 1
        m = sink.records[0]
        assert m.success is True
        assert m.error_detail == ""
        assert m.reasoning_effort == "low"
        assert m.tool_choice == "required"


class TestLiteLLMClientJsonCompletion:
    """tools なし JSON completion のパース境界。"""

    @pytest.fixture
    def client(self):
        return LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-dummy")

    def test_subjective_json_completion_extracts_fenced_json(self, client):
        """vLLM がコードフェンス付き JSON を返しても object を抽出する。"""
        content = '```json\n{"interpreted": "意味", "recall_text": "回想"}\n```'
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_json_content_response(content)
            result = client.complete_episode_subjective_json(
                [{"role": "user", "content": "json"}],
            )
        assert result == {"interpreted": "意味", "recall_text": "回想"}

    def test_reinterpretation_json_completion_extracts_after_think_tag(self, client):
        """thinking 系モデルの思考タグ後にある JSON を抽出する。"""
        content = (
            "<think>hidden reasoning</think>\n"
            '{"episode_updates": [{"episode_id": "ep-a", '
            '"current_interpretation": "意味", "current_recall_text": "回想"}]}'
        )
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_json_content_response(content)
            result = client.complete_episodic_reinterpretation_json(
                [{"role": "user", "content": "json"}],
            )
        assert result["episode_updates"][0]["episode_id"] == "ep-a"

    def test_belief_consolidation_json_completion_delegates_and_returns_dict(self, client):
        """complete_belief_consolidation_json は messages を litellm に渡し、
        返り値の JSON を decisions を含む dict として返す。"""
        content = (
            '{"decisions": [{"action": "create", "text": "探索は空振りが多い", '
            '"importance": 6, "tags": ["探索"]}]}'
        )
        messages = [{"role": "user", "content": "json"}]
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_json_content_response(content)
            result = client.complete_belief_consolidation_json(messages)
        assert m_litellm.completion.call_args.kwargs["messages"] == messages
        assert result["decisions"][0]["action"] == "create"


class TestLiteLLMClientInit:
    """コンストラクタのバリデーション"""

    def test_implements_illm_client(self):
        """LiteLLMClient は ILLMClient を実装している"""
        client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x")
        assert isinstance(client, ILLMClient)

    def test_model_empty_raises_value_error(self):
        """model が空文字のとき ValueError"""
        with pytest.raises(ValueError, match="model must be a non-empty string"):
            LiteLLMClient(model="", api_key="sk-x")
        with pytest.raises(ValueError, match="model must be a non-empty string"):
            LiteLLMClient(model="   ", api_key="sk-x")

    def test_api_key_env_var_empty_raises_value_error(self):
        """api_key_env_var が空のとき ValueError"""
        with pytest.raises(ValueError, match="api_key_env_var must be a non-empty string"):
            LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x", api_key_env_var="")
        with pytest.raises(ValueError, match="api_key_env_var must be a non-empty string"):
            LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-x", api_key_env_var="   ")

    def test_api_key_not_str_raises_type_error(self):
        """api_key に str 以外を渡したとき TypeError"""
        with pytest.raises(TypeError, match="api_key must be str or None"):
            LiteLLMClient(model="openai/gpt-5-mini", api_key=123)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="api_key must be str or None"):
            LiteLLMClient(model="openai/gpt-5-mini", api_key=[])  # type: ignore[arg-type]

    def test_default_model_is_gpt5_mini(self):
        """デフォルトモデルは openai/gpt-5-mini"""
        client = LiteLLMClient(api_key="sk-x")
        assert client._model == "openai/gpt-5-mini"


class TestExtractTokenUsage:
    """_extract_token_usage が provider 別の cached_tokens 経路を全部拾える。"""

    def test_usage_欠落_なら_全部_0(self) -> None:
        """usage 属性が無い response は (0, 0, 0)。"""
        response = MagicMock(spec=[])  # usage 属性なし
        assert LiteLLMClient._extract_token_usage(response) == (0, 0, 0)

    def test_openai_vllm_の_prompt_tokens_details_cached_tokens_を_読む(self) -> None:
        """OpenAI / vLLM 互換: usage.prompt_tokens_details.cached_tokens。"""
        details = MagicMock()
        details.cached_tokens = 320
        usage = MagicMock()
        usage.prompt_tokens = 500
        usage.completion_tokens = 40
        usage.prompt_tokens_details = details
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_token_usage(response) == (500, 40, 320)

    def test_prompt_tokens_details_が_dict_でも_読める(self) -> None:
        """litellm は dict / object どちらでも返してくることがあるので両対応。"""
        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 10
        usage.prompt_tokens_details = {"cached_tokens": 50}
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_token_usage(response) == (100, 10, 50)

    def test_anthropic_の_cache_read_input_tokens_を_読む(self) -> None:
        """Anthropic: usage.cache_read_input_tokens (prompt_tokens_details は無い)。"""
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "cache_read_input_tokens"])
        usage.prompt_tokens = 800
        usage.completion_tokens = 50
        usage.cache_read_input_tokens = 600
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_token_usage(response) == (800, 50, 600)

    def test_旧_vllm_の_直下_cached_tokens_を_読む(self) -> None:
        """legacy fallback: usage.cached_tokens 直下 (prompt_tokens_details / cache_read_input_tokens 共に無い)。"""
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "cached_tokens"])
        usage.prompt_tokens = 200
        usage.completion_tokens = 20
        usage.cached_tokens = 150
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_token_usage(response) == (200, 20, 150)

    def test_cached_tokens_が_どこにも_無い_なら_0(self) -> None:
        """cache 系 field がどこにも無い response は cached_tokens=0。"""
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens = 100
        usage.completion_tokens = 10
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_token_usage(response) == (100, 10, 0)

    def test_cached_tokens_が_None_なら_他経路にフォールバック(self) -> None:
        """prompt_tokens_details.cached_tokens=None でも他経路で 0 まで降りる。"""
        details = MagicMock(spec=["cached_tokens"])
        details.cached_tokens = None
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "prompt_tokens_details"])
        usage.prompt_tokens = 100
        usage.completion_tokens = 10
        usage.prompt_tokens_details = details
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_token_usage(response) == (100, 10, 0)


class TestLiteLLMClientOpenRouterProviderRouting:
    """OpenRouter provider routing 設定の注入挙動。

    Gemma 4 31B のような複数 quantization (turbo=fp4 / fp8) を出す provider で、
    意図しない variant に routing されて tools / response_format が壊れるのを
    防ぐ。env 未設定なら何も注入しない後方互換を厳守する。
    """

    def test_env_未設定なら_provider_routing_は_extra_body_に_入らない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OPENROUTER_* が無ければ provider routing は extra_body に乗らない。

        注: 別途 LLM_REASONING_EFFORT=none が default で reasoning/thinking を inject
        するため extra_body 自体は存在する。ここでは「provider routing が乗っていない」
        ことを assert する (既存テストの本来の意図はこちら)。
        """
        monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
        client = LiteLLMClient(model="openai/gpt-4o-mini", api_key="sk-x")
        assert client.openrouter_routing is None
        kwargs = client.completion_base_kwargs()
        eb = kwargs.get("extra_body")
        if eb is not None:
            assert "provider" not in eb
            assert "quantizations" not in eb

    def test_provider_だけ_設定で_order_と_allow_fallbacks_が入る(self) -> None:
        """provider=DeepInfra → order=[DeepInfra], allow_fallbacks=False。"""
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-x",
            openrouter_provider="DeepInfra",
        )
        routing = client.openrouter_routing
        assert routing == {
            "provider": {"order": ["DeepInfra"], "allow_fallbacks": False}
        }

    def test_quantization_と_require_params_を_組み合わせると_全部入る(self) -> None:
        """provider + quantization + require_params を同時に指定。"""
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-x",
            openrouter_provider="DeepInfra",
            openrouter_quantization="fp8",
            openrouter_require_params=True,
        )
        assert client.openrouter_routing == {
            "provider": {
                "order": ["DeepInfra"],
                "allow_fallbacks": False,
                "quantizations": ["fp8"],
                "require_parameters": True,
            }
        }

    def test_quantization_だけ_設定だと_provider_は_含まれない(self) -> None:
        """provider 指定無しなら order / allow_fallbacks は付けない (=他 provider への
        fallback を残す)。quantization フィルタだけ効かせる用途。"""
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-x",
            openrouter_quantization="fp8",
        )
        assert client.openrouter_routing == {"provider": {"quantizations": ["fp8"]}}

    def test_require_params_True_で_require_parameters_が入る(self) -> None:
        """truthy 解釈は設定 DTO 側で済ませ、クライアントは bool を受け取る。"""
        client = LiteLLMClient(
            model="m", api_key="sk-x", openrouter_require_params=True
        )
        assert client.openrouter_routing == {
            "provider": {"require_parameters": True}
        }

    def test_require_params_False_なら_無視される(self) -> None:
        """False なら他に routing 設定が無いため routing 全体が None になる。"""
        client = LiteLLMClient(
            model="m", api_key="sk-x", openrouter_require_params=False
        )
        assert client.openrouter_routing is None

    def test_completion_base_kwargs_に_extra_body_が_注入される(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """JSON 系経路は completion_base_kwargs() を踏むので、ここに入れば
        complete_*_json 全部に効く。"""
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-x",
            openrouter_provider="DeepInfra",
            openrouter_quantization="fp8",
        )
        kwargs = client.completion_base_kwargs()
        eb = kwargs.get("extra_body")
        # provider routing が入っている (本テストの主眼)
        assert eb is not None
        assert eb["provider"] == {
            "order": ["DeepInfra"],
            "allow_fallbacks": False,
            "quantizations": ["fp8"],
        }
        # reasoning は default OFF として乗っているはず (別テストで保証)

    def test_invoke_が_litellm_completion_に_extra_body_を_渡す(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tool_choice='required' 経路でも extra_body が litellm に流れる。"""
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-x",
            openrouter_provider="DeepInfra",
            openrouter_quantization="fp8",
        )
        with patch(
            "ai_rpg_world.infrastructure.llm.litellm_client.litellm.completion"
        ) as mock_completion:
            mock_completion.return_value = _make_tool_call_response("noop", {})
            client.invoke(messages=[{"role": "user", "content": "hi"}], tools=[{"x": 1}])
            assert mock_completion.called
            _, call_kw = mock_completion.call_args
            # provider routing が流れていることだけ assert (本テストの主眼)
            assert call_kw["extra_body"]["provider"] == {
                "order": ["DeepInfra"],
                "allow_fallbacks": False,
                "quantizations": ["fp8"],
            }

    def test_openrouter_routing_property_は_コピーを返す(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """外部から property 経由で取った dict を mutate しても内部状態は壊れない。"""
        client = LiteLLMClient(
            model="m", api_key="sk-x", openrouter_provider="DeepInfra"
        )
        snapshot = client.openrouter_routing
        assert snapshot is not None
        snapshot["provider"]["order"] = ["Hacked"]
        # 再取得しても汚染されていない
        assert client.openrouter_routing == {
            "provider": {"order": ["DeepInfra"], "allow_fallbacks": False}
        }


def _make_tool_call_response_with_cost(name: str, arguments: dict, cost: float):
    """tool_call + usage.cost を持つ response (OpenRouter 想定)。"""
    func = MagicMock()
    func.name = name
    func.arguments = json.dumps(arguments) if arguments else "{}"
    tc = MagicMock()
    tc.function = func
    msg = MagicMock()
    msg.tool_calls = [tc]
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "cost"])
    usage.prompt_tokens = 100
    usage.completion_tokens = 10
    usage.cost = cost
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


class _RecordingSink:
    def __init__(self) -> None:
        self.records = []

    def record(self, metrics) -> None:  # type: ignore[no-untyped-def]
        self.records.append(metrics)


class TestLiteLLMClientOpenRouterCostTracking:
    """OpenRouter 経由のとき usage.cost を LlmCallMetrics.cost_usd に拾う。

    OpenRouter は ``extra_body.usage.include=True`` を付けると provider 宣告の
    USD コストを返す。直結 / vLLM では返ってこないので 0.0 維持。
    """

    def test_api_base_が_openrouter_なら_usage_include_が_extra_body_に_乗る(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """api_base に 'openrouter.ai' を含む場合に限り usage.include を注入する。"""
        monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-or-x",
            api_base="https://openrouter.ai/api/v1",
        )
        kw = client.completion_base_kwargs()
        # usage.include が乗っていることだけ assert (本テストの主眼)
        assert kw["extra_body"]["usage"] == {"include": True}

    def test_api_base_が_openai_直結なら_provider_routing_系_field_は_付かない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OpenAI / vLLM 直結では usage.include / provider 系は付けない。

        reasoning/thinking は別 axis (default OFF) で乗るので、ここでは
        provider routing と usage 系が漏れ出ていないことを保証する。
        """
        monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
        client = LiteLLMClient(
            model="openai/gpt-4o-mini",
            api_key="sk-x",
            api_base="https://api.openai.com/v1",
        )
        kw = client.completion_base_kwargs()
        eb = kw.get("extra_body")
        if eb is not None:
            assert "usage" not in eb
            assert "provider" not in eb

    def test_provider_routing_と_usage_include_が_同じ_extra_body_に_共存する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """provider routing + api_base=openrouter の組み合わせで両方乗る。"""
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-or-x",
            api_base="https://openrouter.ai/api/v1",
            openrouter_provider="DeepInfra",
            openrouter_quantization="fp8",
        )
        kw = client.completion_base_kwargs()
        eb = kw["extra_body"]
        # provider routing と usage.include が共存していることを assert
        # (reasoning/thinking は別テストの責務)
        assert eb["provider"] == {
            "order": ["DeepInfra"],
            "allow_fallbacks": False,
            "quantizations": ["fp8"],
        }
        assert eb["usage"] == {"include": True}

    def test_response_の_usage_cost_が_metrics_の_cost_usd_に_流れる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """invoke 経路で response.usage.cost が LlmCallMetrics.cost_usd に入る。"""
        client = LiteLLMClient(
            model="openrouter/google/gemma-4-31b-it",
            api_key="sk-or-x",
            api_base="https://openrouter.ai/api/v1",
        )
        sink = _RecordingSink()
        with patch(
            "ai_rpg_world.infrastructure.llm.litellm_client.litellm.completion"
        ) as mock_completion:
            mock_completion.return_value = _make_tool_call_response_with_cost(
                "noop", {}, cost=0.0000089
            )
            client.invoke(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"x": 1}],
                metrics_sink=sink,
            )
        assert len(sink.records) == 1
        assert sink.records[0].cost_usd == pytest.approx(0.0000089)

    def test_usage_に_cost_が_無い_provider_では_cost_usd_は_0(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OpenAI 直結 / vLLM などで cost フィールドが無いとき 0.0 を維持。"""
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens = 50
        usage.completion_tokens = 5
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_cost_usd(response) == 0.0

    def test_usage_全体が_None_なら_cost_usd_は_0(self) -> None:
        """usage がそもそも無い (失敗 response 等) でも例外を出さず 0.0。"""
        response = MagicMock()
        response.usage = None
        assert LiteLLMClient._extract_cost_usd(response) == 0.0

    def test_usage_が_dict_で_来る_provider_でも_cost_を_拾う(self) -> None:
        """一部 provider 経路で usage が dict のまま返る場合の救済。"""
        response = MagicMock()
        response.usage = {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0001}
        assert LiteLLMClient._extract_cost_usd(response) == pytest.approx(0.0001)


class TestLiteLLMClientTimeout:
    """PR #444: long-tail hang を打ち切る timeout 設定。

    PR #443 で 303 秒の異常 call が wall_time 38 分の主因と判明。litellm の
    既定 request_timeout=6000 (= 100 分) が silent に許容していたのが原因。
    本テスト群は LiteLLMClient が timeout を必ず litellm に渡すことを保証する。
    """

    def test_default_timeout_は_90秒(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """env / 引数指定なしなら default 90 秒 (long-tail を抑制する程度)。"""
        monkeypatch.delenv("LLM_REQUEST_TIMEOUT_SECONDS", raising=False)
        client = LiteLLMClient(model="openai/gpt-4o-mini", api_key="sk-x")
        assert client._timeout_seconds == 90.0

    def test_引数で_timeout_を_明示できる(self) -> None:
        client = LiteLLMClient(
            model="m", api_key="sk-x", timeout_seconds=30.0
        )
        assert client._timeout_seconds == 30.0

    def test_constructor_で_timeout_を_override_できる(self) -> None:
        client = LiteLLMClient(model="m", api_key="sk-x", timeout_seconds=45.0)
        assert client._timeout_seconds == 45.0

    def test_timeout_引数がそのまま使われる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "10")
        client = LiteLLMClient(
            model="m", api_key="sk-x", timeout_seconds=120.0
        )
        assert client._timeout_seconds == 120.0

    def test_timeout_非数値引数なら_ValueError(self) -> None:
        """クライアント単体でも不正な timeout 引数は失敗する。"""
        with pytest.raises(ValueError):
            LiteLLMClient(model="m", api_key="sk-x", timeout_seconds="ten")  # type: ignore[arg-type]

    def test_completion_base_kwargs_に_timeout_が_含まれる(self) -> None:
        client = LiteLLMClient(model="m", api_key="sk-x", timeout_seconds=60.0)
        kw = client.completion_base_kwargs()
        assert kw["timeout"] == 60.0

    def test_invoke_が_litellm_completion_に_timeout_を_渡す(self) -> None:
        client = LiteLLMClient(model="m", api_key="sk-x", timeout_seconds=45.0)
        with patch(
            "ai_rpg_world.infrastructure.llm.litellm_client.litellm.completion"
        ) as mock_completion:
            mock_completion.return_value = _make_tool_call_response("noop", {})
            client.invoke(messages=[{"role": "user", "content": "hi"}], tools=[{}])
            _, call_kw = mock_completion.call_args
            assert call_kw["timeout"] == 45.0


class TestLiteLLMClientReasoningEffort:
    """``reasoning_effort`` 引数による reasoning ON/OFF 制御の挙動を保証。

    背景: deepseek-v4-flash 等の reasoning model は default で effort=high が
    乗り、output token を 5-15x 膨らませる。litellm 1.44 の OpenrouterConfig は
    reasoning_effort を素通しせず DeepSeekChatConfig が thinking:{enabled} に
    collapse する (#27439 / #27453)。そのため top-level 引数は信頼できず、
    extra_body 経由で OpenRouter envelope + DeepSeek native の両方を inject する
    belt-and-suspenders 戦略を採る。
    """

    def test_default_は_reasoning_none_と_thinking_disabled_を_注入する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """未指定なら reasoning OFF + thinking disabled が extra_body に乗る。"""
        client = LiteLLMClient(model="m", api_key="sk-x")
        eb = client._build_extra_body()
        assert eb is not None
        assert eb["reasoning"]["effort"] == "none"
        assert eb["reasoning"]["exclude"] is True
        assert eb["thinking"] == {"type": "disabled"}

    def test_high_を_指定すると_reasoning_high_が_乗り_thinking_は_付かない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """effort=high のとき OpenRouter envelope だけ inject、native kill switch は不要。"""
        client = LiteLLMClient(model="m", api_key="sk-x", reasoning_effort="high")
        eb = client._build_extra_body()
        assert eb is not None
        assert eb["reasoning"]["effort"] == "high"
        # high のときは thinking:disabled は意味がないので入れない
        assert "thinking" not in eb

    def test_空文字_指定で_reasoning_系_field_を_一切_注入しない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """reasoning_effort="" は古い model 互換用のエスケープハッチ。"""
        client = LiteLLMClient(model="m", api_key="sk-x", reasoning_effort="")
        eb = client._build_extra_body()
        # extra_body 自体が None でなくてもよいが、reasoning/thinking は乗らない
        if eb is not None:
            assert "reasoning" not in eb
            assert "thinking" not in eb

    def test_未知の_effort_文字列_は_ValueError(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """typo 防止 (silent fallback しない / PR #434 ポリシー継承)。"""
        with pytest.raises(ValueError, match="reasoning_effort"):
            LiteLLMClient(model="m", api_key="sk-x", reasoning_effort="extreme")

    def test_invoke_が_extra_body_に_reasoning_block_を_渡す(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """invoke の litellm.completion 呼び出し時、extra_body に reasoning が乗る。"""
        client = LiteLLMClient(model="m", api_key="sk-x")
        with patch(
            "ai_rpg_world.infrastructure.llm.litellm_client.litellm.completion"
        ) as mock_completion:
            mock_completion.return_value = _make_tool_call_response("noop", {})
            client.invoke(messages=[{"role": "user", "content": "hi"}], tools=[{}])
            _, call_kw = mock_completion.call_args
            eb = call_kw["extra_body"]
            assert eb["reasoning"]["effort"] == "none"
            assert eb["thinking"] == {"type": "disabled"}

    def test_openrouter_routing_と_共存する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """provider routing + reasoning が同一 extra_body に並ぶ (どちらも保持)。"""
        client = LiteLLMClient(
            model="openrouter/x",
            api_key="sk-x",
            openrouter_provider="Baidu",
            openrouter_quantization="fp8",
        )
        eb = client._build_extra_body()
        assert eb is not None
        # provider routing
        assert eb["provider"]["order"] == ["Baidu"]
        assert eb["provider"]["quantizations"] == ["fp8"]
        # reasoning + thinking
        assert eb["reasoning"]["effort"] == "none"
        assert eb["thinking"] == {"type": "disabled"}


class TestLiteLLMClientWallTimeHardCap:
    """``wall_cap_seconds`` 引数による wall-time hard cap の挙動を保証。

    背景: httpx の `Timeout(read=90)` は per-recv 単位の wait であり、サーバが
    時々 1byte でも返せば永遠に待ち続ける (PR #463 後続調査で確定)。H run で
    timeout=90s 設定下に wall_latency=122s の outlier を観測。
    対策として ``concurrent.futures.ThreadPoolExecutor.result(timeout=)`` で
    アプリ層から wall-time を独立に強制する。
    """

    def test_default_wall_cap_は_timeout_seconds_プラス_5秒(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """未指定なら self._timeout_seconds + 5 が wall cap になる。"""
        client = LiteLLMClient(model="m", api_key="sk-x", timeout_seconds=60.0)
        assert client._wall_cap_seconds == 65.0

    def test_constructor_で_wall_cap_を_短く_設定できる(self) -> None:
        """45.0 秒に絞れる (全体律速を避ける用途)。"""
        client = LiteLLMClient(
            model="m",
            api_key="sk-x",
            timeout_seconds=90.0,
            wall_cap_seconds=45.0,
        )
        assert client._wall_cap_seconds == 45.0

    def test_wall_cap_非数値引数は_ValueError(self) -> None:
        """クライアント単体でも不正な wall cap 引数は失敗する。"""
        with pytest.raises(ValueError):
            LiteLLMClient(model="m", api_key="sk-x", wall_cap_seconds="thirty")  # type: ignore[arg-type]

    def test_wall_cap_ゼロ以下は_ValueError(self) -> None:
        """0 以下は意味がない (即 timeout = 1 回も呼べない) ので fail-fast。"""
        with pytest.raises(ValueError, match="must be greater than 0"):
            LiteLLMClient(model="m", api_key="sk-x", wall_cap_seconds=0)

    def test_wall_cap_を_超えた_call_は_LitellmTimeout_に_packaged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """litellm.completion が遅延するときに wall cap で打ち切られ Timeout になる。

        Note: time.sleep を monkeypatch すると Python の time module 全体が
        変わってしまい test 内の sleep にも影響するので、ここでは monkeypatch
        を使わず threading.Event.wait で「絶対 sleep する」を実装する。
        """
        import threading

        # 短い wall cap で test (0.3s で確実に切れる)
        client = LiteLLMClient(model="m", api_key="sk-x", wall_cap_seconds=0.3)

        # Event.wait は monkeypatch されないので確実に N 秒 block する
        _block = threading.Event()

        def slow_completion(**_kw: Any) -> Any:
            _block.wait(timeout=3.0)  # wall cap (0.3s) を超える
            return _make_tool_call_response("noop", {})

        with patch(
            "ai_rpg_world.infrastructure.llm.litellm_client.litellm.completion",
            side_effect=slow_completion,
        ):
            with pytest.raises(LlmApiCallException) as exc_info:
                client.invoke(
                    messages=[{"role": "user", "content": "x"}],
                    tools=[],
                    tool_choice="required",
                )
        # litellm.Timeout に packaging されているはず (LlmApiCallException 経由)
        msg = str(exc_info.value)
        assert "wall-time cap" in msg or "Timeout" in msg, msg

    def test_通常_call_は_wall_cap_の_影響を_受けない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """wall cap 内に完走する call は普通に結果を返す。"""
        client = LiteLLMClient(model="m", api_key="sk-x", wall_cap_seconds=5.0)
        with patch(
            "ai_rpg_world.infrastructure.llm.litellm_client.litellm.completion",
            return_value=_make_tool_call_response("ok", {}),
        ):
            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        assert result is not None
        assert result["name"] == "ok"

    def test_wall_cap_は_per_attempt_で_retry_累積_しない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """wall cap は各 attempt 個別に効き、retry 合算には適用されない。

        = 「最大 wall = (cap × retry 回数 + sleep 合計)」 ではあるが、
        正常 call が cap に引きずられて切られることはない。
        """
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client.time.sleep",
            lambda _s: None,
        )
        client = LiteLLMClient(model="m", api_key="sk-x", wall_cap_seconds=1.0)
        import litellm as _ll

        # 1 回目 RateLimit → 2 回目で成功 (それぞれ 0.1s 程度の short call)
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.RateLimitError = _ll.RateLimitError
            m_litellm.InternalServerError = _ll.InternalServerError
            m_litellm.ServiceUnavailableError = _ll.ServiceUnavailableError
            m_litellm.Timeout = _ll.Timeout
            m_litellm.completion.side_effect = [
                _ll.RateLimitError("rate limited", "openai", "m"),
                _make_tool_call_response("ok", {}),
            ]
            result = client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
        # 2 回目で成功 (= per-attempt wall cap は各 call に独立で適用される)
        assert result is not None
        assert result["name"] == "ok"


class TestLiteLLMClientReasoningEffortOverride:
    """invoke の per-call reasoning_effort override と reasoning_token 捕捉。

    案A (band-gated thinking) の基盤: 通常は構築時の既定 (env / none) で reasoning
    OFF のまま、詰まったターンだけ呼び出し単位で effort を上書きできることを保証する。
    """

    @pytest.fixture
    def client(self):
        return LiteLLMClient(model="openrouter/deepseek/deepseek-v4-flash", api_key="sk-dummy")

    def _completion_extra_body(self, m_litellm) -> dict:
        return m_litellm.completion.call_args.kwargs["extra_body"]

    def test_invoke_reasoning_effort_override_sets_effort_in_extra_body(self, client):
        """reasoning_effort='low' を渡すと、その 1 呼び出しの extra_body.reasoning.effort が
        構築時の既定 (none) を上書きして 'low' になる。"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("world_no_op", {})
            client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
                reasoning_effort="low",
            )
            eb = self._completion_extra_body(m_litellm)
            assert eb["reasoning"]["effort"] == "low"

    def test_invoke_without_override_keeps_construction_default_none(self, client):
        """reasoning_effort を渡さなければ、構築時の既定 (none) のまま送られる
        (= 既存挙動を壊さない・プレフィックスキャッシュ不変)。"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("world_no_op", {})
            client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
            )
            eb = self._completion_extra_body(m_litellm)
            assert eb["reasoning"]["effort"] == "none"

    def test_invoke_rejects_unknown_reasoning_effort(self, client):
        """未知の reasoning_effort は silent fallback せず ValueError で弾く
        (PR #433 と同じ「不正値は落とす」方針)。"""
        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            m_litellm.completion.return_value = _make_tool_call_response("world_no_op", {})
            with pytest.raises(ValueError):
                client.invoke(
                    messages=[{"role": "user", "content": "x"}],
                    tools=[],
                    tool_choice="required",
                    reasoning_effort="bogus",
                )

    def test_extract_reasoning_tokens_reads_completion_tokens_details(self):
        """usage.completion_tokens_details.reasoning_tokens を best-effort で取り出す。"""
        usage = MagicMock()
        details = MagicMock()
        details.reasoning_tokens = 42
        usage.completion_tokens_details = details
        response = MagicMock()
        response.usage = usage
        assert LiteLLMClient._extract_reasoning_tokens(response) == 42

    def test_extract_reasoning_tokens_returns_zero_when_absent(self):
        """reasoning_tokens が無い provider では 0 に縮退する (例外を投げない)。"""
        response = MagicMock()
        response.usage = MagicMock(spec=[])  # no completion_tokens_details
        assert LiteLLMClient._extract_reasoning_tokens(response) == 0

    def test_invoke_emits_reasoning_tokens_in_metrics(self, client):
        """reasoning_tokens が metrics_sink 経由の LlmCallMetrics に載る。"""
        captured = []

        class _Sink:
            def record(self, m):
                captured.append(m)

        with patch("ai_rpg_world.infrastructure.llm.litellm_client.litellm") as m_litellm:
            resp = _make_tool_call_response("world_no_op", {})
            usage = MagicMock()
            details = MagicMock()
            details.reasoning_tokens = 33
            usage.completion_tokens_details = details
            usage.prompt_tokens = 100
            usage.completion_tokens = 50
            usage.prompt_tokens_details = None
            resp.usage = usage
            m_litellm.completion.return_value = resp
            client.invoke(
                messages=[{"role": "user", "content": "x"}],
                tools=[],
                tool_choice="required",
                reasoning_effort="low",
                metrics_sink=_Sink(),
            )
        assert captured
        assert captured[0].reasoning_tokens == 33
