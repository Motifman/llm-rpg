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


# ── P9 (伝聞): build_hearsay_cue_signature ──

from dataclasses import dataclass

from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
    build_hearsay_cue_signature,
)


@dataclass
class _FakeMatch:
    axis: str
    value: str
    start: int


class _FakeMatcher:
    """find_in_text が固定の NounMatch もどきを返す fake。"""

    def __init__(self, matches):
        self._matches = matches

    def find_in_text(self, text):  # noqa: ARG002
        return tuple(self._matches)


class TestBuildHearsayCueSignature:
    """P9: 伝聞の主張から対象を拾って cue を決める (話者は混ぜない)。"""

    def test_spot_target_gives_spot_axis(self) -> None:
        """主張の対象が場所なら spot: 軸。"""
        matcher = _FakeMatcher([_FakeMatch(axis="place_spot", value="12", start=3)])
        assert build_hearsay_cue_signature("岩礁海岸は危ない", matcher) == "spot:12"

    def test_person_target_gives_player_axis(self) -> None:
        """主張の対象が他者なら player: 軸。値は直接体験と揃えた entity:actor:{id} 形式 (P10)。"""
        matcher = _FakeMatcher(
            [_FakeMatch(axis="entity", value="spot_graph_player_5", start=0)]
        )
        assert (
            build_hearsay_cue_signature("エイダは頼りになる", matcher)
            == "player:entity:actor:5"
        )

    def test_person_target_clusters_with_direct_experience_cue(self) -> None:
        """P10: 同一人物の伝聞 cue と直接体験 cue が同じ cue トークンを生む。

        直接体験側の cue は手書きせず、実際の ``build_belief_evidence_cue_signature``
        に chunk episode 相当 (who = ``entity:actor:5`` = chunk の
        ``_who_from_observations`` が観測 actor から生成する形式) を通して導出する。
        こうすることで、揃え先が「実際に belief evidence になる直接体験 cue」で
        あることを固定し、片方の生成規則が変わったらテストが割れるようにする
        (揃っていないと同じ人物の伝聞と体験が別クラスタになり strengthen/contradict
        できず重複 create を生む)。
        """
        from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
            cue_tokens,
        )

        matcher = _FakeMatcher(
            [_FakeMatch(axis="entity", value="spot_graph_player_5", start=0)]
        )
        hearsay_cue = build_hearsay_cue_signature("エイダは頼りになる", matcher)
        # 直接体験: エイダ (player 5) が観測 actor として現れた chunk episode。
        direct_episode = _episode(who=("entity:actor:5",))
        direct_cue = build_belief_evidence_cue_signature(direct_episode)
        common = set(cue_tokens(hearsay_cue)) & set(cue_tokens(direct_cue))
        assert "entity:actor:5" in common

    def test_self_reference_gives_self_axis(self) -> None:
        """対象が聞き手本人なら self: 軸 (その人物についての belief と別枠)。"""
        matcher = _FakeMatcher(
            [_FakeMatch(axis="entity", value="spot_graph_player_7", start=0)]
        )
        cue = build_hearsay_cue_signature(
            "カイは人の話を聞かない", matcher, self_player_id=7
        )
        assert cue == "self:entity:actor:7"

    def test_other_person_not_confused_with_self(self) -> None:
        matcher = _FakeMatcher(
            [_FakeMatch(axis="entity", value="spot_graph_player_5", start=0)]
        )
        cue = build_hearsay_cue_signature("リオは詳しい", matcher, self_player_id=7)
        assert cue == "player:entity:actor:5"

    def test_earliest_match_wins(self) -> None:
        matcher = _FakeMatcher(
            [
                _FakeMatch(axis="entity", value="spot_graph_player_5", start=10),
                _FakeMatch(axis="place_spot", value="3", start=2),
            ]
        )
        assert build_hearsay_cue_signature("北の森でリオが", matcher) == "spot:3"

    def test_no_target_gives_empty_cue(self) -> None:
        """対象を特定できない主張は cue なし (固着の discard に委ねる)。"""
        assert build_hearsay_cue_signature("よく分からない話", _FakeMatcher([])) == ""

    def test_no_matcher_gives_empty_cue(self) -> None:
        assert build_hearsay_cue_signature("何か", None) == ""
