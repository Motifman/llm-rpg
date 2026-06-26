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
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.interfaces import ISlidingWindowMemory
from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
    L5LongSummary,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
    ShortTermMemoryLongSummaryService,
    _ParsedLongSummary,
    build_template_fallback_long_summary,
)
from ai_rpg_world.application.llm.services.short_term_memory_schedulers import (
    InlineShortTermMemoryScheduler,
    IShortTermMemoryScheduler,
)
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
    ShortTermMemorySummaryService,
    _ParsedSummary,
    build_template_fallback_summary,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder, NullTraceRecorder
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_logger = logging.getLogger(__name__)


# raw queue の閾値。docs §3 の (15, 25) を採用。
DEFAULT_L1_SOFT_CAP = 15
DEFAULT_L1_HARD_CAP = 25
DEFAULT_L4_KEEP_GENERATIONS = 3


# PR #449 (PR 4/6): NullObject パターンで silent None skip を排除する helper。
# 構築時 / setter 時にこれを通すことで、emit 経路が `if provider is None` /
# `if recorder is None` のチェックを書かなくてよくなる。
_DEFAULT_NULL_RECORDER = NullTraceRecorder()


def _ensure_trace_recorder_provider(
    provider: Optional[Callable[[], Any]],
) -> Callable[[], ITraceRecorder]:
    """provider を ``Callable[[], ITraceRecorder]`` に正規化する。

    - None なら NullTraceRecorder を返す provider に置き換え
    - 既存 provider が None を返した場合も NullTraceRecorder を返すように
      wrap (= 後方互換 / lazy lookup で recorder 未確定の場合)
    """
    if provider is None:
        return lambda: _DEFAULT_NULL_RECORDER

    def _wrapped() -> ITraceRecorder:
        try:
            recorder = provider()
        except Exception:
            # provider 自体が例外を投げる場合も NullTraceRecorder にフォールバック
            return _DEFAULT_NULL_RECORDER
        return recorder if recorder is not None else _DEFAULT_NULL_RECORDER

    return _wrapped


# persona resolver は (player_id_int) -> (player_name, persona_block)
PersonaResolverFn = Callable[[int], "tuple[str, str]"]


class RollingSummaryShortTermMemory(ISlidingWindowMemory):
    """L1 raw + L4 mid summary 階層型の短期記憶 (Phase 2)。

    L4 生成タスクは ``scheduler`` 経由で実行される (Phase 2.1):

    - 未指定 → ``InlineShortTermMemoryScheduler`` (生成は submit と同じ
      thread で同期実行、tick が 2-5s ブロックする)
    - ``ThreadPoolShortTermMemoryScheduler`` を渡せば非同期化 (生成中も
      tick は進む)

    非同期時に注意:
    - L4 install (``_mid`` 書き込み) は worker thread から呼ばれる →
      ``_mid_lock`` で保護
    - ``get_mid_summary_text`` 読み出しも同 lock 内で snapshot を取る
    - L1 (``_raw``) は main thread のみが触る (append / 消費 popleft 両方)
      ので lock 不要

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
        long_summary_service: Optional[ShortTermMemoryLongSummaryService] = None,
        persona_resolver: Optional[PersonaResolverFn] = None,
        l1_soft_cap: int = DEFAULT_L1_SOFT_CAP,
        l1_hard_cap: int = DEFAULT_L1_HARD_CAP,
        l4_keep_generations: int = DEFAULT_L4_KEEP_GENERATIONS,
        scheduler: Optional[IShortTermMemoryScheduler] = None,
        # PR #435: L4 / L5 が install された瞬間に trace event を 1 件吐く。
        # 失敗時は既に DROPPED / GENERATION_FAILED が吐かれているが、成功時の
        # 生成内容を後追いする経路が無かった。両方とも optional で、None なら
        # 完全 no-op (= 既存挙動の後方互換 / テスト fixture が簡素)。
        trace_recorder_provider: Optional[Callable[[], Any]] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
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
        if long_summary_service is not None and not isinstance(
            long_summary_service, ShortTermMemoryLongSummaryService
        ):
            raise TypeError(
                "long_summary_service must be ShortTermMemoryLongSummaryService or None"
            )
        if persona_resolver is not None and not callable(persona_resolver):
            raise TypeError("persona_resolver must be callable or None")
        if scheduler is not None and not isinstance(scheduler, IShortTermMemoryScheduler):
            raise TypeError(
                "scheduler must be IShortTermMemoryScheduler or None"
            )
        self._service = summary_service
        self._long_service = long_summary_service
        self._persona_resolver = persona_resolver
        self._soft_cap = l1_soft_cap
        self._hard_cap = l1_hard_cap
        self._keep_gen = l4_keep_generations
        self._scheduler: IShortTermMemoryScheduler = (
            scheduler if scheduler is not None else InlineShortTermMemoryScheduler()
        )
        # PR #449 (PR 4/6): trace_recorder_provider が None でも常に
        # NullTraceRecorder を返す callable に正規化する。これで emit 側の
        # `if provider is None: return` / `if recorder is None: return` の
        # silent skip 経路を排除できる (= NullObject パターン)。
        self._trace_recorder_provider: Callable[[], ITraceRecorder] = (
            _ensure_trace_recorder_provider(trace_recorder_provider)
        )
        self._current_tick_provider = current_tick_provider
        self._raw: Dict[int, Deque[ObservationEntry]] = {}
        # L4 は新しい順に並べる (index 0 = 最新)。worker thread からも書く
        # ので mid_lock で保護する。
        self._mid: Dict[int, Deque[L4MidSummary]] = {}
        self._mid_lock = threading.Lock()
        # Phase 3: L5 long summary (1 player 1 件)。worker thread からも書く
        # ので long_lock で保護する。世代数のカウンタも保持。
        self._long: Dict[int, L5LongSummary] = {}
        self._long_gen_index: Dict[int, int] = {}
        self._long_lock = threading.Lock()

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

    def get_oldest_entry_datetime(
        self, player_id: PlayerId
    ) -> Optional[datetime]:
        """PR5 (R1): 現在 short-term window に乗っている最古 entry の ``occurred_at``。

        L1 raw queue の最古 entry を返す。L4 mid summary は raw を畳んだ
        概要であり、構成要素の raw entry そのものは既に retire 済みなので、
        ここでは含めない (= 「**今 raw として手元にあるもの**」の最古を
        返す)。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        pid = int(player_id.value)
        raw = self._raw.get(pid)
        if not raw:
            return None
        # raw queue には naive な datetime (= シナリオファイル由来) と aware な
        # datetime (= LLM 呼び出し後に dataset から組まれた直近観測) が混在しうる。
        # そのまま min() で比較すると ``TypeError: can't compare offset-naive
        # and offset-aware datetimes`` で実験が落ちるため、UTC 相当として
        # 正規化してから比較する。本体の occurred_at は書き換えない。
        def _as_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        return min(_as_utc(entry.occurred_at) for entry in raw)

    def get_long_summary_text(self, player_id: PlayerId) -> str:
        """Phase 3: L5 long summary を prompt 用テキストに整形する。

        L5 未生成なら空文字 (= section 非表示)。
        """
        pid = int(player_id.value)
        with self._long_lock:
            l5 = self._long.get(pid)
        if l5 is None:
            return ""
        return format_long_summary_block(l5)

    def get_mid_summary_text(self, player_id: PlayerId) -> str:
        """L4 mid summary を prompt 用テキストに整形する。

        新しい世代から順に、各世代の compressed_activity / emotional_summary /
        unresolved を箇条書きで並べる。L4 が空なら空文字 (= section 非表示)。

        non-blocking: lock の中で snapshot を取って lock 外で整形する。
        """
        pid = int(player_id.value)
        with self._mid_lock:
            mid = self._mid.get(pid)
            if not mid:
                return ""
            snapshot = list(mid)
        return format_mid_summary_block(snapshot)

    # ──────────────────────────────────────────────────────────
    # 内部ロジック
    # ──────────────────────────────────────────────────────────

    def _ensure_player(self, pid: int) -> None:
        """player 別 dict を初期化する。

        現状の前提: ``_raw`` は main thread のみが触る。``_mid`` は main +
        worker 両方が触るため ``_mid_lock`` で保護する。``_raw`` 初期化も
        同じ lock 内で行うことで、将来 multi-thread 化されても自己防衛可能
        にしておく (review HIGH #2)。
        """
        with self._mid_lock:
            if pid not in self._raw:
                self._raw[pid] = deque()
            if pid not in self._mid:
                self._mid[pid] = deque()

    def _maybe_trigger_summary(self, pid: int) -> None:
        """L1 が閾値を超えたら L4 生成タスクを scheduler に投げる。

        - soft_cap 到達 → LLM 生成を試みる (失敗時 template fallback)
        - hard_cap 到達 → 強制的に template fallback (LLM なしまたは LLM 連続失敗時の安全弁)

        Phase 2.1: 生成は scheduler 経由。Inline なら同期、ThreadPool なら非同期。
        consumed observations と previous_l4 snapshot を **submit 前に確定** させて
        クロージャに渡すので、worker thread の race を避けられる。
        """
        raw = self._raw[pid]
        original_size = len(raw)
        if original_size < self._soft_cap:
            return

        # hard_cap 判定は popleft 前の元サイズで行う
        over_hard_cap = original_size >= self._hard_cap

        # 古い側から soft_cap 件を取り出す (main thread のみが触る → lock 不要)
        consumed: list[ObservationEntry] = []
        for _ in range(self._soft_cap):
            if not raw:
                break
            consumed.append(raw.popleft())
        if not consumed:
            return

        # previous_l4 snapshot を ロック内で取る (worker からの書き込みと race
        # しないように)
        with self._mid_lock:
            previous_l4 = self._mid[pid][0] if self._mid[pid] else None

        force_fallback = over_hard_cap or self._service is None
        if over_hard_cap and self._service is not None:
            _logger.warning(
                "RollingSummaryShortTermMemory(player_id=%s): L1 が hard cap "
                "%d に到達、template fallback で強制圧縮します",
                pid,
                self._hard_cap,
            )
        elif over_hard_cap and self._service is None:
            _logger.info(
                "RollingSummaryShortTermMemory(player_id=%s): L1 が hard cap "
                "%d に到達したが summary_service=None。template fallback のみで動作中",
                pid,
                self._hard_cap,
            )

        # task: クロージャ。submit-time に確定した値だけをキャプチャ。
        def _task() -> None:
            self._run_generation(
                pid=pid,
                consumed=consumed,
                previous_l4=previous_l4,
                force_fallback=force_fallback,
            )

        accepted = self._scheduler.submit(pid, _task)
        if not accepted:
            # review HIGH #1: scheduler が drop した時、consumed observations は
            # 既に _raw から popleft 済みなので失われる (silent data loss)。
            # trace event は scheduler が emit するが、件数情報は memory 側でしか
            # 持っていないので、ここで明示的に WARNING + 件数を残す。
            _logger.warning(
                "RollingSummaryShortTermMemory(player_id=%s): scheduler が "
                "task を drop。%d 件の observations は L1 / L4 のどちらにも "
                "残らず失われます (queue_full or shutdown 由来)。",
                pid,
                len(consumed),
            )

    def _run_generation(
        self,
        *,
        pid: int,
        consumed: list[ObservationEntry],
        previous_l4: Optional[L4MidSummary],
        force_fallback: bool,
    ) -> None:
        """L4 生成本体。Inline なら main thread、ThreadPool なら worker thread。"""
        parsed: _ParsedSummary
        is_fallback = False

        if force_fallback:
            parsed = build_template_fallback_summary(consumed)
            is_fallback = True
        else:
            assert self._service is not None  # force_fallback=False の暗黙保証
            try:
                player_name, persona_block = self._resolve_persona(pid)
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
        self._install_l4(summary)

    def set_trace_recorder_provider(
        self, provider: Optional[Callable[[], Any]]
    ) -> None:
        """trace_recorder_provider を後から差し替える (PR #439 / PR #449 正規化)。

        ``world_runtime`` のように runtime 構築時点では trace_recorder が
        まだ確定していない経路で、後付け注入するための setter。

        PR #449 (PR 4/6): 受け取った provider は ``_ensure_trace_recorder_provider``
        を通して正規化する。None / 例外 / None 返却の全パターンで NullTraceRecorder
        にフォールバックする callable に変換されるので、emit 経路は常に
        ``recorder.record()`` を 1 度だけ呼ぶシンプルな形を維持できる。
        """
        self._trace_recorder_provider = _ensure_trace_recorder_provider(provider)

    def set_current_tick_provider(
        self, provider: Optional[Callable[[], Optional[int]]]
    ) -> None:
        """current_tick_provider を後から差し替える (PR #439)。

        trace event の tick フィールドを正しく入れたいときに使う。
        provider=None で None tick になる。
        """
        self._current_tick_provider = provider

    # PR #451 (PR 6/6): set_summary_services は廃止。
    # ctor で summary_service / long_summary_service / persona_resolver を必ず
    # 指定する経路に統一した (= setter 呼び忘れ silent failure を構造で排除)。
    # 旧来は world_runtime が runtime 構築時点で llm_client を持っていない
    # ライフサイクル都合で空殻 ctor + 後注入していたが、PR #451 で構築順序を
    # 整理して LLM 経路を ctor で揃えるようにした。

    def _emit_l4_generated(self, summary: L4MidSummary) -> None:
        """L4 install 直後に trace event を 1 件吐く (PR #435 / PR #449 簡略化)。

        PR #449 (PR 4/6): provider は ``_ensure_trace_recorder_provider`` で
        正規化済 = **必ず ``ITraceRecorder`` を返す** (NullTraceRecorder fallback)。
        旧来の ``if provider is None`` / ``if recorder is None`` の silent skip
        経路を排除し、本体は recorder.record() を 1 度だけ呼ぶシンプル形に。

        recorder 側で例外が出ても本体経路を倒さないため except は残す。
        """
        try:
            self._trace_recorder_provider().record(
                TraceEventKind.SHORT_TERM_SUMMARY_GENERATED,
                tick=self._safe_current_tick(),
                player_id=summary.player_id,
                summary_id=summary.summary_id,
                raw_count=summary.raw_count,
                compressed_activity=summary.compressed_activity,
                emotional_summary=summary.emotional_summary,
                unresolved=list(summary.unresolved),
                is_fallback=summary.is_fallback,
            )
        except Exception:
            _logger.exception(
                "trace recorder.record raised for SHORT_TERM_SUMMARY_GENERATED; skipping"
            )

    def _emit_l5_generated(self, summary: L5LongSummary) -> None:
        """L5 install 直後に trace event を 1 件吐く (PR #435 / PR #449 簡略化)。"""
        try:
            self._trace_recorder_provider().record(
                TraceEventKind.SHORT_TERM_LONG_SUMMARY_GENERATED,
                tick=self._safe_current_tick(),
                player_id=summary.player_id,
                summary_id=summary.summary_id,
                generation_index=summary.generation_index,
                self_image=summary.self_image,
                world_view=summary.world_view,
                is_fallback=summary.is_fallback,
            )
        except Exception:
            _logger.exception(
                "trace recorder.record raised for SHORT_TERM_LONG_SUMMARY_GENERATED; skipping"
            )

    def _safe_current_tick(self) -> Optional[int]:
        """current_tick_provider を best-effort で評価。例外は None に縮退。"""
        if self._current_tick_provider is None:
            return None
        try:
            return self._current_tick_provider()
        except Exception:
            return None

    def _install_l4(self, summary: L4MidSummary) -> None:
        """新世代 L4 を mid に push する (thread-safe)。

        Inline scheduler では main thread が呼ぶ。ThreadPool では worker
        thread から呼ばれるので必ず lock 内で書き込む。

        通常 ``_ensure_player`` が先に呼ばれている前提だが、テストから
        ``_install_l4`` を直接呼ぶ経路や、将来の coordinator 経路への防衛と
        して、ここでも player 初期化を行う (review HIGH #3)。

        Phase 3: keep_gen を超えて evict された L4 は L5 統合タスクに回す。
        evict は lock 内で検出して取り出し、L5 task の submit は lock 外で行う
        (scheduler 内部の lock とのデッドロック回避)。
        """
        evicted_l4: Optional[L4MidSummary] = None
        pid = summary.player_id
        with self._mid_lock:
            if pid not in self._mid:
                self._mid[pid] = deque()
            self._mid[pid].appendleft(summary)
            while len(self._mid[pid]) > self._keep_gen:
                evicted_l4 = self._mid[pid].pop()

        # PR #435: 成功時の生成内容を trace に残す。lock 外で emit する
        # (recorder の I/O が L4 install を blocking しないように)。
        self._emit_l4_generated(summary)

        if evicted_l4 is not None:
            self._maybe_trigger_long_summary(pid, evicted_l4)

    def _maybe_trigger_long_summary(
        self, pid: int, evicted_l4: L4MidSummary
    ) -> None:
        """Phase 3: L4 が evict されたタイミングで L5 統合 task を投げる。

        - ``long_summary_service=None`` → template fallback で延命 (LLM なしモード)
        - service あり + LLM 成功 → 新 L5
        - service あり + LLM 失敗 → 同じく template fallback で previous_l5 延命

        scheduler.submit の戻り値が False (drop) の場合は WARNING ログを残す
        (L4 既に evict 済みで失われる)。

        **並列性に関する重要な制約 (review HIGH #2)**:
        ``ThreadPoolShortTermMemoryScheduler`` の ``max_workers=1`` (default) を
        前提にしている。同一プレイヤーに対して 2 つの L5 task が並列実行されると
        どちらも同じ ``previous_l5`` snapshot を保持したまま LLM を呼び、
        後勝ちで新世代が古い ``evicted_l4`` に基づく内容で上書きされる risk が
        ある。default 構成 (wiring 経由の ``_build_short_term_memory``) では
        max_workers=1 を使うので影響なし。
        """
        with self._long_lock:
            previous_l5 = self._long.get(pid)

        def _task() -> None:
            self._run_long_generation(
                pid=pid,
                evicted_l4=evicted_l4,
                previous_l5=previous_l5,
            )

        accepted = self._scheduler.submit(pid, _task)
        if not accepted:
            _logger.warning(
                "RollingSummaryShortTermMemory(player_id=%s): scheduler が L5 "
                "統合 task を drop。evicted L4 (summary_id=%s) は失われます "
                "(queue_full or shutdown 由来)。",
                pid,
                evicted_l4.summary_id,
            )

    def _run_long_generation(
        self,
        *,
        pid: int,
        evicted_l4: L4MidSummary,
        previous_l5: Optional[L5LongSummary],
    ) -> None:
        """L5 生成本体。Inline なら main thread、ThreadPool なら worker thread。"""
        parsed: _ParsedLongSummary
        is_fallback = False

        if self._long_service is None:
            parsed = build_template_fallback_long_summary(
                previous_l5=previous_l5,
                evicted_l4=evicted_l4,
            )
            is_fallback = True
        else:
            try:
                player_name, persona_block = self._resolve_persona(pid)
                parsed = self._long_service.generate(
                    player_name=player_name,
                    persona_block=persona_block,
                    previous_l5=previous_l5,
                    evicted_l4=evicted_l4,
                )
            except (LlmApiCallException, ValueError) as e:
                _logger.warning(
                    "RollingSummaryShortTermMemory(player_id=%s): L5 LLM 生成失敗 "
                    "(%s); template fallback (previous_l5 延命) に縮退します",
                    pid,
                    e,
                )
                parsed = build_template_fallback_long_summary(
                    previous_l5=previous_l5,
                    evicted_l4=evicted_l4,
                )
                is_fallback = True
            except Exception as e:  # pragma: no cover - 想定外も握って続行
                _logger.exception(
                    "RollingSummaryShortTermMemory(player_id=%s): 想定外の例外 "
                    "(%s); L5 template fallback に縮退します",
                    pid,
                    e,
                )
                parsed = build_template_fallback_long_summary(
                    previous_l5=previous_l5,
                    evicted_l4=evicted_l4,
                )
                is_fallback = True

        with self._long_lock:
            next_index = self._long_gen_index.get(pid, 0) + 1
            self._long_gen_index[pid] = next_index
            installed = L5LongSummary(
                summary_id=f"l5-{uuid4().hex}",
                player_id=pid,
                generation_index=next_index,
                generated_at=datetime.now(timezone.utc),
                self_image=parsed.self_image,
                world_view=parsed.world_view,
                is_fallback=is_fallback,
            )
            self._long[pid] = installed

        # PR #435: 成功時の生成内容を trace に残す。lock 外で emit する。
        self._emit_l5_generated(installed)

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

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """非同期 scheduler の場合 in-flight L4 生成を完了待ちで終了する。

        Inline scheduler の場合は no-op。
        """
        self._scheduler.shutdown(timeout=timeout)

    # ──────────────────────────────────────────────────────────
    # 検査用 (テスト + trace 用)
    # ──────────────────────────────────────────────────────────

    def _raw_queue_len(self, player_id: int) -> int:
        return len(self._raw.get(player_id, ()))

    def _mid_generations(self, player_id: int) -> list[L4MidSummary]:
        with self._mid_lock:
            return list(self._mid.get(player_id, ()))

    def _long_summary(self, player_id: int) -> Optional[L5LongSummary]:
        with self._long_lock:
            return self._long.get(player_id)


def format_long_summary_block(l5: L5LongSummary) -> str:
    """L5 を prompt 表示用に整形する (Phase 3)。

    self_image / world_view を 2 行で並べる。空ラインは出さない。
    """
    lines: list[str] = []
    if l5.self_image.strip():
        lines.append(f"私について: {l5.self_image.strip()}")
    if l5.world_view.strip():
        lines.append(f"この世界について: {l5.world_view.strip()}")
    return "\n".join(lines)


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
    "format_long_summary_block",
    "format_mid_summary_block",
]
