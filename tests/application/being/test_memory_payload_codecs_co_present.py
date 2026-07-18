"""SubjectiveEpisode の snapshot codec (``_memory_payload_codecs``) が
co_present (PR-M) を round-trip し、旧 snapshot (co_present キー無し) を
空タプルにフォールバックすることを保証する。

co_present は who と同じくエンジン由来の確定事実で、長走実験の終了 → 再開で
共在情報が静かに失われないよう snapshot に乗せる。旧データとの後方互換の
ため、キーが無い場合は例外にせず空タプルとして読む。
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
        who=("エイダ",),
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


class TestSubjectiveEpisodeCodecCoPresentRoundTrip:
    def test_co_present_round_trips(self) -> None:
        """co_present が snapshot の書き出し → 読み戻しで保存される。"""
        ep = _episode(co_present=("ノア", "カイ"))
        restored = dict_to_subjective_episode(subjective_episode_to_dict(ep))
        assert restored.co_present == ("ノア", "カイ")

    def test_empty_co_present_round_trips(self) -> None:
        """共在者が居ない (空) 場合も空タプルとして round-trip する。"""
        ep = _episode(co_present=())
        restored = dict_to_subjective_episode(subjective_episode_to_dict(ep))
        assert restored.co_present == ()

    def test_missing_co_present_key_in_old_payload_defaults_to_empty(self) -> None:
        """PR-M 導入前に保存された snapshot (co_present キーが無い) を読んでも
        壊れず空タプルにフォールバックする。"""
        ep = _episode(co_present=("ノア",))
        payload = subjective_episode_to_dict(ep)
        del payload["co_present"]

        restored = dict_to_subjective_episode(payload)

        assert restored.co_present == ()
