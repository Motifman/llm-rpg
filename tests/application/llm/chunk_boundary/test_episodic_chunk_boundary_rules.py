"""decide_chunk_boundary / summarize_observation_boundary_hints のテスト

Issue #311 後続 (PR #322): cognitive science (Event Segmentation Theory +
working memory) に合わせた境界条件に改修されたため、テストもそれに合わせて
書き換える。主な変更点:

- ``MIN_ACTIONS_FOR_CLOSE = 3``: 単発 action は HOLD
- ``MAX_ACTIONS_FOR_CLOSE = 7``: working memory 上限で強制クローズ
- ``TEMPORAL_GAP_TICKS_FOR_CLOSE = 8``: bucket actions の tick 差が広いと閉じる
- ``OBSERVATION_COUNT_CLOSE_THRESHOLD``: 3 → 5
- ``schedules_turn`` を salient 判定から除外 (LLM ターン投入は scene 境界とは別概念)
- ``scene_boundary=True`` の action があれば閉じる (doorway effect)
"""

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.chunk_boundary.rules import (
    MAX_ACTIONS_FOR_CLOSE,
    MIN_ACTIONS_FOR_CLOSE,
    OBSERVATION_COUNT_CLOSE_THRESHOLD,
    TEMPORAL_GAP_TICKS_FOR_CLOSE,
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


def _make_obs(  # noqa: PLR0913
    *,
    prose: str = "x",
    structured: dict | None = None,
    category: str = "self_only",
    schedules_turn: bool = False,
    breaks_movement: bool = False,
    at: datetime | None = None,
) -> ObservationEntry:
    ts = at or datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
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


def _action(
    at: datetime | None = None,
    *,
    scene_boundary: bool = False,
    occurred_tick: int | None = None,
) -> ActionResultEntry:
    ts = at or datetime(2026, 5, 4, 12, 1, 0, tzinfo=timezone.utc)
    return ActionResultEntry(
        occurred_at=ts,
        action_summary="act",
        result_summary="ok",
        scene_boundary=scene_boundary,
        occurred_tick=occurred_tick,
    )


def _bucket(n: int, *, start_tick: int = 0) -> list[ActionResultEntry]:
    """既定 tick 0,1,2,... の bucket actions を ``n`` 件作る。"""
    return [
        _action(
            at=datetime(2026, 5, 4, 12, 1, i, tzinfo=timezone.utc),
            occurred_tick=start_tick + i,
        )
        for i in range(n)
    ]


class TestSummarizeObservationBoundaryHints:
    """summarize_observation_boundary_hints が観測列からヒントを組み立てること。

    本サマリ自体は change しておらず、``decide_chunk_boundary`` 側で
    schedules_turn を salient から除外する。
    """

    def test_empty_observations_all_false_counts_zero(self):
        h = summarize_observation_boundary_hints(())
        assert h.observation_count == 0
        assert h.any_breaks_movement is False
        assert h.any_schedules_turn is False
        assert h.has_category_transition is False
        assert h.has_structured_keys_change is False

    def test_single_observation_salient_flags(self):
        o = _make_obs(breaks_movement=True, schedules_turn=True)
        h = summarize_observation_boundary_hints([o])
        assert h.observation_count == 1
        assert h.any_breaks_movement is True
        assert h.any_schedules_turn is True

    def test_category_transition_between_two(self):
        a = _make_obs(structured={"a": 1}, category="self_only", at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
        b = _make_obs(structured={"a": 1}, category="social", at=datetime(2026, 5, 4, 12, 0, 1, tzinfo=timezone.utc))
        h = summarize_observation_boundary_hints([a, b])
        assert h.has_category_transition is True

    def test_structured_keys_change_between_two(self):
        a = _make_obs(structured={"type": "a"}, at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
        b = _make_obs(structured={"kind": "b"}, at=datetime(2026, 5, 4, 12, 0, 1, tzinfo=timezone.utc))
        h = summarize_observation_boundary_hints([a, b])
        assert h.has_structured_keys_change is True

    def test_non_observation_raises(self):
        with pytest.raises(TypeError, match="must be ObservationEntry"):
            summarize_observation_boundary_hints(["bad"])  # type: ignore[list-item]


class TestDecideChunkBoundary:
    """``decide_chunk_boundary`` の優先順位 (Issue #311 後続の認知原則ベース)。"""

    def test_no_action_insufficient(self):
        """行動結果 0 件は生成不可・閉じない。"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [_make_obs()], [])
        d = decide_chunk_boundary(inp, explicit_segment_close=True)
        assert d == ChunkBoundaryDecision(
            should_close_chunk=False,
            episode_generation_allowed_if_closed=False,
            reason=ChunkBoundaryReason.INSUFFICIENT_ACTIONS,
        )

    def test_chunk_encoding_gate_zero_actions(self):
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [], [])
        assert chunk_encoding_episode_generation_allowed(inp) is False

    def test_explicit_close_wins_over_min_threshold(self):
        """``explicit_segment_close=True`` は min_actions 未達でも最優先で閉じる。"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [], [_action()])
        d = decide_chunk_boundary(inp, explicit_segment_close=True)
        assert d.should_close_chunk is True
        assert d.reason is ChunkBoundaryReason.SEGMENT_EXPLICIT

    # ── 強制クローズ (cognitive limit / temporal gap) ──

    def test_max_actions_reached_forces_close(self):
        """``MAX_ACTIONS_FOR_CLOSE`` 件以上で強制クローズ (working memory 上限)。"""
        assert MAX_ACTIONS_FOR_CLOSE == 7
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(
            pid, [], _bucket(MAX_ACTIONS_FOR_CLOSE)
        )
        d = decide_chunk_boundary(inp)
        assert d.should_close_chunk is True
        assert d.reason is ChunkBoundaryReason.MAX_ACTIONS_REACHED

    def test_temporal_gap_forces_close(self):
        """bucket の tick 差が ``TEMPORAL_GAP_TICKS_FOR_CLOSE`` 以上で閉じる。"""
        assert TEMPORAL_GAP_TICKS_FOR_CLOSE == 8
        pid = PlayerId(1)
        actions = [
            _action(occurred_tick=0),
            _action(occurred_tick=TEMPORAL_GAP_TICKS_FOR_CLOSE),
        ]
        inp = build_chunk_encoding_input(pid, [], actions)
        d = decide_chunk_boundary(inp)
        assert d.should_close_chunk is True
        assert d.reason is ChunkBoundaryReason.TEMPORAL_GAP

    def test_no_temporal_gap_when_ticks_unknown(self):
        """``occurred_tick=None`` の action だけだと temporal_gap は発火しない。"""
        pid = PlayerId(1)
        actions = [_action(occurred_tick=None) for _ in range(3)]
        inp = build_chunk_encoding_input(pid, [], actions)
        # 3 件 + salient なし → MIN は満たすが scene 境界系もなく HOLD
        d = decide_chunk_boundary(inp)
        # MAX 未達 (3 < 7)、TEMPORAL_GAP は tick 不明で 0 → HOLD
        assert d.reason is ChunkBoundaryReason.HOLD_ACCUMULATING

    # ── MIN gate ──

    def test_single_action_holds_due_to_min_threshold(self):
        """``MIN_ACTIONS_FOR_CLOSE`` 未満は HOLD。"""
        assert MIN_ACTIONS_FOR_CLOSE == 3
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [_make_obs(breaks_movement=True)], [_action()])
        d = decide_chunk_boundary(inp)
        assert d.should_close_chunk is False
        assert d.reason is ChunkBoundaryReason.MIN_ACTIONS_NOT_MET

    def test_two_actions_below_min_holds_even_with_salient(self):
        """2 件 action は salient 観測があっても HOLD (= 単発 episode 防止)。"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(
            pid,
            [_make_obs(breaks_movement=True)],
            _bucket(2),
        )
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.MIN_ACTIONS_NOT_MET

    # ── scene 境界 ──

    def test_scene_boundary_action_closes_when_min_met(self):
        """``scene_boundary=True`` の action があり MIN を満たすなら閉じる。"""
        pid = PlayerId(1)
        actions = [
            _action(occurred_tick=0),
            _action(occurred_tick=1),
            _action(occurred_tick=2, scene_boundary=True),
        ]
        inp = build_chunk_encoding_input(pid, [], actions)
        d = decide_chunk_boundary(inp)
        assert d.should_close_chunk is True
        assert d.reason is ChunkBoundaryReason.SCENE_BOUNDARY_ACTION

    def test_scene_boundary_action_does_not_close_below_min(self):
        """``scene_boundary=True`` でも MIN 未達なら HOLD (単発 spot 遷移を 1 episode に
        まとめない)。"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(
            pid,
            [],
            [_action(scene_boundary=True), _action(scene_boundary=False)],
        )
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.MIN_ACTIONS_NOT_MET

    # ── 観測ベースの境界 (MIN を満たした後) ──

    def test_breaks_movement_closes_above_min(self):
        """``breaks_movement`` 観測で OBSERVATION_SALIENT 経由クローズ。"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(
            pid,
            [_make_obs(breaks_movement=True)],
            _bucket(MIN_ACTIONS_FOR_CLOSE),
        )
        d = decide_chunk_boundary(inp)
        assert d.should_close_chunk is True
        assert d.reason is ChunkBoundaryReason.OBSERVATION_SALIENT

    def test_schedules_turn_alone_does_not_close(self):
        """``schedules_turn`` のみでは閉じない (cognitive 境界とは別概念)。

        これが第21回実験で chunk が 2-3 action ごとに発火していた原因。
        """
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(
            pid,
            [_make_obs(schedules_turn=True)],
            _bucket(MIN_ACTIONS_FOR_CLOSE),
        )
        d = decide_chunk_boundary(inp)
        # OBSERVATION_SALIENT は発火せず、obs 件数 1 件で件数閾値も未達 → HOLD
        assert d.should_close_chunk is False
        assert d.reason is ChunkBoundaryReason.HOLD_ACCUMULATING

    def test_observation_count_threshold(self):
        """観測件数 ``OBSERVATION_COUNT_CLOSE_THRESHOLD`` 以上で閉じる。"""
        assert OBSERVATION_COUNT_CLOSE_THRESHOLD == 5
        pid = PlayerId(1)
        obs = [
            _make_obs(prose="o", at=datetime(2026, 5, 4, 12, 0, i, tzinfo=timezone.utc))
            for i in range(OBSERVATION_COUNT_CLOSE_THRESHOLD)
        ]
        inp = build_chunk_encoding_input(pid, obs, _bucket(MIN_ACTIONS_FOR_CLOSE))
        d = decide_chunk_boundary(inp)
        assert d.should_close_chunk is True
        assert d.reason is ChunkBoundaryReason.OBSERVATION_COUNT_THRESHOLD

    def test_observation_count_below_threshold_holds(self):
        pid = PlayerId(1)
        obs = [
            _make_obs(at=datetime(2026, 5, 4, 12, 0, i, tzinfo=timezone.utc))
            for i in range(OBSERVATION_COUNT_CLOSE_THRESHOLD - 1)
        ]
        inp = build_chunk_encoding_input(pid, obs, _bucket(MIN_ACTIONS_FOR_CLOSE))
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.HOLD_ACCUMULATING

    def test_category_shift_closes(self):
        pid = PlayerId(1)
        obs = [
            _make_obs(category="self_only", at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)),
            _make_obs(category="environment", at=datetime(2026, 5, 4, 12, 0, 1, tzinfo=timezone.utc)),
        ]
        inp = build_chunk_encoding_input(pid, obs, _bucket(MIN_ACTIONS_FOR_CLOSE))
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.CATEGORY_SHIFT

    def test_structured_keys_change_closes(self):
        pid = PlayerId(1)
        obs = [
            _make_obs(structured={"a": 1}, at=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)),
            _make_obs(structured={"b": 1}, at=datetime(2026, 5, 4, 12, 0, 1, tzinfo=timezone.utc)),
        ]
        inp = build_chunk_encoding_input(pid, obs, _bucket(MIN_ACTIONS_FOR_CLOSE))
        d = decide_chunk_boundary(inp)
        assert d.reason is ChunkBoundaryReason.STRUCTURED_KEYS_CHANGED

    # ── HOLD ──

    def test_hold_when_min_met_but_no_close_signal(self):
        """MIN 満たすが scene 境界系も件数も発火しなければ HOLD。"""
        pid = PlayerId(1)
        obs = [_make_obs()]  # 1 件、salient なし
        inp = build_chunk_encoding_input(pid, obs, _bucket(MIN_ACTIONS_FOR_CLOSE))
        d = decide_chunk_boundary(inp)
        assert d.should_close_chunk is False
        assert d.reason is ChunkBoundaryReason.HOLD_ACCUMULATING

    def test_custom_hints_override_derived(self):
        """``hints`` を渡すと observations ではなくそのヒントで判定。"""
        pid = PlayerId(1)
        inp = build_chunk_encoding_input(pid, [_make_obs()], _bucket(MIN_ACTIONS_FOR_CLOSE))
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
