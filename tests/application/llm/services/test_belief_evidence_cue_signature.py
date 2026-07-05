"""build_belief_evidence_cue_signature の決定論性を保証する。

U2 (証拠台帳統一設計 §2 U2): cue_signature は「新しい抽出ロジックを発明
しない」方針で episode の既存構造化フィールドだけから決定論生成される。
同じ素材からは常に同じ文字列が出ることと、tool/spot/player の有無で
出力が変わることを確認する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
    build_belief_evidence_cue_signature,
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
        action=EpisodeAction(tool_name="explore"),
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


class TestBuildBeliefEvidenceCueSignature:
    def test_tool_only(self) -> None:
        """spot / player が無ければ tool 軸だけになる。"""
        episode = _episode(action=EpisodeAction(tool_name="explore"))
        assert build_belief_evidence_cue_signature(episode) == "tool:explore"

    def test_tool_and_spot(self) -> None:
        episode = _episode(
            action=EpisodeAction(tool_name="explore"),
            location=EpisodeLocation(spot_id=3),
        )
        assert build_belief_evidence_cue_signature(episode) == "tool:explore|spot:3"

    def test_tool_spot_and_player(self) -> None:
        episode = _episode(
            action=EpisodeAction(tool_name="speech_say"),
            location=EpisodeLocation(spot_id=3),
            who=("ノア",),
        )
        assert (
            build_belief_evidence_cue_signature(episode)
            == "tool:speech_say|spot:3|player:ノア"
        )

    def test_no_action_falls_back_to_tool_none(self) -> None:
        """action が None の episode (world event 由来等) でも必ず tool 軸が
        先頭に立つ (= 空文字にならない不変条件)。"""
        episode = _episode(action=None)
        assert build_belief_evidence_cue_signature(episode) == "tool:none"

    def test_only_first_who_entry_is_used(self) -> None:
        """複数人が who に居ても cue_signature は最初の 1 人だけを使う
        (決定論性: 順序が固定されている限り同じ出力になる)。"""
        episode = _episode(who=("ノア", "ミラ"))
        assert build_belief_evidence_cue_signature(episode).endswith("player:ノア")

    def test_deterministic_for_same_material(self) -> None:
        """同じ episode フィールドからは何度呼んでも同じ文字列になる。"""
        episode = _episode(
            action=EpisodeAction(tool_name="gather"),
            location=EpisodeLocation(spot_id=7),
            who=("ミラ",),
        )
        first = build_belief_evidence_cue_signature(episode)
        second = build_belief_evidence_cue_signature(episode)
        assert first == second

    def test_rejects_non_episode_argument(self) -> None:
        with pytest.raises(TypeError):
            build_belief_evidence_cue_signature("not-an-episode")
