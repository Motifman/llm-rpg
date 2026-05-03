"""エピソード用チャンク境界のルール（純粋判定・リポジトリ・バッファ非依存）。"""

from ai_rpg_world.application.llm.chunk_boundary.rules import (
    OBSERVATION_COUNT_CLOSE_THRESHOLD,
    ChunkBoundaryDecision,
    ChunkBoundaryReason,
    MIN_ACTION_RESULTS_FOR_EPISODE,
    ObservationBoundaryHints,
    decide_chunk_boundary,
    summarize_observation_boundary_hints,
)

__all__ = [
    "MIN_ACTION_RESULTS_FOR_EPISODE",
    "OBSERVATION_COUNT_CLOSE_THRESHOLD",
    "ChunkBoundaryDecision",
    "ChunkBoundaryReason",
    "ObservationBoundaryHints",
    "decide_chunk_boundary",
    "summarize_observation_boundary_hints",
]
