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

# 第1版の固定閾値（テストが同一定数を参照して期待値を固定する）
OBSERVATION_COUNT_CLOSE_THRESHOLD = 3


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
) -> ChunkBoundaryDecision:
    """
    チャンクを閉じてエピソード生成へ進むべきかを返す。

    - `chunk_encoding_episode_generation_allowed` が偽なら（第 1 版: 行動ゼロ等）生成不可かつ閉じない。
    - 生成可能なとき、`explicit_segment_close` が最優先で閉じる（協調層からの区切り信号）。
    - それ以外は観測ヒントが閾値・顕在性・カテゴリ遷移・structured キー変化のいずれかで閉じる。
    - ヒントが発火せず明示もない場合は HOLD（材料は蓄積継続）。
    """
    if not isinstance(inp, ChunkEncodingInput):
        raise TypeError("inp must be ChunkEncodingInput")
    if hints is not None and not isinstance(hints, ObservationBoundaryHints):
        raise TypeError("hints must be ObservationBoundaryHints or None")
    if not isinstance(explicit_segment_close, bool):
        raise TypeError("explicit_segment_close must be bool")

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

    if hints_eff.observation_count >= OBSERVATION_COUNT_CLOSE_THRESHOLD:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.OBSERVATION_COUNT_THRESHOLD,
        )

    if hints_eff.any_breaks_movement or hints_eff.any_schedules_turn:
        return ChunkBoundaryDecision(
            should_close_chunk=True,
            episode_generation_allowed_if_closed=True,
            reason=ChunkBoundaryReason.OBSERVATION_SALIENT,
        )

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

    return ChunkBoundaryDecision(
        should_close_chunk=False,
        episode_generation_allowed_if_closed=True,
        reason=ChunkBoundaryReason.HOLD_ACCUMULATING,
    )
