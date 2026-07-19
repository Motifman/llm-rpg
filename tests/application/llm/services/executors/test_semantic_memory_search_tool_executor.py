"""``SemanticMemorySearchToolExecutor`` のテスト (Phase 1d)。

semantic_store に対する query 検索が tag 完全一致 > tag 部分一致 > 本文一致 の
優先順で並び、空 query / top_k 範囲 / 大量結果 cap を正しく扱う。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.application.llm.services.executors.semantic_memory_search_tool_executor import (
    SemanticMemorySearchToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MEMORY_SEARCH_SEMANTIC
from tests.application.llm._semantic_being_test_helpers import (
    SemanticBeingTestSetup,
    make_semantic_being_setup,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _entry(
    *,
    entry_id: str,
    text: str = "なにかの学び",
    tags: tuple = (),
    importance_score: int = 5,
    created_at: datetime = _NOW,
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=1,
        text=text,
        evidence_episode_ids=("ep-1",),
        confidence=0.6,
        created_at=created_at,
        importance_score=importance_score,
        tags=tags,
    )


@pytest.fixture
def setup() -> SemanticBeingTestSetup:
    """Phase 3 Step 3b-3: executor は being_id 経路必須。

    Being provision + Resolver 注入を仕込んだ helper を返す。
    """
    s = make_semantic_being_setup()
    s.provision(1)
    return s


@pytest.fixture
def executor(setup: SemanticBeingTestSetup) -> SemanticMemorySearchToolExecutor:
    return SemanticMemorySearchToolExecutor(
        semantic_store=setup.semantic_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )


def _add(
    setup: SemanticBeingTestSetup,
    entry: SemanticMemoryEntry,
    player_id: int = 1,
) -> None:
    setup.populate(player_id, entry)


class TestSemanticMemorySearchHandlerRegistration:
    """get_handlers が tool name を返す。"""

    def test_handler_dict_tool_name_key_included(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """handlerdict に toolname がキーとして含まれる。"""
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in executor.get_handlers()


class TestSemanticMemorySearchArgValidation:
    """引数の境界。"""

    def test_query_empty_string_invalid_argument(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """query が空文字なら invalidargument。"""
        result = executor._run_search_semantic(player_id=1, arguments={"query": ""})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_query_unspecified_invalid_argument(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """query が未指定なら invalidargument。"""
        result = executor._run_search_semantic(player_id=1, arguments={})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_query_around_blank_invalid_argument(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """query が前後空白だけなら invalidargument。"""
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "   "}
        )
        assert result.success is False

    def test_top_k_non_number_default(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """top_k='abc' は default 5 として動作する (例外を伝播しない)。"""
        _add(setup, _entry(entry_id="x", tags=("a",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "a", "top_k": "abc"}
        )
        assert result.success is True

    def test_top_k_zero_default(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """topk が負数または 0 は default に縮退。"""
        for raw in (0, -3):
            result = executor._run_search_semantic(
                player_id=1, arguments={"query": "a", "top_k": raw}
            )
            assert result.success is True

    def test_top_k_max_value_over_32_cap(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """topk が最大値を超えたら 32 で cap。"""
        for i in range(50):
            _add(setup, _entry(entry_id=f"s{i}", text=f"q{i}", tags=("q",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "q", "top_k": 1000}
        )
        payload = json.loads(result.message)
        assert len(payload["matched_entries"]) == 32


class TestSemanticMemorySearchScoring:
    """tag 完全一致 / tag 部分一致 / 本文一致 の score 優先順。"""

    def test_tag_all_matches(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """tag 完全一致が 最上位。"""
        _add(setup, _entry(entry_id="text_only", text="タカシは漁の名手", tags=()))
        _add(setup, _entry(entry_id="exact", text="ある記憶", tags=("タカシ",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "タカシ"}
        )
        payload = json.loads(result.message)
        ids = [row["entry_id"] for row in payload["matched_entries"]]
        assert ids[0] == "exact"

    def test_match_entry_not_rendered(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """match しない entry は結果に出ない。"""
        _add(setup, _entry(entry_id="match", text="毒キノコ", tags=()))
        _add(setup, _entry(entry_id="miss", text="ココナッツ", tags=()))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "毒"}
        )
        payload = json.loads(result.message)
        ids = [row["entry_id"] for row in payload["matched_entries"]]
        assert ids == ["match"]

    def test_text_matches_hit(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """本文部分一致でも hit する。"""
        _add(setup, _entry(entry_id="text", text="北の洞窟は熊の巣", tags=()))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "北の洞窟"}
        )
        payload = json.loads(result.message)
        assert any(row["entry_id"] == "text" for row in payload["matched_entries"])

    def test_case_insensitive_match(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """英語混在: tag "Boss" と query "boss" は match する。"""
        _add(setup, _entry(entry_id="b", tags=("Boss",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "boss"}
        )
        payload = json.loads(result.message)
        assert payload["matched_entries"][0]["entry_id"] == "b"

    def test_same_match_score_importance(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """同じ matchscore なら importance が高い方が上位。"""
        _add(setup, _entry(entry_id="low", tags=("q",), importance_score=3))
        _add(setup, _entry(entry_id="high", tags=("q",), importance_score=9))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "q"}
        )
        payload = json.loads(result.message)
        assert payload["matched_entries"][0]["entry_id"] == "high"


class TestSemanticMemorySearchPayload:
    """返却 JSON が想定通り。"""

    def test_query_matched_entries_included(
        self,
        executor: SemanticMemorySearchToolExecutor,
        setup: SemanticBeingTestSetup,
    ) -> None:
        """query と matchedentries が含まれる。"""
        _add(setup, _entry(entry_id="x", text="ok", tags=("k",), importance_score=7))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "k"}
        )
        payload = json.loads(result.message)
        assert payload["query"] == "k"
        row = payload["matched_entries"][0]
        assert row["entry_id"] == "x"
        assert row["tags"] == ["k"]
        assert row["importance_score"] == 7
        assert row["match_score"] > 0
        assert row["summary"] == "ok"

    def test_returns_store_empty_success(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """「思い出そうとしたが何もなかった」も正常な検索結果。"""
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "X"}
        )
        assert result.success is True
        payload = json.loads(result.message)
        assert payload["matched_entries"] == []
