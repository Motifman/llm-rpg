"""
チャンクを閉じてエピソード生成を起動するかの判定。

入力は同期済みの ChunkEncodingInput（unified_timeline の不変条件を満たすこと）と、
オプションで観測から集約した境界ヒント。協調層は観測バッファの drain 等を担い、
本モジュールはポートを持たない。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    ChunkEncodingInput,
    chunk_encoding_episode_generation_allowed,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


def _as_utc(value: datetime) -> datetime:
    """naive datetime を UTC aware として扱い、aware はそのまま返す。

    Issue #311 後続: 観測列の sort で aware/naive 混在による TypeError を
    防ぐ。``episodic_chunk_coordinator._as_utc`` と同じ意図のヘルパ
    (循環 import を避けるためここで重複定義する; どちらも純関数)。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

# Issue #311 後続: cognitive science (Event Segmentation Theory + working memory)
# に合わせた閾値群。
#
# - OBSERVATION_COUNT_CLOSE_THRESHOLD: 3 → 5 に引き上げ。3 件は micro-event 級、
#   5-8 件が scene-level の自然な区切りに近い (Zacks の naturalistic 研究)。
# - MIN_ACTIONS_FOR_CLOSE: working memory 容量 (4±1) の下限。これ以下の action
#   数では 1 つの episode として括る価値が薄い (= 単発 action は HOLD)。
# - MAX_ACTIONS_FOR_CLOSE: working memory 容量 (7±2) の上限。これを超えて
#   bucket が膨らんだら scene 境界が来ていなくても強制クローズして 1 chunk に
#   閉じ込める (recall 効率の確保)。
# - TEMPORAL_GAP_TICKS_FOR_CLOSE: bucket 内 actions の最古/最新の tick 差が
#   これ以上開いたら時間的に分断された scene とみなす。
OBSERVATION_COUNT_CLOSE_THRESHOLD = 5
MIN_ACTIONS_FOR_CLOSE = 3
MAX_ACTIONS_FOR_CLOSE = 7
TEMPORAL_GAP_TICKS_FOR_CLOSE = 8


@dataclass(frozen=True)
class ObservationBoundaryHints:
    """区間内観測から得た境界ヒント（件数・顕在性・カテゴリ・structured の骨格変化）。"""

    observation_count: int
    any_breaks_movement: bool
    any_schedules_turn: bool
    has_category_transition: bool
    has_structured_keys_change: bool

    def __post_init__(self) -> None:
        if not isinstance(self.observation_count, int):
            raise TypeError("observation_count must be int")
        if self.observation_count < 0:
            raise ValueError("observation_count must be non-negative")
        for name in (
            "any_breaks_movement",
            "any_schedules_turn",
            "has_category_transition",
            "has_structured_keys_change",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")


def _structured_key_fingerprint(structured: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(structured.keys())


def summarize_observation_boundary_hints(
    observations: Sequence[ObservationEntry],
) -> ObservationBoundaryHints:
    """
    ObservationEntry の列から境界ヒントを決定論的に集約する。

    入力タプルの並びは不定でもよい。カテゴリ遷移・structured キー変化は
    `occurred_at` 昇順（同一時刻は元の相対順を安定ソートで保持）の隣接比較とする。
    """
    obs_list = list(observations)
    for i, o in enumerate(obs_list):
        if not isinstance(o, ObservationEntry):
            raise TypeError(f"observations[{i}] must be ObservationEntry")

    obs_list.sort(key=lambda e: _as_utc(e.occurred_at))

    n = len(obs_list)
    any_breaks = any(o.output.breaks_movement for o in obs_list)
    any_sched = any(o.output.schedules_turn for o in obs_list)

    cat_transition = False
    struct_change = False
    if n >= 2:
        for i in range(1, n):
            prev, cur = obs_list[i - 1], obs_list[i]
            if prev.output.observation_category != cur.output.observation_category:
                cat_transition = True
            if _structured_key_fingerprint(prev.output.structured) != _structured_key_fingerprint(
                cur.output.structured
            ):
                struct_change = True

    return ObservationBoundaryHints(
        observation_count=n,
        any_breaks_movement=any_breaks,
        any_schedules_turn=any_sched,
        has_category_transition=cat_transition,
        has_structured_keys_change=struct_change,
    )


class ChunkBoundaryReason(str, Enum):
    """閉じる／閉じないの理由（カーソル説明用）。"""

    # chunk_encoding_episode_generation_allowed と同義: 区間内 ActionResult が 0 件
    INSUFFICIENT_ACTIONS = "insufficient_actions"
    SEGMENT_EXPLICIT = "segment_explicit"
    OBSERVATION_COUNT_THRESHOLD = "observation_count_threshold"
    OBSERVATION_SALIENT = "observation_salient"
    CATEGORY_SHIFT = "category_shift"
    STRUCTURED_KEYS_CHANGED = "structured_keys_changed"
    # Issue #311 後続: cognitive science 由来の境界条件
    SCENE_BOUNDARY_ACTION = "scene_boundary_action"  # ActionResultEntry.scene_boundary=True (e.g. spot 遷移)
    TEMPORAL_GAP = "temporal_gap"                     # bucket 内 actions の tick 差が閾値超
    MAX_ACTIONS_REACHED = "max_actions_reached"       # working memory 上限 (= 強制クローズ)
    MIN_ACTIONS_NOT_MET = "min_actions_not_met"       # 単発 action は HOLD (HOLD 理由内訳)
    # U8 (予測誤差統一設計 部品2a): bucket 内に「成功を予測していたのに失敗」
    # または「error_code 付き失敗」があれば境界候補にする (誤差ゲート付き符号化)。
    # error_gated_boundary_enabled=True のときのみ評価される (default OFF)。
    PREDICTION_ERROR_SALIENT = "prediction_error_salient"
    HOLD_ACCUMULATING = "hold_accumulating"


@dataclass(frozen=True)
class ChunkBoundaryDecision:
    should_close_chunk: bool
    episode_generation_allowed_if_closed: bool
    reason: ChunkBoundaryReason

    def __post_init__(self) -> None:
        if not isinstance(self.should_close_chunk, bool):
            raise TypeError("should_close_chunk must be bool")
        if not isinstance(self.episode_generation_allowed_if_closed, bool):
            raise TypeError("episode_generation_allowed_if_closed must be bool")
        if not isinstance(self.reason, ChunkBoundaryReason):
            raise TypeError("reason must be ChunkBoundaryReason")


def decide_chunk_boundary(
    inp: ChunkEncodingInput,
    *,
    hints: ObservationBoundaryHints | None = None,
    explicit_segment_close: bool = False,
    error_gated_boundary_enabled: bool = False,
) -> ChunkBoundaryDecision:
    """
    チャンクを閉じてエピソード生成へ進むべきかを返す。

    判定順 (Issue #311 後続で cognitive science に合わせた構成):

    1. **エンコーディング不可** (action 0 件) → HOLD
    2. **明示シグナル** (``explicit_segment_close``) → 即クローズ
    3. **強制クローズ系** (cognitive limit / 時間断絶):
       - bucket actions が ``MAX_ACTIONS_FOR_CLOSE`` 件以上 (working memory 上限)
       - bucket actions の tick 差が ``TEMPORAL_GAP_TICKS_FOR_CLOSE`` 以上 (時間断絶)
    4. **MIN_ACTIONS_FOR_CLOSE 未満** → 強制 HOLD
       (単発 action は episode に値しない — micro-event を防ぐ)
    5. **scene 境界系** (event segmentation theory):
       - bucket 内 ``ActionResultEntry.scene_boundary=True`` (spot 遷移等)
       - observation の category_shift / structured_keys_change
       - ``breaks_movement`` 観測 (顕著な「進行を遮る」イベント — schedules_turn は
         過剰発火するため除外)
    5d. **誤差ゲート付き境界 (U8 部品2a、``error_gated_boundary_enabled=True`` のときのみ)**:
       bucket 内 action に「成功を予測していたのに失敗」(``expected_result`` が
       非空 かつ ``success=False``) または「error_code 付き失敗」があれば境界候補。
       この時点で n_actions は 4 で ``MIN_ACTIONS_FOR_CLOSE`` をクリア済み。
    6. **観測件数閾値** → クローズ (件数で scene 級到達と見なす)
    7. 何も該当なし → HOLD (材料は蓄積継続)
    """
    if not isinstance(inp, ChunkEncodingInput):
        raise TypeError("inp must be ChunkEncodingInput")
    if hints is not None and not isinstance(hints, ObservationBoundaryHints):
        raise TypeError("hints must be ObservationBoundaryHints or None")
    if not isinstance(explicit_segment_close, bool):
        raise TypeError("explicit_segment_close must be bool")
    if not isinstance(error_gated_boundary_enabled, bool):
        raise TypeError("error_gated_boundary_enabled must be bool")

    encoding_ok = chunk_encoding_episode_generation_allowed(inp)
    if not encoding_ok:
        return ChunkBoundaryDecision(
            should_close_chunk=False,
            episode_generation_allowed_if_closed=False,
            reason=ChunkBoundaryReason.INSUFFICIENT_ACTIONS,
        )

    hints_eff = hints if hints is not None else summarize_observation_boundary_hints(inp.observations)

    if explicit_segment_close:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.SEGMENT_EXPLICIT,
        )

    actions = inp.action_results
    n_actions = len(actions)

    # 3a. MAX 強制クローズ (working memory 上限の保護)
    if n_actions >= MAX_ACTIONS_FOR_CLOSE:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.MAX_ACTIONS_REACHED,
        )

    # 3b. 時間断絶 (long temporal gap)
    if n_actions >= 2:
        tick_span = _action_tick_span(actions)
        if tick_span >= TEMPORAL_GAP_TICKS_FOR_CLOSE:
            return ChunkBoundaryDecision(
                should_close_chunk=True,
                episode_generation_allowed_if_closed=True,
                reason=ChunkBoundaryReason.TEMPORAL_GAP,
            )

    # 4. MIN 未満は強制 HOLD (= 単発 action では閉じない)
    if n_actions < MIN_ACTIONS_FOR_CLOSE:
        return ChunkBoundaryDecision(
            should_close_chunk=False,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.MIN_ACTIONS_NOT_MET,
        )

    # 5a. scene 境界 action (spot 遷移成功 等の caller-flagged 境界)
    if any(a.scene_boundary for a in actions):
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.SCENE_BOUNDARY_ACTION,
        )

    # 5b. 観測ベースの scene 境界
    if hints_eff.has_category_transition:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.CATEGORY_SHIFT,
        )

    if hints_eff.has_structured_keys_change:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.STRUCTURED_KEYS_CHANGED,
        )

    # 5c. breaks_movement のみ "salient" として尊重。schedules_turn は LLM ターン
    # 投入トリガであり scene 境界とは別概念なので除外 (第21回実験 #311 で過剰発火を観測)
    if hints_eff.any_breaks_movement:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.OBSERVATION_SALIENT,
        )

    # 5d. 誤差ゲート付き境界 (U8 部品2a: 予測誤差が跳ねた所で場面を切る)
    if error_gated_boundary_enabled and _has_salient_prediction_error(actions):
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.PREDICTION_ERROR_SALIENT,
        )

    # 6. 観測件数閾値
    if hints_eff.observation_count >= OBSERVATION_COUNT_CLOSE_THRESHOLD:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.OBSERVATION_COUNT_THRESHOLD,
        )

    return ChunkBoundaryDecision(
        should_close_chunk=False,
        episode_generation_allowed_if_closed=True,
        reason=ChunkBoundaryReason.HOLD_ACCUMULATING,
    )


def _has_salient_prediction_error(actions: Sequence[Any]) -> bool:
    """U8 (予測誤差統一設計 部品2a): bucket 内 action に構造的な予測ミスがあるか。

    「成功を予測していたのに失敗」(``expected_result`` が非空文字列 かつ
    ``success=False``) または「error_code 付き失敗」(``error_code`` が非空文字列
    かつ ``success=False``) のいずれかに該当する action が 1 件でもあれば True。
    どちらの条件も ``success=False`` を前提とする (成功した action は対象外)。
    """
    for a in actions:
        if getattr(a, "success", True):
            continue
        expected_result = getattr(a, "expected_result", None)
        error_code = getattr(a, "error_code", None)
        if isinstance(expected_result, str) and expected_result.strip():
            return True
        if isinstance(error_code, str) and error_code.strip():
            return True
    return False


def _action_tick_span(actions: Sequence[Any]) -> int:
    """bucket actions の ``occurred_tick`` の最大-最小差を返す。

    tick が記録されていない (= None) action は除外し、残った tick が 2 件
    未満なら span = 0 (= 判定できない) とする。
    """
    ticks: list[int] = []
    for a in actions:
        t = getattr(a, "occurred_tick", None)
        if isinstance(t, int) and not isinstance(t, bool):
            ticks.append(t)
    if len(ticks) < 2:
        return 0
    return max(ticks) - min(ticks)
