"""SubjectiveEpisode が経験の主体 BeingId を必須で持つことを保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)


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
        who=("p",),
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


class TestSubjectiveEpisodeBeingId:
    """being_id 必須と型検証を保証する。"""

    def test_being_id_is_required(self) -> None:
        """being_id を欠くと dataclass 必須フィールドとして TypeError になる。"""
        with pytest.raises(TypeError):
            SubjectiveEpisode(
                episode_id="ep-1",
                player_id=1,
                occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                game_time_label=None,
                source=EpisodeSource(event_ids=("evt-1",)),
                location=EpisodeLocation(),
                action=EpisodeAction(tool_name="t"),
                who=("p",),
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

    def test_non_being_id_raises_type_error(self) -> None:
        """being_id に BeingId 以外を渡すと TypeError になる。"""
        with pytest.raises(TypeError, match="being_id must be BeingId"):
            _episode(being_id="not-a-being-id")  # type: ignore[arg-type]

    def test_player_id_remains_int(self) -> None:
        """player_id は attach 元の身体として int のまま残る。"""
        ep = _episode(player_id=42)
        assert ep.player_id == 42
        assert ep.being_id == BeingId("being_w1_p42")
