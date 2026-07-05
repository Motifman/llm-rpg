"""SubjectiveEpisode の snapshot codec (``_memory_payload_codecs``) が
salience (U6) を round-trip し、旧 snapshot (salience キー無し) を
"low" にフォールバックすることを保証する。

heading と違い salience は必須フィールド (常に low/high) なので、
「キーが無い旧データ」は例外にせず "low" として読める後方互換が要件。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.being._memory_payload_codecs import (
    dict_to_subjective_episode,
    subjective_episode_to_dict,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


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
    return SubjectiveEpisode(**base)


class TestSubjectiveEpisodeCodecSalienceRoundTrip:
    def test_low_salience_round_trips(self) -> None:
        ep = _episode(salience="low")
        restored = dict_to_subjective_episode(subjective_episode_to_dict(ep))
        assert restored.salience == "low"

    def test_high_salience_round_trips(self) -> None:
        ep = _episode(salience="high")
        restored = dict_to_subjective_episode(subjective_episode_to_dict(ep))
        assert restored.salience == "high"

    def test_missing_salience_key_in_old_payload_defaults_to_low(self) -> None:
        """U6 導入前に保存された snapshot (salience キーが無い) を読んでも
        壊れず "low" にフォールバックする。"""
        ep = _episode(salience="low")
        payload = subjective_episode_to_dict(ep)
        del payload["salience"]

        restored = dict_to_subjective_episode(payload)

        assert restored.salience == "low"
