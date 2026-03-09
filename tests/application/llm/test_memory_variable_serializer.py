"""memory_variable_serializer のテスト（正常・境界・例外）"""

from datetime import datetime

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeMemoryEntry,
    LongTermFactEntry,
    MemoryLawEntry,
)
from ai_rpg_world.application.llm.services.memory_variable_serializer import (
    episode_to_dict,
    episodes_to_dicts,
    fact_to_dict,
    facts_to_dicts,
    law_to_dict,
    laws_to_dicts,
)


def _make_episode(eid: str = "e1") -> EpisodeMemoryEntry:
    return EpisodeMemoryEntry(
        id=eid,
        context_summary="洞窟にいた",
        action_taken="move_to を実行",
        outcome_summary="到着した",
        entity_ids=("loc_1",),
        location_id="洞窟",
        timestamp=datetime.now(),
        importance="medium",
        surprise=False,
        recall_count=0,
    )


def _make_fact(fid: str = "f1", content: str = "スライムは火が弱い") -> LongTermFactEntry:
    return LongTermFactEntry(
        id=fid,
        content=content,
        player_id=1,
        updated_at=datetime.now(),
    )


def _make_law(lid: str = "l1") -> MemoryLawEntry:
    return MemoryLawEntry(
        id=lid,
        subject="移動",
        relation="すると",
        target="到着",
        strength=1.0,
        player_id=1,
    )


class TestEpisodeToDict:
    """episode_to_dict の正常・例外ケース"""

    def test_converts_episode_to_dict(self):
        """EpisodeMemoryEntry を dict に変換"""
        entry = _make_episode("e1")
        got = episode_to_dict(entry)
        assert got["id"] == "e1"
        assert got["context_summary"] == "洞窟にいた"
        assert got["action_taken"] == "move_to を実行"
        assert got["location_id"] == "洞窟"
        assert "timestamp" in got
        assert got["importance"] == "medium"
        assert got["recall_count"] == 0

    def test_entry_none_raises_type_error(self):
        """entry が None のとき TypeError"""
        with pytest.raises(TypeError, match="entry must not be None"):
            episode_to_dict(None)  # type: ignore[arg-type]

    def test_entry_wrong_type_raises_type_error(self):
        """entry が EpisodeMemoryEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="entry must be EpisodeMemoryEntry"):
            episode_to_dict(_make_fact())  # type: ignore[arg-type]


class TestFactToDict:
    """fact_to_dict の正常・例外ケース"""

    def test_converts_fact_to_dict(self):
        """LongTermFactEntry を dict に変換"""
        entry = _make_fact("f1", "スライムは火が弱い")
        got = fact_to_dict(entry)
        assert got["id"] == "f1"
        assert got["content"] == "スライムは火が弱い"
        assert "updated_at" in got

    def test_entry_none_raises_type_error(self):
        """entry が None のとき TypeError"""
        with pytest.raises(TypeError, match="entry must not be None"):
            fact_to_dict(None)  # type: ignore[arg-type]

    def test_entry_wrong_type_raises_type_error(self):
        """entry が LongTermFactEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="entry must be LongTermFactEntry"):
            fact_to_dict(_make_episode())  # type: ignore[arg-type]


class TestLawToDict:
    """law_to_dict の正常・例外ケース"""

    def test_converts_law_to_dict(self):
        """MemoryLawEntry を dict に変換"""
        entry = _make_law("l1")
        got = law_to_dict(entry)
        assert got["id"] == "l1"
        assert got["subject"] == "移動"
        assert got["relation"] == "すると"
        assert got["target"] == "到着"
        assert got["strength"] == 1.0

    def test_entry_none_raises_type_error(self):
        """entry が None のとき TypeError"""
        with pytest.raises(TypeError, match="entry must not be None"):
            law_to_dict(None)  # type: ignore[arg-type]

    def test_entry_wrong_type_raises_type_error(self):
        """entry が MemoryLawEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="entry must be MemoryLawEntry"):
            law_to_dict(_make_episode())  # type: ignore[arg-type]


class TestEpisodesToDicts:
    """episodes_to_dicts の正常・例外ケース"""

    def test_converts_list_to_dicts(self):
        """EpisodeMemoryEntry のリストを dict のリストに変換"""
        entries = [_make_episode("e1"), _make_episode("e2")]
        got = episodes_to_dicts(entries)
        assert len(got) == 2
        assert got[0]["id"] == "e1"
        assert got[1]["id"] == "e2"

    def test_empty_list_returns_empty(self):
        """空リストは空リストを返す"""
        assert episodes_to_dicts([]) == []

    def test_entries_none_raises_type_error(self):
        """entries が None のとき TypeError"""
        with pytest.raises(TypeError, match="entries must not be None"):
            episodes_to_dicts(None)  # type: ignore[arg-type]

    def test_entries_not_list_raises_type_error(self):
        """entries が list でないとき TypeError"""
        with pytest.raises(TypeError, match="entries must be list"):
            episodes_to_dicts("not a list")  # type: ignore[arg-type]

    def test_entries_contains_none_raises_type_error(self):
        """entries に None が含まれるとき episode_to_dict で TypeError"""
        with pytest.raises(TypeError, match="entry must not be None"):
            episodes_to_dicts([_make_episode(), None])  # type: ignore[list-item]


class TestFactsToDicts:
    """facts_to_dicts の正常・例外ケース"""

    def test_converts_list_to_dicts(self):
        """LongTermFactEntry のリストを dict のリストに変換"""
        entries = [_make_fact("f1"), _make_fact("f2")]
        got = facts_to_dicts(entries)
        assert len(got) == 2
        assert got[0]["id"] == "f1"
        assert got[1]["id"] == "f2"

    def test_empty_list_returns_empty(self):
        """空リストは空リストを返す"""
        assert facts_to_dicts([]) == []

    def test_entries_none_raises_type_error(self):
        """entries が None のとき TypeError"""
        with pytest.raises(TypeError, match="entries must not be None"):
            facts_to_dicts(None)  # type: ignore[arg-type]

    def test_entries_not_list_raises_type_error(self):
        """entries が list でないとき TypeError"""
        with pytest.raises(TypeError, match="entries must be list"):
            facts_to_dicts({})  # type: ignore[arg-type]


class TestLawsToDicts:
    """laws_to_dicts の正常・例外ケース"""

    def test_converts_list_to_dicts(self):
        """MemoryLawEntry のリストを dict のリストに変換"""
        entries = [_make_law("l1"), _make_law("l2")]
        got = laws_to_dicts(entries)
        assert len(got) == 2
        assert got[0]["subject"] == "移動"
        assert got[1]["subject"] == "移動"

    def test_empty_list_returns_empty(self):
        """空リストは空リストを返す"""
        assert laws_to_dicts([]) == []

    def test_entries_none_raises_type_error(self):
        """entries が None のとき TypeError"""
        with pytest.raises(TypeError, match="entries must not be None"):
            laws_to_dicts(None)  # type: ignore[arg-type]

    def test_entries_not_list_raises_type_error(self):
        """entries が list でないとき TypeError"""
        with pytest.raises(TypeError, match="entries must be list"):
            laws_to_dicts(123)  # type: ignore[arg-type]
