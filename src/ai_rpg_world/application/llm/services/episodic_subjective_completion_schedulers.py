"""``IEpisodicSubjectiveCompletionScheduler`` の実装群 (PR #309 / Issue #295 後続)。

# 何のため

エピソード記憶の LLM 主観文付与 (``EpisodicChunkSubjectiveFieldsService``) を
「いつ・どこで」走らせるかの抽象化。chunk_coordinator は draft を episode_store
に書いた後、scheduler に「LLM 補完を投げる」だけ。完了時に scheduler が同じ
episode_id で store を上書きする。

# 提供する 2 実装

- ``InlineEpisodicSubjectiveScheduler``: 同期。submit が呼ばれた瞬間に LLM を
  叩く。テスト / オフライン用途 / 段階的移行用。
- ``ThreadPoolEpisodicSubjectiveScheduler``: 非同期。``concurrent.futures.ThreadPoolExecutor``
  でバックグラウンド実行する本番想定の実装。

# Pattern A (Fire-and-forget + eventual consistency)

1. chunk_coordinator が draft (PR #305 のテンプレ既定値で埋まった episode) を
   即座に store に書く
2. scheduler.submit(draft, ...) で LLM 呼び出しを投入 (非ブロッキング)
3. ワーカーが裏で ``service.merge_llm_subjective_fields`` を呼び、merged を
   ``store.put(merged)`` で上書き (同じ episode_id)
4. recall side は draft でも merged でも読める。空でないテンプレ文章が常に
   prompt に乗ることが保証されている (#305)

# 並行性の前提

- ``InMemorySubjectiveEpisodeStore`` は PR #309 で thread-safe 化済み (内部 RLock)
- ``SubjectiveEpisode`` は ``frozen=True`` の dataclass で、呼び出し側に渡した
  オブジェクト自体は変化しない (上書きは store 内の dict 差し替えのみ)
- ワーカー thread の例外は **絶対に呼び出し元 thread に propagate しない** —
  WARN ログ + ``EPISODIC_SUBJECTIVE_FAILED`` trace を出して draft (= テンプレ
  既定値) のままにする
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Callable, Optional

from ai_rpg_world.application.llm.contracts.chunk_encoding import ChunkEncodingInput
from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import SubjectiveEpisode
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind

_logger = logging.getLogger(__name__)


def _emit_trace(
    recorder_provider: Optional[Callable[[], Optional[ITraceRecorder]]],
    tick_provider: Optional[Callable[[], Optional[int]]],
    *,
    kind: str,
    player_id: int,
    payload: dict,
) -> None:
    """trace event を最善努力で記録する (例外は握りつぶす)。"""
    recorder: Optional[ITraceRecorder] = None
    if recorder_provider is not None:
        try:
            recorder = recorder_provider()
        except Exception:
            _logger.debug("trace recorder provider raised", exc_info=True)
            recorder = None
    if recorder is None:
        return
    tick: Optional[int] = None
    if tick_provider is not None:
        try:
            tick = tick_provider()
        except Exception:
            tick = None
    try:
        recorder.record(kind, tick=tick, player_id=player_id, **payload)
    except Exception:
        # trace 失敗で本筋を止めない
        _logger.debug("trace recorder.record(%s) failed", kind, exc_info=True)


class InlineEpisodicSubjectiveScheduler:
    """submit と同じ thread で LLM を叩く同期実装。

    テスト / オフライン経路 / async が使えない CI 環境向け。
    レイテンシは ``ThreadPoolEpisodicSubjectiveScheduler`` と等価のメソッド
    挙動だが「ゲーム tick が LLM 完了までブロックする」。
    """

    def __init__(
        self,
        service: EpisodicChunkSubjectiveFieldsService,
        episode_store: IEpisodicEpisodeStore,
        *,
        trace_recorder_provider: Optional[Callable[[], Optional[ITraceRecorder]]] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        if not isinstance(service, EpisodicChunkSubjectiveFieldsService):
            raise TypeError("service must be EpisodicChunkSubjectiveFieldsService")
        if not isinstance(episode_store, IEpisodicEpisodeStore):
            raise TypeError("episode_store must be IEpisodicEpisodeStore")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")
        self._service = service
        self._store = episode_store
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def submit(
        self,
        draft: SubjectiveEpisode,
        *,
        persona_text: str,
        encoding_input: ChunkEncodingInput,
    ) -> None:
        if not isinstance(draft, SubjectiveEpisode):
            raise TypeError("draft must be SubjectiveEpisode")
        if not isinstance(persona_text, str):
            raise TypeError("persona_text must be str")
        if not isinstance(encoding_input, ChunkEncodingInput):
            raise TypeError("encoding_input must be ChunkEncodingInput")
        start = time.monotonic()
        try:
            merged = self._service.merge_llm_subjective_fields(
                draft,
                persona_text=persona_text,
                encoding_input=encoding_input,
            )
            self._store.put(merged)
        except Exception as exc:
            _logger.warning(
                "InlineEpisodicSubjectiveScheduler: LLM 補完が失敗 (%s)。"
                "draft (テンプレ既定値) のまま継続。",
                exc,
            )
            _emit_trace(
                self._trace_recorder_provider,
                self._current_tick_provider,
                kind=TraceEventKind.EPISODIC_SUBJECTIVE_FAILED,
                player_id=int(draft.player_id),
                payload={
                    "episode_id": draft.episode_id,
                    "error_code": type(exc).__name__,
                },
            )
            return
        latency_ms = int((time.monotonic() - start) * 1000)
        recall_snippet = (merged.recall_text or "")[:120]
        _emit_trace(
            self._trace_recorder_provider,
            self._current_tick_provider,
            kind=TraceEventKind.EPISODIC_SUBJECTIVE_FILLED,
            player_id=int(merged.player_id),
            payload={
                "episode_id": merged.episode_id,
                "latency_ms": latency_ms,
                "recall_text_snippet": recall_snippet,
            },
        )

    def shutdown(self, timeout: Optional[float] = None) -> None:
        # 同期実装はキュー無し。何もしない。
        del timeout


class ThreadPoolEpisodicSubjectiveScheduler:
    """``concurrent.futures.ThreadPoolExecutor`` で LLM 補完を裏で走らせる実装。

    LLM API は I/O bound (HTTP 待ち) なので GIL は実害が無い。

    Args:
        service: LLM を呼ぶサービス本体
        episode_store: 完了時に上書きする store (thread-safe 前提、
            ``InMemorySubjectiveEpisodeStore`` は #309 で保護済み)
        max_workers: ワーカー thread 数 (既定 1)。LLM API の RPS 制限を考慮
            すると 1〜2 が安全側。
        max_queue_size: in-flight + pending の上限。これを超えて submit された
            ジョブは drop + ``EPISODIC_SUBJECTIVE_DROPPED`` trace を吐く。
            既定 100 (= プレイヤー数 × 数十 chunk を許容)。
        trace_recorder_provider / current_tick_provider: 任意の trace 配線。
    """

    def __init__(
        self,
        service: EpisodicChunkSubjectiveFieldsService,
        episode_store: IEpisodicEpisodeStore,
        *,
        max_workers: int = 1,
        max_queue_size: int = 100,
        trace_recorder_provider: Optional[Callable[[], Optional[ITraceRecorder]]] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        if not isinstance(service, EpisodicChunkSubjectiveFieldsService):
            raise TypeError("service must be EpisodicChunkSubjectiveFieldsService")
        if not isinstance(episode_store, IEpisodicEpisodeStore):
            raise TypeError("episode_store must be IEpisodicEpisodeStore")
        if not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive int")
        if not isinstance(max_queue_size, int) or max_queue_size < 1:
            raise ValueError("max_queue_size must be a positive int")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")

        self._service = service
        self._store = episode_store
        self._max_queue_size = max_queue_size
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="episodic_subj",
        )
        # in-flight / queued ジョブの追跡: episode_id → Future。
        # 同一 episode の重複 submit を dedupe するためにも使う。
        self._inflight: dict[str, Future] = {}
        self._inflight_lock = threading.Lock()
        self._is_shutdown = False

    def submit(
        self,
        draft: SubjectiveEpisode,
        *,
        persona_text: str,
        encoding_input: ChunkEncodingInput,
    ) -> None:
        if not isinstance(draft, SubjectiveEpisode):
            raise TypeError("draft must be SubjectiveEpisode")
        if not isinstance(persona_text, str):
            raise TypeError("persona_text must be str")
        if not isinstance(encoding_input, ChunkEncodingInput):
            raise TypeError("encoding_input must be ChunkEncodingInput")
        eid = draft.episode_id
        # 重複 / overflow / shutdown チェックはロック内で原子的に
        with self._inflight_lock:
            if self._is_shutdown:
                # shutdown 後の submit は静かに drop する
                return
            if eid in self._inflight:
                # 同一 episode の重複投入は無視 (chunk_coordinator がリトライした
                # ケース等)
                return
            if len(self._inflight) >= self._max_queue_size:
                _logger.warning(
                    "ThreadPoolEpisodicSubjectiveScheduler: キュー満杯 "
                    "(%d/%d)、新規 submit を drop: episode_id=%s",
                    len(self._inflight),
                    self._max_queue_size,
                    eid,
                )
                _emit_trace(
                    self._trace_recorder_provider,
                    self._current_tick_provider,
                    kind=TraceEventKind.EPISODIC_SUBJECTIVE_DROPPED,
                    player_id=int(draft.player_id),
                    payload={
                        "episode_id": eid,
                        "queue_size": len(self._inflight),
                        "max_queue_size": self._max_queue_size,
                    },
                )
                return
            # ロック内で Future を確保するが、実行は submit() の外でも問題ない
            # (ThreadPoolExecutor.submit はそれ自体 thread-safe)
            try:
                future = self._executor.submit(
                    self._worker, draft, persona_text, encoding_input
                )
            except RuntimeError:
                # Executor が shutdown 済み (競合) → drop
                _logger.debug("Executor shutdown during submit", exc_info=True)
                return
            self._inflight[eid] = future
        # done callback は inflight からの除去のみ。trace は worker 内で吐く
        # (失敗時とで分けるため)。
        future.add_done_callback(lambda _fut, _eid=eid: self._on_done(_eid))

    def _on_done(self, episode_id: str) -> None:
        with self._inflight_lock:
            self._inflight.pop(episode_id, None)

    def _worker(
        self,
        draft: SubjectiveEpisode,
        persona_text: str,
        encoding_input: ChunkEncodingInput,
    ) -> None:
        """ワーカー thread の本体。例外は呼び出し元に propagate しないこと。"""
        start = time.monotonic()
        try:
            merged = self._service.merge_llm_subjective_fields(
                draft,
                persona_text=persona_text,
                encoding_input=encoding_input,
            )
            self._store.put(merged)
        except Exception as exc:
            _logger.warning(
                "ThreadPoolEpisodicSubjectiveScheduler worker failed (%s)。"
                "draft (テンプレ既定値) のまま継続: episode_id=%s",
                exc,
                draft.episode_id,
                exc_info=True,
            )
            _emit_trace(
                self._trace_recorder_provider,
                self._current_tick_provider,
                kind=TraceEventKind.EPISODIC_SUBJECTIVE_FAILED,
                player_id=int(draft.player_id),
                payload={
                    "episode_id": draft.episode_id,
                    "error_code": type(exc).__name__,
                },
            )
            return
        latency_ms = int((time.monotonic() - start) * 1000)
        recall_snippet = (merged.recall_text or "")[:120]
        _emit_trace(
            self._trace_recorder_provider,
            self._current_tick_provider,
            kind=TraceEventKind.EPISODIC_SUBJECTIVE_FILLED,
            player_id=int(merged.player_id),
            payload={
                "episode_id": merged.episode_id,
                "latency_ms": latency_ms,
                "recall_text_snippet": recall_snippet,
            },
        )

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """進行中ジョブを drain しつつ executor を閉じる。

        ``timeout=None`` は完了まで無期限待機。``timeout`` 秒経っても残って
        いるジョブは諦めて (cancel) executor を強制終了する。

        shutdown 後の ``submit`` は静かに drop される。
        """
        with self._inflight_lock:
            self._is_shutdown = True
            pending = list(self._inflight.values())
        if timeout is None:
            # 全部待つ
            self._executor.shutdown(wait=True)
            return
        if pending:
            try:
                wait(pending, timeout=timeout)
            except Exception:
                _logger.debug("wait() raised during shutdown", exc_info=True)
        # 残ったジョブはキャンセル可能なものだけキャンセル、走り始めたものは諦める
        self._executor.shutdown(wait=False, cancel_futures=True)

    # テスト用ヘルパ (private 扱い)
    def _inflight_count(self) -> int:
        with self._inflight_lock:
            return len(self._inflight)


__all__ = [
    "InlineEpisodicSubjectiveScheduler",
    "ThreadPoolEpisodicSubjectiveScheduler",
]
