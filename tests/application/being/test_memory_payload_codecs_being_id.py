"""SubjectiveEpisode / MemoryLink / SemanticMemoryEntry snapshot codec の being_id 往復と旧形式 fallback を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import (
    dict_to_memory_link,
    dict_to_semantic_entry,
    dict_to_subjective_episode,
    memory_link_to_dict,
    semantic_entry_to_dict,
    subjective_episode_to_dict,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)


_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(
        episode_id="ep-1",
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="t"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )
    base.update(overrides)
    if "being_id" not in overrides:
        base["being_id"] = BeingId(f"being_w1_p{base['player_id']}")
    return SubjectiveEpisode(**base)


class TestSubjectiveEpisodeCodecBeingId:
    """being_id の encode / decode と旧 snapshot 互換を保証する。"""

    def test_new_format_round_trips_being_id(self) -> None:
        """新形式 payload は being_id を往復する。"""
        ep = _episode(being_id=BeingId("being_w1_p9"))
        restored = dict_to_subjective_episode(subjective_episode_to_dict(ep))
        assert restored.being_id == BeingId("being_w1_p9")

    def test_old_format_uses_fallback_being_id(self) -> None:
        """being_id キーが無い旧 snapshot は fallback から復元できる。"""
        ep = _episode()
        payload = subjective_episode_to_dict(ep)
        del payload["being_id"]
        fallback = BeingId("being_w1_p1")
        restored = dict_to_subjective_episode(payload, fallback_being_id=fallback)
        assert restored.being_id == fallback

    def test_old_format_without_fallback_fails(self) -> None:
        """being_id キーも fallback も無いと decode は失敗する。"""
        ep = _episode()
        payload = subjective_episode_to_dict(ep)
        del payload["being_id"]
        with pytest.raises(ValueError, match="being_id is required"):
            dict_to_subjective_episode(payload)

    def test_payload_and_fallback_mismatch_fails(self) -> None:
        """payload の being_id と fallback が不一致なら失敗する。"""
        ep = _episode(being_id=BeingId("being_a"))
        payload = subjective_episode_to_dict(ep)
        with pytest.raises(ValueError, match="does not match snapshot being"):
            dict_to_subjective_episode(payload, fallback_being_id=BeingId("being_b"))


def _memory_link(**overrides) -> MemoryLink:
    base = dict(
        link_id="mlk-1",
        player_id=1,
        episode_id_a="ep-1",
        episode_id_b="ep-2",
        link_type=MemoryLinkType.CO_RECALL,
        strength=0.9,
        co_activation_count=1,
        created_at=_NOW,
        last_activated_at=_NOW,
        decay_rate=0.001,
    )
    base.update(overrides)
    if "being_id" not in overrides:
        base["being_id"] = BeingId(f"being_w1_p{base['player_id']}")
    return MemoryLink(**base)


class TestMemoryLinkCodecBeingId:
    """MemoryLink の being_id encode / decode と旧 snapshot 互換を保証する。"""

    def test_new_format_round_trips_being_id(self) -> None:
        """新形式 payload は being_id を往復する。"""
        link = _memory_link(being_id=BeingId("being_w1_p9"))
        restored = dict_to_memory_link(memory_link_to_dict(link))
        assert restored.being_id == BeingId("being_w1_p9")

    def test_old_format_uses_fallback_being_id(self) -> None:
        """being_id キーが無い旧 snapshot は fallback から復元できる。"""
        link = _memory_link()
        payload = memory_link_to_dict(link)
        del payload["being_id"]
        fallback = BeingId("being_w1_p1")
        restored = dict_to_memory_link(payload, fallback_being_id=fallback)
        assert restored.being_id == fallback

    def test_old_format_without_fallback_fails(self) -> None:
        """being_id キーも fallback も無いと decode は失敗する。"""
        link = _memory_link()
        payload = memory_link_to_dict(link)
        del payload["being_id"]
        with pytest.raises(ValueError, match="being_id is required"):
            dict_to_memory_link(payload)

    def test_payload_and_fallback_mismatch_fails(self) -> None:
        """payload の being_id と fallback が不一致なら失敗する。"""
        link = _memory_link(being_id=BeingId("being_a"))
        payload = memory_link_to_dict(link)
        with pytest.raises(ValueError, match="does not match snapshot being"):
            dict_to_memory_link(payload, fallback_being_id=BeingId("being_b"))


def _semantic_entry(**overrides) -> SemanticMemoryEntry:
    base = dict(
        entry_id="sem-1",
        player_id=1,
        text="探索は空振りが多い",
        evidence_episode_ids=("ep-1",),
        confidence=0.6,
        created_at=_NOW,
    )
    base.update(overrides)
    if "being_id" not in overrides:
        base["being_id"] = BeingId(f"being_w1_p{base['player_id']}")
    return SemanticMemoryEntry(**base)


class TestSemanticMemoryEntryCodecBeingId:
    """SemanticMemoryEntry の being_id encode / decode と旧 snapshot 互換を保証する。"""

    def test_new_format_round_trips_being_id(self) -> None:
        """新形式 payload は being_id を往復する。"""
        entry = _semantic_entry(being_id=BeingId("being_w1_p9"))
        restored = dict_to_semantic_entry(semantic_entry_to_dict(entry))
        assert restored.being_id == BeingId("being_w1_p9")

    def test_old_format_uses_fallback_being_id(self) -> None:
        """being_id キーが無い旧 snapshot は fallback から復元できる。"""
        entry = _semantic_entry()
        payload = semantic_entry_to_dict(entry)
        del payload["being_id"]
        fallback = BeingId("being_w1_p1")
        restored = dict_to_semantic_entry(payload, fallback_being_id=fallback)
        assert restored.being_id == fallback

    def test_old_format_without_fallback_fails(self) -> None:
        """being_id キーも fallback も無いと decode は失敗する。"""
        entry = _semantic_entry()
        payload = semantic_entry_to_dict(entry)
        del payload["being_id"]
        with pytest.raises(ValueError, match="being_id is required"):
            dict_to_semantic_entry(payload)

    def test_payload_and_fallback_mismatch_fails(self) -> None:
        """payload の being_id と fallback が不一致なら失敗する。"""
        entry = _semantic_entry(being_id=BeingId("being_a"))
        payload = semantic_entry_to_dict(entry)
        with pytest.raises(ValueError, match="does not match snapshot being"):
            dict_to_semantic_entry(payload, fallback_being_id=BeingId("being_b"))
