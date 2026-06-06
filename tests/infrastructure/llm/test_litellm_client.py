"""LiteLLMClient のテスト（正常・境界・例外・初期化）"""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolate_litellm_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """開発者の .env / OPENAI_API_BASE がテスト混入しないようにする"""
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setattr(
        "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
        lambda: None,
    )


from ai_rpg_world.application.llm.contracts.interfaces import ILLMClient
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

    def test_invoke_reads_api_base_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """api_base が未指定だと環境変数 OPENAI_API_BASE を参照する"""
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:9999/v1")
        monkeypatch.setattr(
            "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
            lambda: None,
        )
        client = LiteLLMClient(model="openai/from-env-base", api_key="k")
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
