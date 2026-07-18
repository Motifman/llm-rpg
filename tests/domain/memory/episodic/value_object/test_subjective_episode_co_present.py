"""SubjectiveEpisode の co_present フィールドが「その場に居た人 (共在)」を
who (= 実際に動作した人) とは別のエンジン由来の確定事実として安全に出し入れ
できることを保証する (PR-M: 約束清算の共在ゲート誤棄却の修正)。

co_present は who と同じ正規化 (空文字拒否・tuple 検証) を持ち、既定は空タプル。
既存の全構築箇所・snapshot 往復が co_present を意識せずに作っても壊れない
後方互換を保証する。
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
        recall_text=None,
    )
    base.update(overrides)
    return SubjectiveEpisode(**base)


class TestSubjectiveEpisodeCoPresent:
    """co_present フィールドの既定値・正規化・妥当性検証を保証する。"""

    def test_co_present_default_is_empty_tuple(self) -> None:
        """既存の SubjectiveEpisode 構築箇所が co_present を意識せずに作っても
        既定の空タプルで壊れない (= PR-M 導入前と同じ挙動の後方互換)。"""
        ep = _episode()
        assert ep.co_present == ()

    def test_co_present_preserves_given_names(self) -> None:
        """渡した共在者名を tuple としてそのまま保持する。"""
        ep = _episode(co_present=("ノア", "カイ"))
        assert ep.co_present == ("ノア", "カイ")

    def test_co_present_rejects_blank_entry(self) -> None:
        """空文字・空白のみの共在者名は value object 層で弾く (who と同じ正規化)。"""
        with pytest.raises(Exception):
            _episode(co_present=("ノア", "   "))

    def test_co_present_rejects_non_tuple(self) -> None:
        """tuple 以外を渡すと TypeError を投げる (who と同じ型検証)。"""
        with pytest.raises(TypeError):
            _episode(co_present=["ノア"])

    def test_co_present_is_independent_of_who(self) -> None:
        """co_present は who とは独立に保持され、who を書き換えない。"""
        ep = _episode(who=("エイダ",), co_present=("ノア",))
        assert ep.who == ("エイダ",)
        assert ep.co_present == ("ノア",)
