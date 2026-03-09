"""MemoryQueryExecutor のテスト（正常・境界・例外）"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    EpisodeMemoryEntry,
    LongTermFactEntry,
    MemoryLawEntry,
)
from ai_rpg_world.application.llm.exceptions import (
    DslEvaluationException,
    DslParseException,
    InvalidOutputModeException,
)
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_working_memory_store import (
    InMemoryWorkingMemoryStore,
)
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_observation(prose: str = "洞窟に到着した") -> ObservationEntry:
    """テスト用の ObservationEntry を作成"""
    return ObservationEntry(
        occurred_at=datetime.now(),
        output=ObservationOutput(
            prose=prose,
            structured={"event": "arrival"},
        ),
    )


def _make_episode(eid: str, context: str = "洞窟にいた") -> EpisodeMemoryEntry:
    return EpisodeMemoryEntry(
        id=eid,
        context_summary=context,
        action_taken="move_to を実行",
        outcome_summary="到着した",
        entity_ids=("loc_1",),
        location_id="洞窟",
        timestamp=datetime.now(),
        importance="medium",
        surprise=False,
        recall_count=0,
    )


def _make_fact(fid: str, content: str) -> LongTermFactEntry:
    return LongTermFactEntry(
        id=fid,
        content=content,
        player_id=1,
        updated_at=datetime.now(),
    )


def _make_law(lid: str) -> MemoryLawEntry:
    return MemoryLawEntry(
        id=lid,
        subject="移動",
        relation="すると",
        target="到着",
        strength=1.0,
        player_id=1,
    )


@pytest.fixture
def episode_store():
    return InMemoryEpisodeMemoryStore()


@pytest.fixture
def long_term_store():
    return InMemoryLongTermMemoryStore()


@pytest.fixture
def sliding_window():
    return DefaultSlidingWindowMemory(max_entries_per_player=50)


@pytest.fixture
def action_result_store():
    return DefaultActionResultStore(max_entries_per_player=50)


@pytest.fixture
def working_memory_store():
    return InMemoryWorkingMemoryStore(max_entries_per_player=50)


@pytest.fixture
def state_provider():
    return lambda pid: "現在地: テストスポット"

@pytest.fixture
def recent_events_formatter():
    return DefaultRecentEventsFormatter()


@pytest.fixture
def executor(
    episode_store,
    long_term_store,
    sliding_window,
    action_result_store,
    working_memory_store,
    state_provider,
    recent_events_formatter,
):
    return MemoryQueryExecutor(
        episode_store=episode_store,
        long_term_store=long_term_store,
        sliding_window=sliding_window,
        action_result_store=action_result_store,
        working_memory_store=working_memory_store,
        state_provider=state_provider,
        recent_events_formatter=recent_events_formatter,
    )


@pytest.fixture
def player_id():
    return PlayerId(1)


class TestMemoryQueryExecutorEpisodic:
    """episodic 変数のテスト"""

    def test_episodic_take_returns_entries(
        self, executor, episode_store, player_id
    ):
        """episodic.take(5) でエピソードを取得"""
        episode_store.add(player_id, _make_episode("e1"))
        episode_store.add(player_id, _make_episode("e2"))
        got = executor.execute(player_id, "episodic.take(5)", "text")
        assert "result" in got
        assert "洞窟にいた" in got["result"]

    def test_episodic_take_respects_limit(
        self, executor, episode_store, player_id
    ):
        """episodic.take(2) は最大 2 件"""
        for i in range(5):
            episode_store.add(player_id, _make_episode(f"e{i}"))
        got = executor.execute(player_id, "episodic.take(2)", "count")
        assert got["count"] == "2"


class TestMemoryQueryExecutorFacts:
    """facts 変数のテスト"""

    def test_facts_take_returns_entries(
        self, executor, long_term_store, player_id
    ):
        """facts.take(3) で事実を取得"""
        long_term_store.add_fact(player_id, "スライムは火が弱い")
        long_term_store.add_fact(player_id, "ゴブリンは集団で現れる")
        got = executor.execute(player_id, "facts.take(5)", "text")
        assert "result" in got
        assert "スライム" in got["result"]


class TestMemoryQueryExecutorState:
    """state 変数のテスト"""

    def test_state_returns_provider_output(self, executor, player_id):
        """state で state_provider の出力を取得"""
        got = executor.execute(player_id, "state", "text")
        assert got["result"] == "現在地: テストスポット"

    def test_state_with_take_ignores_take(self, executor, player_id):
        """state は .take を無視して全体を返す"""
        got = executor.execute(player_id, "state.take(1)", "text")
        assert "現在地" in (got.get("result") or "")


class TestMemoryQueryExecutorWorkingMemory:
    """working_memory 変数のテスト"""

    def test_working_memory_take_returns_entries(
        self, executor, working_memory_store, player_id
    ):
        """working_memory.take(3) でメモを取得"""
        working_memory_store.append(player_id, "仮説1")
        working_memory_store.append(player_id, "仮説2")
        got = executor.execute(player_id, "working_memory.take(3)", "text")
        assert "result" in got
        assert "仮説1" in got["result"]
        assert "仮説2" in got["result"]


class TestMemoryQueryExecutorLaws:
    """laws 変数のテスト"""

    def test_laws_take_returns_entries(
        self, executor, long_term_store, player_id
    ):
        """laws.take(n) で法則を取得"""
        long_term_store.upsert_law(
            player_id, subject="移動", relation="すると", target="到着"
        )
        long_term_store.upsert_law(
            player_id, subject="攻撃", relation="で", target="ダメージ"
        )
        got = executor.execute(player_id, "laws.take(5)", "text")
        assert "result" in got
        assert "移動" in got["result"]
        assert "攻撃" in got["result"]

    def test_laws_take_respects_limit(
        self, executor, long_term_store, player_id
    ):
        """laws.take(2) は最大 2 件"""
        for i in range(5):
            long_term_store.upsert_law(
                player_id,
                subject=f"法則{i}",
                relation="すると",
                target="結果",
            )
        got = executor.execute(player_id, "laws.take(2)", "count")
        assert got["count"] == "2"

    def test_laws_empty_returns_zero(self, executor, player_id):
        """法則がなければ 0 件"""
        got = executor.execute(player_id, "laws.take(10)", "text")
        assert "（0件）" in (got.get("result") or "")


class TestMemoryQueryExecutorRecentEvents:
    """recent_events 変数のテスト"""

    def test_recent_events_returns_formatted_output(
        self,
        executor,
        sliding_window,
        action_result_store,
        player_id,
    ):
        """recent_events で観測と行動結果を取得"""
        sliding_window.append(player_id, _make_observation("北へ移動した"))
        action_result_store.append(
            player_id,
            "move_to を実行",
            "洞窟に到着した",
        )
        got = executor.execute(player_id, "recent_events", "text")
        assert "result" in got
        result = got["result"] or ""
        assert "北へ移動" in result or "洞窟" in result or "move_to" in result

    def test_recent_events_with_take_ignores_take(
        self, executor, sliding_window, player_id
    ):
        """recent_events は .take を無視して全体を返す（スカラ変数）"""
        sliding_window.append(player_id, _make_observation("観測1"))
        got = executor.execute(player_id, "recent_events.take(1)", "text")
        assert "result" in got

    def test_recent_events_empty_returns_formatted(
        self, executor, player_id
    ):
        """観測・行動結果がなければ空のフォーマット"""
        got = executor.execute(player_id, "recent_events", "text")
        assert "result" in got


class TestMemoryQueryExecutorOutputModes:
    """output_mode のテスト"""

    def test_output_mode_count(self, executor, episode_store, player_id):
        """output_mode=count で件数"""
        episode_store.add(player_id, _make_episode("e1"))
        got = executor.execute(player_id, "episodic.take(10)", "count")
        assert got["count"] == "1"

    def test_output_mode_preview(self, executor, episode_store, player_id):
        """output_mode=preview でプレビュー"""
        episode_store.add(player_id, _make_episode("e1"))
        got = executor.execute(player_id, "episodic.take(10)", "preview")
        assert "preview" in got
        assert "result" in got

    def test_output_mode_text_default(
        self, executor, episode_store, player_id
    ):
        """output_mode=text で本文"""
        episode_store.add(player_id, _make_episode("e1"))
        got = executor.execute(player_id, "episodic.take(10)", "text")
        assert "result" in got
        assert "洞窟にいた" in (got.get("result") or "")


class TestMemoryQueryExecutorExceptions:
    """例外ケース"""

    def test_unknown_variable_raises_parse_error(self, executor, player_id):
        """未知の変数で DslParseException"""
        with pytest.raises(DslParseException, match="Unknown variable"):
            executor.execute(player_id, "unknown_var.take(5)", "text")

    def test_episodic_without_take_raises_parse_error(
        self, executor, player_id
    ):
        """episodic のみ（take なし）で DslParseException"""
        with pytest.raises(DslParseException, match="Unsupported DSL form"):
            executor.execute(player_id, "episodic", "text")

    def test_player_id_none_raises_type_error(self, executor):
        """player_id が None で TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            executor.execute(None, "episodic.take(5)", "text")  # type: ignore[arg-type]

    def test_expr_empty_raises_parse_error(self, executor, player_id):
        """expr が空文字で DslParseException"""
        with pytest.raises(DslParseException, match="must not be empty"):
            executor.execute(player_id, "", "text")

    def test_expr_whitespace_only_raises_parse_error(
        self, executor, player_id
    ):
        """expr が空白のみで DslParseException"""
        with pytest.raises(DslParseException, match="must not be empty"):
            executor.execute(player_id, "   \t\n  ", "text")

    def test_expr_not_str_raises_type_error(self, executor, player_id):
        """expr が str でないとき TypeError"""
        with pytest.raises(TypeError, match="expr must be str"):
            executor.execute(player_id, 123, "text")  # type: ignore[arg-type]

    def test_output_mode_not_str_raises_type_error(
        self, executor, player_id
    ):
        """output_mode が str でないとき TypeError"""
        with pytest.raises(TypeError, match="output_mode must be str"):
            executor.execute(
                player_id, "episodic.take(5)", 123  # type: ignore[arg-type]
            )

    def test_output_mode_invalid_raises_invalid_output_mode(
        self, executor, episode_store, player_id
    ):
        """output_mode が不正なとき InvalidOutputModeException"""
        episode_store.add(player_id, _make_episode("e1"))
        with pytest.raises(
            InvalidOutputModeException, match="output_mode must be one of"
        ):
            executor.execute(player_id, "episodic.take(5)", "invalid")

    def test_output_mode_empty_raises_invalid_output_mode(
        self, executor, player_id
    ):
        """output_mode が空文字で InvalidOutputModeException"""
        with pytest.raises(
            InvalidOutputModeException, match="output_mode must be one of"
        ):
            executor.execute(player_id, "episodic.take(5)", "")
