"""``RollingSummaryShortTermMemory``: L1 raw + L4 mid summary 階層型短期記憶。

Phase 2 (#356 後続) で導入。``DefaultSlidingWindowMemory`` の代替として
``ISlidingWindowMemory`` を満たす別実装。

挙動概要:
- ``append`` / ``append_all`` で L1 raw queue (max 25) に積む
- L1 サイズが soft cap (15) を超えると **古い 15 件を取り出して L4 を生成**
  し、L1 を 15 件分縮める
- L4 は新しい順に 3 世代だけ保持し、それ以上は破棄
- LLM 生成失敗 / hard cap (25) 到達時は **template fallback** (raw 連結)
  で L4 を埋める (silent failure 防止: WARNING ログ)
- ``get_recent`` / ``get_mid_summary_text`` を実装し ``ISlidingWindowMemory``
  契約を満たす

詳細: docs/memory_system/short_term_memory_design.md §3。
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Optional, Sequence
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.interfaces import ISlidingWindowMemory
from ai_rpg_world.application.llm.contracts.short_term_memory import L4MidSummary
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
    ShortTermMemorySummaryService,
    _ParsedSummary,
    build_template_fallback_summary,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_logger = logging.getLogger(__name__)


# raw queue の閾値。docs §3 の (15, 25) を採用。
DEFAULT_L1_SOFT_CAP = 15
DEFAULT_L1_HARD_CAP = 25
DEFAULT_L4_KEEP_GENERATIONS = 3


# persona resolver は (player_id_int) -> (player_name, persona_block)
PersonaResolverFn = Callable[[int], "tuple[str, str]"]


class RollingSummaryShortTermMemory(ISlidingWindowMemory):
    """L1 raw + L4 mid summary 階層型の短期記憶 (Phase 2)。

    現状の生成タイミングは **inline / sync** (``submit`` した thread でそのまま
    LLM を呼ぶ)。LLM 呼び出しは 2-5s かかるため、async scheduler は Phase 2.1
    の後続改善 (本 module では未実装)。

    `summary_service=None` を渡すと **LLM 経路は disable** され、L1 が
    閾値 (soft cap 15) を超えても LLM での要約は走らない。ただし L1 が
    無限に増えないよう、**template fallback で L4 を生成する** (raw 連結)。
    完全に sliding window 等価ではない: L1 は固定容量で循環するが、L4 は
    fallback 内容で埋まる。

    テスト / オフライン経路 / LLM 未配線運用で使う。
    """

    def __init__(
        self,
        *,
        summary_service: Optional[ShortTermMemorySummaryService] = None,
        persona_resolver: Optional[PersonaResolverFn] = None,
        l1_soft_cap: int = DEFAULT_L1_SOFT_CAP,
        l1_hard_cap: int = DEFAULT_L1_HARD_CAP,
        l4_keep_generations: int = DEFAULT_L4_KEEP_GENERATIONS,
    ) -> None:
        if l1_soft_cap <= 0:
            raise ValueError("l1_soft_cap must be positive")
        if l1_hard_cap <= 0:
            raise ValueError("l1_hard_cap must be positive")
        if l1_hard_cap < l1_soft_cap:
            raise ValueError("l1_hard_cap must be >= l1_soft_cap")
        if l4_keep_generations <= 0:
            raise ValueError("l4_keep_generations must be positive")
        if summary_service is not None and not isinstance(
            summary_service, ShortTermMemorySummaryService
        ):
            raise TypeError(
                "summary_service must be ShortTermMemorySummaryService or None"
            )
        if persona_resolver is not None and not callable(persona_resolver):
            raise TypeError("persona_resolver must be callable or None")
        self._service = summary_service
        self._persona_resolver = persona_resolver
        self._soft_cap = l1_soft_cap
        self._hard_cap = l1_hard_cap
        self._keep_gen = l4_keep_generations
        self._raw: Dict[int, Deque[ObservationEntry]] = {}
        # L4 は新しい順に並べる (index 0 = 最新)
        self._mid: Dict[int, Deque[L4MidSummary]] = {}

    # ──────────────────────────────────────────────────────────
    # ISlidingWindowMemory contract
    # ──────────────────────────────────────────────────────────

    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        pid = int(player_id.value)
        self._ensure_player(pid)
        self._raw[pid].append(entry)
        self._maybe_trigger_summary(pid)

    def append_all(
        self, player_id: PlayerId, entries: List[ObservationEntry]
    ) -> List[ObservationEntry]:
        """observations を順に append する。

        ``DefaultSlidingWindowMemory`` と違って evict は無い (代わりに L4 に
        畳む)。本 implementation では戻り値は常に空 list (overflow 0)。
        """
        for e in entries:
            self.append(player_id, e)
        return []

    def get_recent(
        self, player_id: PlayerId, limit: int
    ) -> List[ObservationEntry]:
        pid = int(player_id.value)
        if limit <= 0 or pid not in self._raw:
            return []
        raw = self._raw[pid]
        # 新しい順で返す (sliding window 互換)
        return list(reversed(list(raw)[-limit:]))

    def get_mid_summary_text(self, player_id: PlayerId) -> str:
        """L4 mid summary を prompt 用テキストに整形する。

        新しい世代から順に、各世代の compressed_activity / emotional_summary /
        unresolved を箇条書きで並べる。L4 が空なら空文字 (= section 非表示)。
        """
        pid = int(player_id.value)
        mid = self._mid.get(pid)
        if not mid:
            return ""
        return format_mid_summary_block(list(mid))

    # ──────────────────────────────────────────────────────────
    # 内部ロジック
    # ──────────────────────────────────────────────────────────

    def _ensure_player(self, pid: int) -> None:
        if pid not in self._raw:
            self._raw[pid] = deque()
            self._mid[pid] = deque()

    def _maybe_trigger_summary(self, pid: int) -> None:
        """L1 が閾値を超えたら L4 生成 trigger を発火する。

        - soft_cap 到達 → LLM 生成を試みる (失敗時 template fallback)
        - hard_cap 到達 → 強制的に template fallback (LLM なしまたは LLM 連続失敗時の安全弁)
        """
        raw = self._raw[pid]
        original_size = len(raw)
        if original_size < self._soft_cap:
            return

        # hard_cap 判定は popleft 前の元サイズで行う (review HIGH #2 修正)。
        # popleft 後だと「元サイズが hard_cap 以上か」を正しく判定できない。
        over_hard_cap = original_size >= self._hard_cap

        # 古い側から soft_cap 件を取り出す
        consumed: list[ObservationEntry] = []
        for _ in range(self._soft_cap):
            if not raw:
                break
            consumed.append(raw.popleft())
        if not consumed:
            return

        # service 未注入 or hard_cap 到達時 or LLM 失敗時は template fallback
        parsed: _ParsedSummary
        is_fallback = False

        if self._service is None or over_hard_cap:
            parsed = build_template_fallback_summary(consumed)
            is_fallback = True
            if over_hard_cap and self._service is not None:
                _logger.warning(
                    "RollingSummaryShortTermMemory(player_id=%s): L1 が hard cap "
                    "%d に到達、template fallback で強制圧縮します",
                    pid,
                    self._hard_cap,
                )
            elif over_hard_cap and self._service is None:
                # LLM 未配線 + hard_cap 到達: 本番設定で LLM 忘れの可能性が高い。
                # silent failure 防止のため debug ではなく info で出す。
                _logger.info(
                    "RollingSummaryShortTermMemory(player_id=%s): L1 が hard cap "
                    "%d に到達したが summary_service=None。template fallback のみで動作中",
                    pid,
                    self._hard_cap,
                )
        else:
            try:
                player_name, persona_block = self._resolve_persona(pid)
                previous_l4 = self._mid[pid][0] if self._mid[pid] else None
                parsed = self._service.generate(
                    player_name=player_name,
                    persona_block=persona_block,
                    observations=consumed,
                    previous_l4=previous_l4,
                )
            except (LlmApiCallException, ValueError) as e:
                _logger.warning(
                    "RollingSummaryShortTermMemory(player_id=%s): L4 LLM 生成失敗 "
                    "(%s); template fallback に縮退します",
                    pid,
                    e,
                )
                parsed = build_template_fallback_summary(consumed)
                is_fallback = True
            except Exception as e:  # pragma: no cover - 想定外も握って続行
                _logger.exception(
                    "RollingSummaryShortTermMemory(player_id=%s): 想定外の例外 "
                    "(%s); template fallback に縮退します",
                    pid,
                    e,
                )
                parsed = build_template_fallback_summary(consumed)
                is_fallback = True

        summary = L4MidSummary(
            summary_id=f"l4-{uuid4().hex}",
            player_id=pid,
            raw_count=len(consumed),
            generated_at=datetime.now(timezone.utc),
            compressed_activity=parsed.compressed_activity,
            emotional_summary=parsed.emotional_summary,
            unresolved=parsed.unresolved,
            is_fallback=is_fallback,
        )
        # 新しい世代を先頭に push、保持上限を超えたら最古を破棄
        self._mid[pid].appendleft(summary)
        while len(self._mid[pid]) > self._keep_gen:
            self._mid[pid].pop()

    def _resolve_persona(self, pid: int) -> tuple[str, str]:
        if self._persona_resolver is None:
            return (f"Player {pid}", "")
        try:
            name, persona = self._persona_resolver(pid)
            return (name or f"Player {pid}", persona or "")
        except Exception as e:
            _logger.warning(
                "persona_resolver failed for player_id=%s: %s; using defaults",
                pid,
                e,
            )
            return (f"Player {pid}", "")

    # ──────────────────────────────────────────────────────────
    # 検査用 (テスト + trace 用)
    # ──────────────────────────────────────────────────────────

    def _raw_queue_len(self, player_id: int) -> int:
        return len(self._raw.get(player_id, ()))

    def _mid_generations(self, player_id: int) -> list[L4MidSummary]:
        return list(self._mid.get(player_id, ()))


def format_mid_summary_block(generations: Sequence[L4MidSummary]) -> str:
    """L4 世代群を prompt 表示用に整形する (新しい順)。

    空 input なら空文字。先頭が「最新」になるよう呼出側で並べる前提。
    """
    if not generations:
        return ""
    blocks: list[str] = []
    for i, gen in enumerate(generations):
        header = "[最新] " if i == 0 else f"[{i+1} 世代前] "
        lines: list[str] = []
        lines.append(f"{header}{gen.compressed_activity.strip()}")
        if gen.emotional_summary.strip():
            lines.append(f"  気分: {gen.emotional_summary.strip()}")
        if gen.unresolved:
            lines.append("  未解決:")
            for u in gen.unresolved:
                lines.append(f"    - {u}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


__all__ = [
    "DEFAULT_L1_HARD_CAP",
    "DEFAULT_L1_SOFT_CAP",
    "DEFAULT_L4_KEEP_GENERATIONS",
    "PersonaResolverFn",
    "RollingSummaryShortTermMemory",
    "format_mid_summary_block",
]
