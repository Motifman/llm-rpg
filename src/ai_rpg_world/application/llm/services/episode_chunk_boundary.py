"""
チャンク境界判定（エピソード生成をいつ起動するか）。

入力は同期済みタイムラインを保持する ChunkEncodingInput と、オプションで観測 drain などのヒント。
ドメイン層にはリポジトリ・バッファを置かず、協調オブジェクトがヒントを組み立てて本関数へ渡す。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Any, FrozenSet, Mapping

from ai_rpg_world.application.llm.contracts.chunk_encoding import ChunkEncodingInput
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    chunk_encoding_episode_generation_allowed,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


class EpisodeChunkBoundaryDecision(Enum):
    """チャンクを閉じてエピソードエンコードへ進むか。"""

    DEFER = "defer"
    CLOSE_FOR_EPISODE_ENCODING = "close_for_episode_encoding"


@dataclass(frozen=True)
class ChunkBoundaryObservationHints:
    """
    観測バッファ drain 直後など、アプリケーション層が付与する境界ヒント。
    件数しきい値は policy と組み合わせて解釈する。
    """

    drained_observation_entry_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.drained_observation_entry_count, int):
            raise TypeError("drained_observation_entry_count must be int")
        if self.drained_observation_entry_count < 0:
            raise ValueError("drained_observation_entry_count must be >= 0")


@dataclass(frozen=True)
class EpisodeChunkBoundaryPolicy:
    """テストで固定しやすいしきい値・フラグ（第 1 版）。"""

    drained_observations_close_threshold: int = 10**9
    max_observations_in_chunk_before_close: int = 10**9
    close_on_observation_category_shift: bool = True
    close_on_structured_keys_shift: bool = True
    close_when_allowed_without_observation_boundary_signal: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.drained_observations_close_threshold, int):
            raise TypeError("drained_observations_close_threshold must be int")
        if self.drained_observations_close_threshold < 0:
            raise ValueError("drained_observations_close_threshold must be >= 0")
        if not isinstance(self.max_observations_in_chunk_before_close, int):
            raise TypeError("max_observations_in_chunk_before_close must be int")
        if self.max_observations_in_chunk_before_close < 0:
            raise ValueError("max_observations_in_chunk_before_close must be >= 0")
        if not isinstance(self.close_when_allowed_without_observation_boundary_signal, bool):
            raise TypeError("close_when_allowed_without_observation_boundary_signal must be bool")


@dataclass(frozen=True)
class EpisodeChunkBoundaryVerdict:
    decision: EpisodeChunkBoundaryDecision
    reason_code: str
    interval_end_occurred_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, str):
            raise TypeError("reason_code must be str")
        if self.interval_end_occurred_at is not None and not isinstance(
            self.interval_end_occurred_at, datetime
        ):
            raise TypeError("interval_end_occurred_at must be datetime or None")


def _structured_keys(o: Mapping[str, Any]) -> FrozenSet[str]:
    return frozenset(o.keys())


def _observation_category_shift(observations: tuple[ObservationEntry, ...]) -> bool:
    if len(observations) < 2:
        return False
    return observations[0].output.observation_category != observations[-1].output.observation_category


def _observation_structured_keys_shift(observations: tuple[ObservationEntry, ...]) -> bool:
    if len(observations) < 2:
        return False
    prev_keys = _structured_keys(observations[0].output.structured)
    for o in observations[1:]:
        if _structured_keys(o.output.structured) != prev_keys:
            return True
        prev_keys = _structured_keys(o.output.structured)
    return False


def decide_episode_chunk_boundary(
    inp: ChunkEncodingInput,
    *,
    observation_hints: ChunkBoundaryObservationHints | None = None,
    policy: EpisodeChunkBoundaryPolicy | None = None,
) -> EpisodeChunkBoundaryVerdict:
    """
    チャンクを閉じてエピソード生成を起動してよいか判定する。

    第 1 版: 区間に ActionResultEntry が 1 件も無ければ必ず DEFER。
    観測は件数・カテゴリ・structured キー集合の変化・drain ヒントで境界を補強する。
    行動のみのチャンクはシグナル不要で CLOSE。
    観測が載っているときは、カテゴリ変化・structured キー変化・件数上限・drain ヒントで CLOSE。
    policy.close_when_allowed_without_observation_boundary_signal が True（既定）なら、
    上記いずれにも当たらなくてもエピソード起動可なら CLOSE（理由コードは chunk_ready_default）。
    False のときは観測ありかつシグナルなしの場合のみ DEFER（ヒント検証用）。
    """
    if not isinstance(inp, ChunkEncodingInput):
        raise TypeError("inp must be ChunkEncodingInput")
    pol = policy or EpisodeChunkBoundaryPolicy()
    hints = observation_hints or ChunkBoundaryObservationHints()

    if not chunk_encoding_episode_generation_allowed(inp):
        return EpisodeChunkBoundaryVerdict(
            decision=EpisodeChunkBoundaryDecision.DEFER,
            reason_code="no_action_in_interval",
            interval_end_occurred_at=None,
        )

    obs = inp.observations

    if hints.drained_observation_entry_count >= pol.drained_observations_close_threshold:
        return _close_verdict(inp, "drain_hint_threshold")

    if len(obs) >= pol.max_observations_in_chunk_before_close:
        return _close_verdict(inp, "observation_count_cap")

    if pol.close_on_observation_category_shift and _observation_category_shift(obs):
        return _close_verdict(inp, "observation_category_shift")

    if pol.close_on_structured_keys_shift and _observation_structured_keys_shift(obs):
        return _close_verdict(inp, "structured_keys_shift")

    if len(obs) == 0:
        return _close_verdict(inp, "action_only_chunk")

    if pol.close_when_allowed_without_observation_boundary_signal:
        return _close_verdict(inp, "chunk_ready_default")

    return EpisodeChunkBoundaryVerdict(
        decision=EpisodeChunkBoundaryDecision.DEFER,
        reason_code="no_boundary_signal_with_observations",
        interval_end_occurred_at=None,
    )


def _close_verdict(inp: ChunkEncodingInput, reason_code: str) -> EpisodeChunkBoundaryVerdict:
    if not inp.unified_timeline:
        raise ValueError("close verdict requires non-empty unified_timeline")
    end_at = inp.unified_timeline[-1].occurred_at
    return EpisodeChunkBoundaryVerdict(
        decision=EpisodeChunkBoundaryDecision.CLOSE_FOR_EPISODE_ENCODING,
        reason_code=reason_code,
        interval_end_occurred_at=end_at,
    )
