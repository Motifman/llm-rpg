"""SubagentRunner のテスト（bindings 評価・文字数制限・LLM モック・evidence 形式）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import SubagentEvidenceEntry
from ai_rpg_world.application.llm.exceptions import DslParseException
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.subagent_runner import (
    MAX_BINDINGS_PER_CALL,
    MAX_CHARS_PER_BINDING,
    MAX_TOTAL_CHARS_FOR_SUBAGENT,
    SubagentRunner,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestSubagentRunnerSuccess:
    """正常系: bindings 評価・answer_summary・evidence"""

    @pytest.fixture
    def executor(self):
        ex = MagicMock(spec=MemoryQueryExecutor)
        ex.execute.return_value = {"result": "エピソード1: 洞窟で探索した"}
        return ex

    @pytest.fixture
    def invoke_text(self):
        return lambda sys, user: "要約: 洞窟での探索が記録されています。"

    @pytest.fixture
    def runner(self, executor, invoke_text):
        return SubagentRunner(
            memory_query_executor=executor,
            invoke_text=invoke_text,
        )

    def test_run_evaluates_bindings_and_returns_summary(
        self, runner, executor, invoke_text
    ):
        """bindings を評価し、invoke_text で要約を取得"""
        bindings = {"episodes": "episodic.take(5)"}
        result = runner.run(PlayerId(1), bindings, "何が記録されていますか？")

        executor.execute.assert_called_once()
        call_args = executor.execute.call_args
        assert call_args[0][0] == PlayerId(1)
        assert call_args[0][1] == "episodic.take(5)"
        assert call_args[1].get("output_mode") == "text"

        assert result.answer_summary == "要約: 洞窟での探索が記録されています。"
        assert len(result.evidence) == 1
        assert result.evidence[0].binding_name == "episodes"
        assert result.evidence[0].source_var == "episodic"
        assert result.used_bindings == ("episodes",)
        assert result.truncation_note is None

    def test_run_multiple_bindings(self, runner, executor):
        """複数 binding を評価"""
        executor.execute.side_effect = [
            {"result": "エピソードA"},
            {"result": "事実B"},
        ]
        bindings = {
            "ep": "episodic.take(3)",
            "facts": "facts.take(2)",
        }
        result = runner.run(PlayerId(2), bindings, "要約して")

        assert executor.execute.call_count == 2
        assert len(result.evidence) == 2
        assert result.used_bindings == ("ep", "facts")

    def test_run_empty_bindings_invokes_with_empty_data(self, runner, executor):
        """空の bindings では executor は呼ばれず、invoke_text のみ呼ばれる"""
        result = runner.run(PlayerId(1), {}, "要約して")
        executor.execute.assert_not_called()
        assert len(result.evidence) == 0
        assert result.used_bindings == ()
        assert result.answer_summary is not None


class TestSubagentRunnerTruncation:
    """境界・文字数制限"""

    def test_run_truncates_long_binding(self):
        """binding 結果が MAX_CHARS_PER_BINDING 超えで truncate"""
        long_text = "x" * (MAX_CHARS_PER_BINDING + 100)
        executor = MagicMock(spec=MemoryQueryExecutor)
        executor.execute.return_value = {"result": long_text}
        invoke_text = lambda sys, user: "要約"
        runner = SubagentRunner(
            memory_query_executor=executor,
            invoke_text=invoke_text,
        )

        result = runner.run(
            PlayerId(1),
            {"data": "episodic.take(100)"},
            "要約して",
        )

        assert result.answer_summary == "要約"
        assert result.truncation_note is not None
        assert "truncated" in result.truncation_note

    def test_run_exceeds_max_bindings_raises_value_error(self):
        """bindings が MAX_BINDINGS_PER_CALL 超えで ValueError"""
        executor = MagicMock(spec=MemoryQueryExecutor)
        executor.execute.return_value = {"result": "a"}
        runner = SubagentRunner(
            memory_query_executor=executor,
            invoke_text=lambda s, u: "ok",
        )

        bindings = {f"b{i}": "episodic.take(1)" for i in range(MAX_BINDINGS_PER_CALL + 1)}
        with pytest.raises(
            ValueError,
            match=f"bindings count must be <= {MAX_BINDINGS_PER_CALL}",
        ):
            runner.run(PlayerId(1), bindings, "q")


class TestSubagentRunnerValidation:
    """型チェック・引数バリデーション"""

    @pytest.fixture
    def runner(self):
        ex = MagicMock(spec=MemoryQueryExecutor)
        ex.execute.return_value = {"result": ""}
        return SubagentRunner(
            memory_query_executor=ex,
            invoke_text=lambda s, u: "",
        )

    def test_run_player_id_not_player_id_raises_type_error(self, runner):
        """player_id が PlayerId でないとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            runner.run(1, {"a": "episodic.take(1)"}, "q")  # type: ignore[arg-type]

    def test_run_bindings_not_dict_raises_type_error(self, runner):
        """bindings が dict でないとき TypeError"""
        with pytest.raises(TypeError, match="bindings must be dict"):
            runner.run(PlayerId(1), [], "q")  # type: ignore[arg-type]

    def test_run_query_not_str_raises_type_error(self, runner):
        """query が str でないとき TypeError"""
        with pytest.raises(TypeError, match="query must be str"):
            runner.run(PlayerId(1), {"a": "x"}, 123)  # type: ignore[arg-type]

    def test_run_bindings_value_not_str_raises_type_error(self, runner):
        """bindings の値が str でないとき TypeError"""
        with pytest.raises(TypeError, match="bindings keys and values must be str"):
            runner.run(PlayerId(1), {"a": 123}, "q")

    def test_run_bindings_key_not_str_raises_type_error(self, runner):
        """bindings のキーが str でないとき TypeError"""
        ex = MagicMock(spec=MemoryQueryExecutor)
        ex.execute.return_value = {"result": "x"}
        r = SubagentRunner(
            memory_query_executor=ex,
            invoke_text=lambda s, u: "ok",
        )
        with pytest.raises(TypeError, match="bindings keys and values must be str"):
            r.run(PlayerId(1), {123: "episodic.take(1)"}, "q")  # type: ignore[dict-item]

    def test_run_query_empty_accepted(self, runner):
        """query が空文字でも run は成功する（呼び出し側で検証）"""
        result = runner.run(PlayerId(1), {"a": "episodic.take(1)"}, "")
        assert result.answer_summary is not None


class TestSubagentRunnerExceptionPropagation:
    """例外伝播のテスト"""

    def test_executor_execute_raises_propagates(self):
        """executor.execute が例外を投げたとき run が伝播する"""
        ex = MagicMock(spec=MemoryQueryExecutor)
        ex.execute.side_effect = DslParseException(
            "Unsupported DSL form", expr="invalid"
        )
        runner = SubagentRunner(
            memory_query_executor=ex,
            invoke_text=lambda s, u: "ok",
        )
        with pytest.raises(DslParseException, match="Unsupported DSL form"):
            runner.run(
                PlayerId(1),
                {"a": "invalid"},
                "要約して",
            )

    def test_invoke_text_raises_propagates(self):
        """invoke_text が例外を投げたとき run が伝播する"""

        def failing_invoke(_sys: str, _user: str) -> str:
            raise ValueError("LLM エラー")

        ex = MagicMock(spec=MemoryQueryExecutor)
        ex.execute.return_value = {"result": "データ"}
        runner = SubagentRunner(
            memory_query_executor=ex,
            invoke_text=failing_invoke,
        )
        with pytest.raises(ValueError, match="LLM エラー"):
            runner.run(
                PlayerId(1),
                {"a": "episodic.take(1)"},
                "要約して",
            )

    def test_executor_returns_none_result_handled(self):
        """executor が result キーなしで返したとき空文字として扱う"""
        ex = MagicMock(spec=MemoryQueryExecutor)
        ex.execute.return_value = {}
        runner = SubagentRunner(
            memory_query_executor=ex,
            invoke_text=lambda sys, user: "要約完了",
        )
        result = runner.run(
            PlayerId(1),
            {"a": "episodic.take(1)"},
            "要約して",
        )
        assert result.answer_summary == "要約完了"


class TestSubagentRunnerInit:
    """コンストラクタ検証"""

    def test_init_executor_not_memory_query_executor_raises_type_error(self):
        """memory_query_executor が MemoryQueryExecutor でないとき TypeError"""
        with pytest.raises(TypeError, match="memory_query_executor must be MemoryQueryExecutor"):
            SubagentRunner(
                memory_query_executor=object(),
                invoke_text=lambda s, u: "",
            )

    def test_init_invoke_text_not_callable_raises_type_error(self):
        """invoke_text が callable でないとき TypeError"""
        ex = MagicMock(spec=MemoryQueryExecutor)
        with pytest.raises(TypeError, match="invoke_text must be callable"):
            SubagentRunner(
                memory_query_executor=ex,
                invoke_text="not_callable",
            )
