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
