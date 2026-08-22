"""EpisodicRecallObservation の being_id 必須化を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
_BEING = BeingId("being_w1_p3")


def _obs(*, being_id: BeingId = _BEING) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id="recall-1",
        player_id=3,
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


class TestEpisodicRecallObservationBeingId:
    """being_id 必須・player_id 維持・型検証。"""

    def test_being_id_is_required_field(self) -> None:
        """being_id を渡すと VO が構築できる。"""
        obs = _obs()
        assert obs.being_id == _BEING

    def test_player_id_remains_int(self) -> None:
        """player_id は int のまま保持される。"""
        obs = _obs()
        assert obs.player_id == 3
        assert isinstance(obs.player_id, int)

    def test_non_being_id_raises_type_error(self) -> None:
        """being_id が BeingId でないと TypeError。"""
        with pytest.raises(TypeError, match="being_id must be BeingId"):
            EpisodicRecallObservation(
                recall_id="recall-1",
                player_id=3,
                being_id="being_w1_p3",  # type: ignore[arg-type]
                episode_id="ep-1",
                recalled_at=_NOW,
                source_axes=("temporal",),
                current_state_snapshot="state",
                recent_events_snapshot="events",
                persona_snapshot="persona",
                situation_cues=("cue",),
                turn_index=1,
            )

    def test_non_int_player_id_raises_type_error(self) -> None:
        """player_id が int でないと TypeError。"""
        with pytest.raises(TypeError, match="player_id must be int"):
            EpisodicRecallObservation(
                recall_id="recall-1",
                player_id="3",  # type: ignore[arg-type]
                being_id=_BEING,
                episode_id="ep-1",
                recalled_at=_NOW,
                source_axes=("temporal",),
                current_state_snapshot="state",
                recent_events_snapshot="events",
                persona_snapshot="persona",
                situation_cues=("cue",),
                turn_index=1,
            )
