"""Memory Reflection ジョブを同一プロセスのバックグラウンドスレッドで処理する。"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from typing import Optional, Set

from ai_rpg_world.application.llm.exceptions import (
    LlmApiCallException,
    MemoryReflectionException,
)
from ai_rpg_world.application.llm.services.memory_reflection_processor import (
    AFTER_SUBJECTIVE_ENCODE_TRIGGER,
    DEFAULT_SITUATION_AFTER_ENCODE,
    DEFAULT_SITUATION_PASSIVE,
    MemoryReflectionJob,
    PASSIVE_RECALL_TRIGGER,
    SubjectiveMemoryReflectionProcessor,
)
from ai_rpg_world.application.llm.contracts.dtos import SubjectiveEpisode
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_RESCHEDULE_CODES = frozenset({"LLM_API_CALL_FAILED", "LLM_RATE_LIMIT"})


class SameProcessMemoryReflectionScheduler:
    """queue.Queue + daemon スレッド。enqueue の重複キーを抑止し、失敗時は指数バックオフで再キュー。"""

    def __init__(
        self,
        processor: SubjectiveMemoryReflectionProcessor,
        *,
        max_attempts: int = 4,
        backoff_base_seconds: float = 2.0,
        backoff_max_seconds: float = 120.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if not isinstance(processor, SubjectiveMemoryReflectionProcessor):
            raise TypeError("processor must be SubjectiveMemoryReflectionProcessor")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if backoff_base_seconds <= 0:
            raise ValueError("backoff_base_seconds must be greater than 0")
        self._processor = processor
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._q: queue.Queue[MemoryReflectionJob | None] = queue.Queue()
        self._inflight_keys: Set[str] = set()
        self._inflight_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop,
            name="MemoryReflectionWorker",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self, *, wait: bool = False, timeout: float = 5.0) -> None:
        self._stop.set()
        self._q.put(None)
        if wait:
            self._thread.join(timeout=timeout)

    @staticmethod
    def _job_key(job: MemoryReflectionJob) -> str:
        return f"{job.player_id.value}:{job.episode_id}:{job.trigger}"

    def enqueue(self, job: MemoryReflectionJob) -> bool:
        if not isinstance(job, MemoryReflectionJob):
            raise TypeError("job must be MemoryReflectionJob")
        key = self._job_key(job)
        with self._inflight_lock:
            if key in self._inflight_keys:
                self._logger.info(
                    "memory_reflection_enqueue_deduped",
                    extra={
                        "component": "memory_reflection",
                        "correlation_id": job.correlation_id,
                        "player_id": job.player_id.value,
                        "episode_id": job.episode_id,
                        "trigger": job.trigger,
                        "phase": "enqueue_deduped",
                    },
                )
                return False
            self._inflight_keys.add(key)
        self._q.put(job)
        self._logger.info(
            "memory_reflection_enqueued",
            extra={
                "component": "memory_reflection",
                "correlation_id": job.correlation_id,
                "player_id": job.player_id.value,
                "episode_id": job.episode_id,
                "trigger": job.trigger,
                "phase": "enqueued",
            },
        )
        return True

    def maybe_enqueue_after_subjective_encode(
        self,
        player_id: PlayerId,
        episode: SubjectiveEpisode,
        *,
        situation_text: str = "",
    ) -> bool:
        """encoding 成功直後に呼ぶ。トリガに応じてキューへ（Recall とは別経路）。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        correlation_id = uuid.uuid4().hex
        job = MemoryReflectionJob(
            player_id=player_id,
            episode_id=episode.episode_id,
            trigger=AFTER_SUBJECTIVE_ENCODE_TRIGGER,
            correlation_id=correlation_id,
            situation_text=situation_text or DEFAULT_SITUATION_AFTER_ENCODE,
        )
        return self.enqueue(job)

    def maybe_enqueue_passive_recall(
        self,
        player_id: PlayerId,
        episode_id: str,
        *,
        situation_text: str = "",
    ) -> bool:
        """Passive Recall で想起されたエピソードに対し、Reflection ジョブをキューする。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode_id, str) or not episode_id.strip():
            raise ValueError("episode_id must be non-empty str")
        correlation_id = uuid.uuid4().hex
        job = MemoryReflectionJob(
            player_id=player_id,
            episode_id=episode_id,
            trigger=PASSIVE_RECALL_TRIGGER,
            correlation_id=correlation_id,
            situation_text=situation_text.strip() or DEFAULT_SITUATION_PASSIVE,
        )
        return self.enqueue(job)

    def _release_key(self, job: MemoryReflectionJob) -> None:
        key = self._job_key(job)
        with self._inflight_lock:
            self._inflight_keys.discard(key)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:
                break
            try:
                self._run_with_retries(job)
            finally:
                self._release_key(job)
                self._q.task_done()

    def _run_with_retries(self, job: MemoryReflectionJob) -> None:
        delay = self._backoff_base
        for attempt in range(1, self._max_attempts + 1):
            try:
                self._processor.run_once(job)
                return
            except (MemoryReflectionException, LlmApiCallException) as e:
                code = getattr(e, "error_code", None)
                resched = isinstance(e, LlmApiCallException) and code in _RESCHEDULE_CODES
                self._logger.warning(
                    "memory_reflection_attempt_failed",
                    exc_info=True,
                    extra={
                        "component": "memory_reflection",
                        "correlation_id": job.correlation_id,
                        "player_id": job.player_id.value,
                        "episode_id": job.episode_id,
                        "trigger": job.trigger,
                        "phase": "attempt_failed",
                        "attempt": attempt,
                        "error_code": code,
                        "reschedulable": resched,
                    },
                )
                if attempt >= self._max_attempts or not resched:
                    self._logger.error(
                        "memory_reflection_dead_letter",
                        extra={
                            "component": "memory_reflection",
                            "correlation_id": job.correlation_id,
                            "player_id": job.player_id.value,
                            "episode_id": job.episode_id,
                            "trigger": job.trigger,
                            "phase": "dead_letter",
                            "attempt": attempt,
                        },
                    )
                    return
                time.sleep(min(delay, self._backoff_max))
                delay = min(delay * 2.0, self._backoff_max)
