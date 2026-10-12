"""build_belief_evidence_cue_signature の決定論性を保証する。

U2 (証拠台帳統一設計 §2 U2): cue_signature は「新しい抽出ロジックを発明
しない」方針で episode の既存構造化フィールドだけから決定論生成される。
同じ素材からは常に同じ文字列が出ることと、tool/spot/player の有無で
出力が変わることを確認する。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
    build_belief_evidence_cue_signature,
    build_goal_stagnation_cue_signature,
    cue_tokens,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(episode_id='ep-1', player_id=1, occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc), game_time_label=None, source=EpisodeSource(event_ids=('evt-1',)), location=EpisodeLocation(), action=EpisodeAction(tool_name='explore'), who=(), what='w', why=None, observed='o', expected=None, outcome='ok', prediction_error=None, felt=None, interpreted=None, cues=())
    base.update(overrides)
    if 'being_id' not in overrides:
        base['being_id'] = BeingId(f"being_w1_p{base['player_id']}")
    return SubjectiveEpisode(**base)

class TestBuildBeliefEvidenceCueSignature:

    def test_tool_only(self) -> None:
        """spot / player が無ければ tool 軸だけになる。"""
        episode = _episode(action=EpisodeAction(tool_name='explore'))
        assert build_belief_evidence_cue_signature(episode) == 'tool:explore'

    def test_tool_and_spot(self) -> None:
        episode = _episode(action=EpisodeAction(tool_name='explore'), location=EpisodeLocation(spot_id=3))
        assert build_belief_evidence_cue_signature(episode) == 'tool:explore|spot:3'

    def test_tool_spot_and_player(self) -> None:
        episode = _episode(action=EpisodeAction(tool_name='speech_say'), location=EpisodeLocation(spot_id=3), who=('ノア',))
        assert build_belief_evidence_cue_signature(episode) == 'tool:speech_say|spot:3|player:ノア'

    def test_no_action_falls_back_to_tool_none(self) -> None:
        """action が None の episode (world event 由来等) でも必ず tool 軸が
        先頭に立つ (= 空文字にならない不変条件)。"""
        episode = _episode(action=None)
        assert build_belief_evidence_cue_signature(episode) == 'tool:none'

    def test_only_first_who_entry_is_used(self) -> None:
        """複数人が who に居ても cue_signature は最初の 1 人だけを使う
        (決定論性: 順序が固定されている限り同じ出力になる)。"""
        episode = _episode(who=('ノア', 'ミラ'))
        assert build_belief_evidence_cue_signature(episode).endswith('player:ノア')

    def test_deterministic_for_same_material(self) -> None:
        """同じ episode フィールドからは何度呼んでも同じ文字列になる。"""
        episode = _episode(action=EpisodeAction(tool_name='gather'), location=EpisodeLocation(spot_id=7), who=('ミラ',))
        first = build_belief_evidence_cue_signature(episode)
        second = build_belief_evidence_cue_signature(episode)
        assert first == second

    def test_rejects_non_episode_argument(self) -> None:
        with pytest.raises(TypeError):
            build_belief_evidence_cue_signature('not-an-episode')
class TestSelfAxisSeparationInCueTokens:
    """self: 軸の cue が、照合トークン層で同一人物の player: 軸の cue と別クラスタに保たれることを保証する。

    ``cue_tokens`` が最初の ``:`` で軸接頭辞を剥がすと ``self:entity:actor:7`` と
    ``player:entity:actor:7`` が同じトークンに潰れる。保存済みの belief に self: 軸の
    cue が残っているので、伝聞の部品を消したあと (#1631) も分離を保つ。
    """

    def test_self_and_player_tokens_of_same_person_do_not_collide(self) -> None:
        """同一人物 (player 7) の self: 軸の cue と player: 軸の cue は共通トークンを持たない。"""
        assert set(cue_tokens('self:entity:actor:7')) & set(cue_tokens('player:entity:actor:7')) == set()

    def test_self_token_does_not_collide_with_direct_experience_of_same_person(self) -> None:
        """self: 軸の cue は、同一人物 (player 7) の直接体験の cue とも共通トークンを持たない。"""
        direct_cue = build_belief_evidence_cue_signature(_episode(who=('entity:actor:7',)))
        assert set(cue_tokens('self:entity:actor:7')) & set(cue_tokens(direct_cue)) == set()

    def test_self_cues_of_same_person_share_token(self) -> None:
        """同じ本人 (player 7) についての self: 軸の cue どうしは同じトークンを持つ。"""
        assert set(cue_tokens('self:entity:actor:7')) & set(cue_tokens('self:entity:actor:7'))

class TestGoalStagnationCueSignature:
    """P-U1: build_goal_stagnation_cue_signature が goal: 軸の cue_signature を
    決定論的に組み立てる挙動を保証する。"""

    def test_same_objective_text_yields_same_cue_signature(self) -> None:
        """同じ目的文からは常に同じ cue_signature が出る (繰り返し停滞が同一
        cue に積み上がり、cue_signature_repeat_threshold の早期 flush に乗る)。"""
        first = build_goal_stagnation_cue_signature('山頂へ行く')
        second = build_goal_stagnation_cue_signature('山頂へ行く')
        assert first == second == 'goal:山頂へ行く'

    def test_different_objective_text_yields_different_cue_signature(self) -> None:
        """目的が違えば cue_signature も分かれる (異なる目的の停滞が同じ
        belief にまとまらない)。"""
        a = build_goal_stagnation_cue_signature('山頂へ行く')
        b = build_goal_stagnation_cue_signature('古い地図を手に入れる')
        assert a != b

    def test_pipe_character_is_normalized_to_avoid_axis_collision(self) -> None:
        """目的文に含まれる "|" は cue_signature の軸区切りと衝突するため
        空白に正規化される。"""
        cue = build_goal_stagnation_cue_signature('山頂へ行く|狼煙を上げる')
        assert '|' not in cue
        assert cue == 'goal:山頂へ行く 狼煙を上げる'

    def test_empty_objective_text_raises(self) -> None:
        """空/空白のみの目的文は呼び出し側の不変条件違反として ValueError。"""
        with pytest.raises(ValueError):
            build_goal_stagnation_cue_signature('   ')


class TestJapaneseActorReachesPlayerAxis:
    """日本語名の相手が chunk episode の who を経て cue_signature の player: 軸に届く。"""

    def test_japanese_actor_observation_adds_player_axis(self) -> None:
        """actor 'ノア' の観測を含む chunk episode の cue_signature は 'player:entity:actor:ノア' を含む。"""
        t = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(occurred_at=t, output=ObservationOutput(prose='ノアが近づいた。', structured={'actor': 'ノア'}, observation_category='social'))
        act = ActionResultEntry(occurred_at=t + timedelta(minutes=1), action_summary='話しかけた', result_summary='返事があった。', tool_name='speak')
        episode = ChunkEpisodeDraftBuilder().build(build_chunk_encoding_input(PlayerId(1), (obs,), (act,)), being_id=BeingId('being_w1_p1'))

        assert build_belief_evidence_cue_signature(episode) == 'tool:speak|player:entity:actor:ノア'
