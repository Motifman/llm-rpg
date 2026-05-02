"""MemoryContextPack（§2.7）と最小組み立てのテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.memory_context_pack import MemoryContextPack
from ai_rpg_world.application.llm.services.memory_context_pack_assembly import (
    assemble_memory_context_pack_for_recall_turn,
)


def test_memory_context_pack_empty_factory() -> None:
    p = MemoryContextPack.empty()
    assert p.current_situation == ""
    assert p.focus_episode_id is None
    assert p.co_recalled_episode_ids == ()


def test_memory_context_pack_rejects_empty_string_in_tuple() -> None:
    with pytest.raises(ValueError, match="temporal_neighbor"):
        MemoryContextPack(temporal_neighbor_episode_ids=("a", ""))


def test_memory_context_pack_rejects_blank_focus_id() -> None:
    with pytest.raises(ValueError, match="focus_episode_id"):
        MemoryContextPack(focus_episode_id="   ")


def test_assemble_for_recall_turn_sets_focus_and_co_recalled() -> None:
    p = assemble_memory_context_pack_for_recall_turn(
        situation_summary="霧の広場。",
        current_goals="出口を探す",
        current_attention="足音",
        recalled_episode_ids=("ep-a", "ep-b"),
    )
    assert p.current_situation == "霧の広場。"
    assert p.current_goals == "出口を探す"
    assert p.current_attention == "足音"
    assert p.focus_episode_id == "ep-a"
    assert p.co_recalled_episode_ids == ("ep-a", "ep-b")


def test_assemble_for_recall_turn_no_recall() -> None:
    p = assemble_memory_context_pack_for_recall_turn(
        situation_summary="静か",
        current_goals="",
        recalled_episode_ids=(),
    )
    assert p.focus_episode_id is None
    assert p.co_recalled_episode_ids == ()


def test_semantic_context_tuple_validation() -> None:
    p = MemoryContextPack(semantic_context=("罠に注意",))
    assert p.semantic_context == ("罠に注意",)
