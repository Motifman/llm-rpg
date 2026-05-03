"""decide_chunk_boundary / summarize_observation_boundary_hints のテスト"""

from datetime import datetime

import pytest

from ai_rpg_world.application.llm.chunk_boundary.rules import (
    OBSERVATION_COUNT_CLOSE_THRESHOLD,
    ChunkBoundaryDecision,
    ChunkBoundaryReason,
    ObservationBoundaryHints,
    decide_chunk_boundary,
    summarize_observation_boundary_hints,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    build_chunk_encoding_input,
    chunk_encoding_episode_generation_allowed,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_obs(  # noqa: PLR0913 — テスト用ファクトリ
    *,
    prose: str = "x",
    structured: dict | None = None,
    category: str = "self_only",
    schedules_turn: bool = False,
    breaks_movement: bool = False,
    at: datetime | None = None,
) -> ObservationEntry:
    ts = at or datetime(2026, 5, 4, 12, 0, 0)
    return ObservationEntry(
        occurred_at=ts,
        output=ObservationOutput(
            prose=prose,
            structured=structured if structured is not None else {"type": "t"},
            observation_category=category,  # type: ignore[arg-type]
            schedules_turn=schedules_turn,
            breaks_movement=breaks_movement,
        ),
    )


def _action(at: datetime | None = None) -> ActionResultEntry:
    ts = at or datetime(2026, 5, 4, 12, 1, 0)
    return ActionResultEntry(
        occurred_at=ts,
        action_summary="act",
        result_summary="ok",
    )


class TestSummarizeObservationBoundaryHints:
    """summarize_observation_boundary_hints が観測列からヒントを組み立てること"""

    def test_empty_observations_all_false_counts_zero(self):
        """観測が空のとき件数0・各フラグは偽"""
        h = summarize_observation_boundary_hints(())
        assert h.observation_count == 0
        assert h.any_breaks_movement is False
        assert h.any_schedules_turn is False
        assert h.has_category_transition is False
        assert h.has_structured_keys_change is False

    def test_single_observation_salient_flags(self):
        """1件でも breaks_movement / schedules_turn を拾う"""
        o = _make_obs(breaks_movement=True, schedules_turn=True)
        h = summarize_observation_boundary_hints([o])
        assert h.observation_count == 1
        assert h.any_breaks_movement is True
        assert h.any_schedules_turn is True

    def test_category_transition_between_two(self):
        """連続観測で observation_category が変われば遷移"""
        a = _make_obs(structured={"a": 1}, category="self_only", at=datetime(2026, 5, 4, 12, 0, 0))
        b = _make_obs(structured={"a": 1}, category="social", at=datetime(2026, 5, 4, 12, 0, 1))
        h = summarize_observation_boundary_hints([a, b])
        assert h.has_category_transition is True

    def test_tuple_order_irrelevant_category_follows_occurred_at(self):
        """並びが時系列と逆でも occurred_at 昇順で遷移を検知する"""
        later_first_in_tuple = _make_obs(
            category="social", at=datetime(2026, 5, 4, 12, 0, 2)
        )
        earlier_second_in_tuple = _make_obs(
            category="self_only", at=datetime(2026, 5, 4, 12, 0, 1)
        )
        h = summarize_observation_boundary_hints([later_first_in_tuple, earlier_second_in_tuple])
        assert h.has_category_transition is True

    def test_same_structured_keys_different_values_no_key_change(self):
        """キー集合が同じなら structured 変化とみなさない"""
        a = _make_obs(structured={"a": 1}, at=datetime(2026, 5, 4, 12, 0, 0))
        b = _make_obs(structured={"a": 99}, at=datetime(2026, 5, 4, 12, 0, 1))
        h = summarize_observation_boundary_hints([a, b])
        assert h.has_structured_keys_change is False

    def test_structured_keys_change_between_two(self):
        """連続観測（時系列順）で structured のキー集合が変われば真"""
        a = _make_obs(structured={"type": "a"}, at=datetime(2026, 5, 4, 12, 0, 0))
        b = _make_obs(structured={"kind": "b"}, at=datetime(2026, 5, 4, 12, 0, 1))
        h = summarize_observation_boundary_hints([a, b])
        assert h.has_structured_keys_change is True

    def test_non_observation_raises(self):
        """ObservationEntry 以外は TypeError"""
        with pytest.raises(TypeError, match="must be ObservationEntry"):
            summarize_observation_boundary_hints(["bad"])  # type: ignore[list-item]


class TestDecideChunkBoundary:
    """decide_chunk_boundary のゲート・優先順位・HOLD"""

    def test_no_action_insufficient(self):
        """行動結果0件は生成不可・閉じない"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [_make_obs()], [])
        d = decide_chunk_boundary(inp, explicit_segment_close=True)
        assert d == ChunkBoundaryDecision(
            should_close_chunk=False,
            episode_generation_allowed_if_closed=False,
            reason=ChunkBoundaryReason.INSUFFICIENT_ACTIONS,
        )

    def test_chunk_encoding_gate_zero_actions(self):
        """第1版のエンコード可否は chunk_encoding のゲートに委譲（0件は不可）"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [], [])
        assert chunk_encoding_episode_generation_allowed(inp) is False

    def test_explicit_close_wins_over_hints(self):
        """行動あり・明示区切りなら SEGMENT_EXPLICIT（観測なしでも可）"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [], [_action()])
        d = decide_chunk_boundary(inp, explicit_segment_close=True)
        assert d.should_close_chunk is True
        assert d.episode_generation_allowed_if_closed is True
        assert d.reason is ChunkBoundaryReason.SEGMENT_EXPLICIT

    def test_observation_count_threshold(self):
        """観測件数が閾値以上なら OBSERVATION_COUNT_THRESHOLD"""
        assert OBSERVATION_COUNT_CLOSE_THRESHOLD == 3
        pid = PlayerId(1)
        obs = [_make_obs(prose="1", at=datetime(2026, 5, 4, 12, 0, i)) for i in range(3)]
        inp = build_chunk_encoding_input(pid, obs, [_action(at=datetime(2026, 5, 4, 13, 0, 0))])
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.OBSERVATION_COUNT_THRESHOLD
        assert d.should_close_chunk is True

    def test_observation_count_below_threshold_holds(self):
        """観測が閾値未満で他ヒントがなければ HOLD（閾値=3）"""
        assert OBSERVATION_COUNT_CLOSE_THRESHOLD == 3
        pid = PlayerId(1)
        obs = [_make_obs(at=datetime(2026, 5, 4, 12, 0, i)) for i in range(2)]
        inp = build_chunk_encoding_input(pid, obs, [_action()])
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.HOLD_ACCUMULATING
        assert d.should_close_chunk is False

    def test_salient_observation_before_category_in_priority(self):
        """salient 観測はカテゴリ遷移より先に評価される（理由が SALIENT になる）"""
        pid = PlayerId(1)
        obs = [
            _make_obs(category="self_only", breaks_movement=True, at=datetime(2026, 5, 4, 12, 0, 0)),
            _make_obs(category="social", at=datetime(2026, 5, 4, 12, 0, 1)),
        ]
        inp = build_chunk_encoding_input(pid, obs, [_action()])
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.OBSERVATION_SALIENT

    def test_category_shift_when_not_salient(self):
        """salient なし・件数不足でもカテゴリ遷移で閉じる"""
        pid = PlayerId(1)
        obs = [
            _make_obs(category="self_only", at=datetime(2026, 5, 4, 12, 0, 0)),
            _make_obs(category="environment", at=datetime(2026, 5, 4, 12, 0, 1)),
        ]
        inp = build_chunk_encoding_input(pid, obs, [_action()])
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.CATEGORY_SHIFT

    def test_structured_keys_change_only(self):
        """カテゴリは同一で structured キーだけ変わる場合 STRUCTURED_KEYS_CHANGED"""
        pid = PlayerId(1)
        obs = [
            _make_obs(structured={"a": 1}, at=datetime(2026, 5, 4, 12, 0, 0)),
            _make_obs(structured={"b": 1}, at=datetime(2026, 5, 4, 12, 0, 1)),
        ]
        inp = build_chunk_encoding_input(pid, obs, [_action()])
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.STRUCTURED_KEYS_CHANGED

    def test_hold_when_has_action_but_no_close_signal(self):
        """行動はあるが明示も観測ヒントも閉じない → HOLD"""
        pid = PlayerId(1)
        obs = [_make_obs(at=datetime(2026, 5, 4, 12, 0, 0))]
        inp = build_chunk_encoding_input(pid, obs, [_action()])
        d = decide_chunk_boundary(inp, explicit_segment_close=False)
        assert d.should_close_chunk is False
        assert d.episode_generation_allowed_if_closed is True
        assert d.reason is ChunkBoundaryReason.HOLD_ACCUMULATING

    def test_custom_hints_override_derived(self):
        """hints を渡すと ChunkEncodingInput.observations ではなくそのヒントで判定"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [_make_obs()], [_action()])
        custom = ObservationBoundaryHints(
            observation_count=0,
            any_breaks_movement=False,
            any_schedules_turn=False,
            has_category_transition=False,
            has_structured_keys_change=False,
        )
        d = decide_chunk_boundary(inp, hints=custom)
        assert d.reason is ChunkBoundaryReason.HOLD_ACCUMULATING

    def test_explicit_segment_close_type_error(self):
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [], [_action()])
        with pytest.raises(TypeError, match="explicit_segment_close"):
            decide_chunk_boundary(inp, explicit_segment_close="yes")  # type: ignore[arg-type]

    def test_invalid_chunk_encoding_input_type(self):
        with pytest.raises(TypeError, match="ChunkEncodingInput"):
            decide_chunk_boundary("nope")  # type: ignore[arg-type]

    def test_hints_wrong_type(self):
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [], [_action()])
        with pytest.raises(TypeError, match="ObservationBoundaryHints"):
            decide_chunk_boundary(inp, hints="x")  # type: ignore[arg-type]
