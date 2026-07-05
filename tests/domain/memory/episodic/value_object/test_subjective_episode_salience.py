"""SubjectiveEpisode の salience フィールドが U6 (STRUCTURED_FAILURE + salience)
の一撃学習経路に使える形で安全に出し入れできることを保証する。

heading (Optional, 既定 None) と違い、salience は「値が無い」状態を表現
しない (常に "low" か "high" のどちらか) 必須フィールド。既定値 "low" で
既存の構築箇所が salience を意識せずに作っても壊れない後方互換を保証する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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
        recall_text=None,
    )
    base.update(overrides)
    return SubjectiveEpisode(**base)


class TestSubjectiveEpisodeSalience:
    """salience フィールドの既定値・妥当性検証を保証する。"""

    def test_salience_default_is_low(self) -> None:
        """既存の SubjectiveEpisode 構築箇所が salience を意識せずに作っても
        既定 "low" で壊れない (= U6 導入前と同じ挙動の後方互換)。"""
        ep = _episode()
        assert ep.salience == "low"

    def test_salience_high_is_accepted(self) -> None:
        ep = _episode(salience="high")
        assert ep.salience == "high"

    def test_invalid_salience_raises_value_error(self) -> None:
        """"low"/"high" 以外 (typo 等) は value object 層で弾く。
        parse 段階での正規化 (invalid → "low") は application 層
        (``episodic_chunk_subjective_fields.py`` の ``_normalize_salience``)
        の責務で、この層は正規化済みの値だけを受ける契約にしておく。"""
        with pytest.raises(ValueError):
            _episode(salience="medium")

    def test_empty_salience_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _episode(salience="")
