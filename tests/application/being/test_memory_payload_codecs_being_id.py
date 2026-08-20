"""SubjectiveEpisode snapshot codec の being_id 往復と旧形式 fallback を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import (
    dict_to_subjective_episode,
    subjective_episode_to_dict,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(
        episode_id="ep-1",
        player_id=1,
        being_id=BeingId("being-test"),
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
    if 'being_id' not in overrides:
        base['being_id'] = BeingId(f"being_w1_p{base['player_id']}")
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
