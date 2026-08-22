"""SubjectiveEpisode / MemoryLink / SemanticMemoryEntry / EpisodicReinterpretationEntry /
EpisodicRecallObservation snapshot codec の being_id 往復と旧形式 fallback を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import (
    dict_to_memory_link,
    dict_to_recall_observation,
    dict_to_reinterpretation_entry,
    dict_to_semantic_entry,
    dict_to_subjective_episode,
    memory_link_to_dict,
    recall_observation_to_dict,
    reinterpretation_entry_to_dict,
    semantic_entry_to_dict,
    subjective_episode_to_dict,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)


_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)
_REINTERP_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
_BEING = BeingId("being_w1_p1")
_OTHER = BeingId("being_w1_p2")


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


def _reinterpretation_entry(*, being_id: BeingId = _BEING) -> EpisodicReinterpretationEntry:
    return EpisodicReinterpretationEntry(
        entry_id="je-1",
        player_id=1,
        being_id=being_id,
        episode_id="ep-1",
        created_at=_REINTERP_NOW,
        turn_index=5,
        current_interpretation="interp",
        current_recall_text="recall text",
        source_recall_ids=("r-1",),
        status=EpisodicReinterpretationStatus.ACTIVE,
    )


class TestReinterpretationEntryCodecBeingId:
    """reinterpretation journal codec の being_id 契約。"""

    def test_round_trip_preserves_being_id(self) -> None:
        """往復で being_id が保持される。"""
        original = _reinterpretation_entry()
        data = reinterpretation_entry_to_dict(original)
        assert data["being_id"] == _BEING.value
        restored = dict_to_reinterpretation_entry(data, fallback_being_id=_BEING)
        assert restored == original

    def test_legacy_payload_without_being_id_uses_fallback(self) -> None:
        """旧形式 (being_id キー無し) は fallback から復元する。"""
        data = reinterpretation_entry_to_dict(_reinterpretation_entry())
        del data["being_id"]
        restored = dict_to_reinterpretation_entry(data, fallback_being_id=_BEING)
        assert restored.being_id == _BEING

    def test_missing_being_id_and_no_fallback_raises(self) -> None:
        """being_id も fallback も無いと ValueError。"""
        data = reinterpretation_entry_to_dict(_reinterpretation_entry())
        del data["being_id"]
        with pytest.raises(
            ValueError,
            match="being_id is required to decode EpisodicReinterpretationEntry",
        ):
            dict_to_reinterpretation_entry(data)

    def test_payload_and_fallback_mismatch_raises(self) -> None:
        """payload と fallback の being_id が不一致なら ValueError。"""
        data = reinterpretation_entry_to_dict(_reinterpretation_entry(being_id=_OTHER))
        with pytest.raises(
            ValueError,
            match="reinterpretation entry being_id does not match snapshot being",
        ):
            dict_to_reinterpretation_entry(data, fallback_being_id=_BEING)


def _recall_observation(*, being_id: BeingId = _BEING) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id="recall-1",
        player_id=1,
        being_id=being_id,
        episode_id="ep-1",
        recalled_at=_NOW,
        source_axes=("temporal",),
        current_state_snapshot="state",
        recent_events_snapshot="events",
        persona_snapshot="persona",
        situation_cues=("cue",),
        turn_index=1,
    )


class TestRecallObservationCodecBeingId:
    """recall buffer codec の being_id 契約。"""

    def test_round_trip_preserves_being_id(self) -> None:
        """往復で being_id が保持される。"""
        original = _recall_observation(being_id=BeingId("being_w1_p9"))
        data = recall_observation_to_dict(original)
        assert data["being_id"] == "being_w1_p9"
        restored = dict_to_recall_observation(data)
        assert restored == original

    def test_legacy_payload_without_being_id_uses_fallback(self) -> None:
        """旧形式 (being_id キー無し) は fallback から復元する。"""
        data = recall_observation_to_dict(_recall_observation())
        del data["being_id"]
        restored = dict_to_recall_observation(data, fallback_being_id=_BEING)
        assert restored.being_id == _BEING

    def test_missing_being_id_and_no_fallback_raises(self) -> None:
        """being_id も fallback も無いと ValueError。"""
        data = recall_observation_to_dict(_recall_observation())
        del data["being_id"]
        with pytest.raises(
            ValueError,
            match="being_id is required to decode EpisodicRecallObservation",
        ):
            dict_to_recall_observation(data)

    def test_payload_and_fallback_mismatch_raises(self) -> None:
        """payload と fallback の being_id が不一致なら ValueError。"""
        data = recall_observation_to_dict(_recall_observation(being_id=_OTHER))
        with pytest.raises(
            ValueError,
            match="recall observation being_id does not match snapshot being",
        ):
            dict_to_recall_observation(data, fallback_being_id=_BEING)

