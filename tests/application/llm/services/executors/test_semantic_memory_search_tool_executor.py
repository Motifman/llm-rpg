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
def executor() -> SemanticMemorySearchToolExecutor:
    store = InMemorySemanticMemoryStore()
    return SemanticMemorySearchToolExecutor(semantic_store=store)


def _add(executor: SemanticMemorySearchToolExecutor, entry: SemanticMemoryEntry) -> None:
    executor.semantic_store.add(entry)


class TestSemanticMemorySearchHandlerRegistration:
    """get_handlers が tool name を返す。"""

    def test_handler_dict_に_tool_name_が_キーとして含まれる(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        assert TOOL_NAME_MEMORY_SEARCH_SEMANTIC in executor.get_handlers()


class TestSemanticMemorySearchArgValidation:
    """引数の境界。"""

    def test_query_が_空文字なら_invalid_argument(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        result = executor._run_search_semantic(player_id=1, arguments={"query": ""})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_query_が_未指定なら_invalid_argument(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        result = executor._run_search_semantic(player_id=1, arguments={})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_query_が_前後空白だけなら_invalid_argument(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "   "}
        )
        assert result.success is False

    def test_top_k_の_非数値は_default_に_縮退(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """top_k='abc' は default 5 として動作する (例外を伝播しない)。"""
        _add(executor, _entry(entry_id="x", tags=("a",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "a", "top_k": "abc"}
        )
        assert result.success is True

    def test_top_k_が_負数_または_0_は_default_に_縮退(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        for raw in (0, -3):
            result = executor._run_search_semantic(
                player_id=1, arguments={"query": "a", "top_k": raw}
            )
            assert result.success is True

    def test_top_k_が_最大値_を超えたら_32_で_cap(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        for i in range(50):
            _add(executor, _entry(entry_id=f"s{i}", text=f"q{i}", tags=("q",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "q", "top_k": 1000}
        )
        payload = json.loads(result.message)
        assert len(payload["matched_entries"]) == 32


class TestSemanticMemorySearchScoring:
    """tag 完全一致 / tag 部分一致 / 本文一致 の score 優先順。"""

    def test_tag_完全一致が_最上位(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        _add(executor, _entry(entry_id="text_only", text="タカシは漁の名手", tags=()))
        _add(executor, _entry(entry_id="exact", text="ある記憶", tags=("タカシ",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "タカシ"}
        )
        payload = json.loads(result.message)
        ids = [row["entry_id"] for row in payload["matched_entries"]]
        assert ids[0] == "exact"

    def test_match_しない_entry_は_結果に出ない(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        _add(executor, _entry(entry_id="match", text="毒キノコ", tags=()))
        _add(executor, _entry(entry_id="miss", text="ココナッツ", tags=()))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "毒"}
        )
        payload = json.loads(result.message)
        ids = [row["entry_id"] for row in payload["matched_entries"]]
        assert ids == ["match"]

    def test_本文部分一致でも_hit_する(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        _add(executor, _entry(entry_id="text", text="北の洞窟は熊の巣", tags=()))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "北の洞窟"}
        )
        payload = json.loads(result.message)
        assert any(row["entry_id"] == "text" for row in payload["matched_entries"])

    def test_case_insensitive_に_match(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """英語混在: tag "Boss" と query "boss" は match する。"""
        _add(executor, _entry(entry_id="b", tags=("Boss",)))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "boss"}
        )
        payload = json.loads(result.message)
        assert payload["matched_entries"][0]["entry_id"] == "b"

    def test_同じ_match_score_なら_importance_が_高い方が_上位(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        _add(executor, _entry(entry_id="low", tags=("q",), importance_score=3))
        _add(executor, _entry(entry_id="high", tags=("q",), importance_score=9))
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "q"}
        )
        payload = json.loads(result.message)
        assert payload["matched_entries"][0]["entry_id"] == "high"


class TestSemanticMemorySearchPayload:
    """返却 JSON が想定通り。"""

    def test_query_と_matched_entries_が_含まれる(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        _add(executor, _entry(entry_id="x", text="ok", tags=("k",), importance_score=7))
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

    def test_store_が_空でも_success_を返す(
        self, executor: SemanticMemorySearchToolExecutor
    ) -> None:
        """「思い出そうとしたが何もなかった」も正常な検索結果。"""
        result = executor._run_search_semantic(
            player_id=1, arguments={"query": "X"}
        )
        assert result.success is True
        payload = json.loads(result.message)
        assert payload["matched_entries"] == []
