"""SubjectiveEpisode と周辺契約型の検証テスト。"""

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _minimal_episode(**overrides):
    base = dict(
        episode_id="ep-1",
        player_id=7,
        occurred_at=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        game_time_label="Day 3 · noon",
        source=EpisodeSource(event_ids=("action_evt_42",)),
        location=EpisodeLocation(spot_id=12, tile_area_ids=(3, 4), sub_location_id=9),
        action=EpisodeAction(tool_name="spot_graph_interact", canonical_arguments_text='{"target": 1}'),
        who=("entity:alice", "player:self"),
        what="古い箱を調べた",
        why="罠の有無を確認するため",
        observed="箱を開けると床が沈み、ダメージを受けた",
        expected="中身が見える",
        outcome="失敗（罠発動）",
        prediction_error="安全だと思ったが罠だった",
        felt="caution",
        interpreted=None,
        cues=(
            EpisodicCue(
                axis="place_spot",
                value="12",
                source=EpisodicCueSource.RUNTIME_CONTEXT,
            ),
        ),
        recall_text="地下で箱を開けて罠を踏んだ",
    )
    base.update(overrides)
    return SubjectiveEpisode(**base)


class TestEpisodeSourceAndValidation:
    """ソース参照・必須フィールド・空文字拒否"""

    def test_episode_source_rejects_blank_event_id(self) -> None:
        """event_ids に空文字や空白のみを含めると ValueError になる。"""
        with pytest.raises(ValueError, match="event_ids"):
            EpisodeSource(event_ids=("ok", "  "))

    def test_episode_source_requires_at_least_one_id(self) -> None:
        """追跡可能性のため event_ids が空タプルでは構築できない。"""
        with pytest.raises(ValueError, match="at least one"):
            EpisodeSource(event_ids=())

    def test_subjective_episode_rejects_blank_episode_id(self) -> None:
        """episode_id が空白のみのとき構築できない。"""
        with pytest.raises(ValueError, match="episode_id"):
            _minimal_episode(episode_id="   ")

    def test_subjective_episode_rejects_blank_observed(self) -> None:
        """observed はソース・オブ・トゥルース側の本文であり空文字は拒否する。"""
        with pytest.raises(ValueError, match="observed"):
            _minimal_episode(observed="")

    def test_optional_string_fields_reject_blank(self) -> None:
        """任意文字列フィールドに空文字を渡すと拒否し None のみを許す。"""
        with pytest.raises(ValueError, match="why"):
            _minimal_episode(why="  ")
        with pytest.raises(ValueError, match="expected"):
            _minimal_episode(expected="")
        with pytest.raises(ValueError, match="interpreted"):
            _minimal_episode(interpreted="\t")
        with pytest.raises(ValueError, match="recall_text"):
            _minimal_episode(recall_text="  ")


class TestEpisodicCueCanonical:
    """cue の正規化と canonical 表現"""

    def test_cue_strips_and_lowercases_axis(self) -> None:
        """軸名は前後空白を除去し小文字に正規化してから canonical に使う。"""
        cue = EpisodicCue(
            axis=" Place_SPOT ",
            value=" 12 ",
            source=EpisodicCueSource.RUNTIME_CONTEXT,
        )
        assert cue.axis == "place_spot"
        assert cue.value == "12"
        assert cue.to_canonical() == "place_spot:12"

    def test_cue_axis_must_not_contain_colon(self) -> None:
        """axis に ':' を含めると曖昧になるため拒否する。"""
        with pytest.raises(ValueError, match="axis"):
            EpisodicCue(
                axis="a:b",
                value="c",
                source=EpisodicCueSource.TOOL,
            )


class TestFiveWOneHMinimalShape:
    """5W1H をフィールドに載せられる最小形状"""

    def test_subjective_episode_covers_who_where_what_when_why_how(self) -> None:
        """
        who・場所・時刻・what・why・行動（how）が同時に成立する。
        when は occurred_at（実時間）と任意の game_time_label で表す。
        """
        ep = _minimal_episode()
        assert ep.who
        assert ep.location.spot_id == 12
        assert ep.occurred_at.tzinfo is not None
        assert ep.game_time_label is not None
        assert ep.what
        assert ep.why is not None
        assert ep.action is not None and ep.action.tool_name


class TestInterpretedOptional:
    """LLM 主観フィールドが無くてもエピソードが成立する"""

    def test_llm_subjective_fields_can_be_none(self) -> None:
        """interpreted / recall_text が None でも構築できる（決定論・チャンク草案の土台）。"""
        ep = _minimal_episode(interpreted=None, recall_text=None)
        assert ep.interpreted is None
        assert ep.recall_text is None
