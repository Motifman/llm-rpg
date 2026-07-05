"""U7 (予測誤差統一設計 / 無意識コンテキスト): chunk 主観補完 LLM に渡す
「いまの自分 (信念と自己像)」テキストを組み立てる provider の builder。

設計判断:

- **単一注入**: ``EpisodicChunkSubjectiveFieldsService`` に provider を 1 点だけ
  注入する (coordinator / 同期・非同期 2 scheduler の 3 点には配線しない)。
  ``merge_llm_subjective_fields`` は同期・非同期どちらの経路からも呼ばれる
  唯一のメソッドなので、そこで provider を呼べば両経路に自動で効く
- **belief 取得は既存の ``SemanticPassiveRecallService`` を再利用**: 新規 store
  は作らない。cue 一致の active belief top-K (``top_k`` 引数、既定 5 件) を
  確信度付きで整形する
- **L5 (self_image / world_view) は任意**: RollingSummary 使用時のみ
  ``long_summary_text_provider`` が非 None になる想定。sliding_window 実装
  (``DefaultSlidingWindowMemory``) には該当メソッドが無いので、呼び出し側は
  ``getattr(sliding_window, "get_long_summary_text", None)`` のように安全に
  解決してから渡す
- **失敗はすべて空文字に縮退**: belief 取得・L5 取得のどちらが失敗しても
  chunk 補完自体は止めない (無意識コンテキストは「あれば良い」side feature)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
    SemanticPassiveRecallService,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue

_logger = logging.getLogger(__name__)

# belief top-K の既定件数。docs/memory_system/prediction_error_unified_
# implementation_plan.md U7 節・prediction_error_unified_memory_design.md §4
# で合意した「5 件 cap」。
DEFAULT_UNCONSCIOUS_CONTEXT_BELIEF_TOP_K = 5


def build_unconscious_context_provider(
    *,
    semantic_recall_service_provider: Callable[
        [], Optional[SemanticPassiveRecallService]
    ],
    long_summary_text_provider: Optional[Callable[[int], str]] = None,
    top_k: int = DEFAULT_UNCONSCIOUS_CONTEXT_BELIEF_TOP_K,
    now_provider: Optional[Callable[[], datetime]] = None,
) -> Callable[[int, Sequence[EpisodicCue]], str]:
    """belief top-K (+ L5 自己像/世界観) を 1 本のテキストに束ねる provider を作る。

    Args:
        semantic_recall_service_provider: 呼び出し時点の ``SemanticPassiveRecallService``
            を返す thunk。``EpisodicChunkSubjectiveFieldsService`` の構築が
            semantic store の構築より先に走る wiring 上の制約があるため、
            即値ではなく遅延解決の thunk として受け取る (未構築なら None を返す)。
        long_summary_text_provider: player_id(int) → L5 整形済みテキストの
            provider。None、または呼び出し結果が空文字なら L5 行は省略する。
        top_k: belief 取得件数の上限。既定 5。
        now_provider: 想起スコアリングの基準時刻を返す thunk。None なら
            呼び出し時の ``datetime.now(timezone.utc)``。

    Returns:
        ``(player_id, cues) -> str`` の provider。例外は内部で握りつぶし、
        失敗時は空文字を返す (chunk 補完を止めないため)。
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    def _provider(player_id: int, cues: Sequence[EpisodicCue]) -> str:
        lines: list[str] = []

        service: Optional[SemanticPassiveRecallService] = None
        try:
            service = semantic_recall_service_provider()
        except Exception:
            _logger.warning(
                "semantic_recall_service_provider failed for player_id=%s",
                player_id,
                exc_info=True,
            )

        if service is not None:
            try:
                now = now_provider() if now_provider is not None else datetime.now(timezone.utc)
                candidates = service.retrieve(
                    player_id=player_id,
                    situation_cues=cues,
                    top_k=top_k,
                    now=now,
                )
                for candidate in candidates:
                    text = (candidate.entry.text or "").strip()
                    if not text:
                        continue
                    lines.append(f"- {text} (確信度: {candidate.entry.confidence:.2f})")
            except Exception:
                _logger.warning(
                    "unconscious context belief retrieval failed for player_id=%s",
                    player_id,
                    exc_info=True,
                )

        if long_summary_text_provider is not None:
            try:
                l5_text = long_summary_text_provider(player_id)
                if isinstance(l5_text, str) and l5_text.strip():
                    lines.append(l5_text.strip())
            except Exception:
                _logger.warning(
                    "unconscious context long summary retrieval failed for player_id=%s",
                    player_id,
                    exc_info=True,
                )

        return "\n".join(lines)

    return _provider


__all__ = [
    "DEFAULT_UNCONSCIOUS_CONTEXT_BELIEF_TOP_K",
    "build_unconscious_context_provider",
]
