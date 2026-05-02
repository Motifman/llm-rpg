"""pending の EpisodeCandidate を Encoder で SubjectiveEpisode に変換する。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeEncodingContextDto,
    SubjectiveEpisode,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IEpisodeCandidateStore,
    IEpisodeEncoder,
    ISubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.exceptions import EpisodeEncodingException
from ai_rpg_world.application.llm.services.experience_trace_bundle_resolver import (
    ExperienceTraceBundleResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EpisodeEncodingProcessor:
    """list_pending_encoding → resolve traces → encode → store → candidate を encoded に更新。"""

    def __init__(
        self,
        *,
        candidate_store: IEpisodeCandidateStore,
        trace_resolver: ExperienceTraceBundleResolver,
        subjective_episode_store: ISubjectiveEpisodeStore,
        encoder: IEpisodeEncoder,
        context_provider: Callable[[PlayerId], EpisodeEncodingContextDto],
        max_retries: int = 2,
        max_queue_retries: int = 5,
        encoding_backoff_base_seconds: float = 2.0,
        encoding_backoff_max_seconds: float = 300.0,
        utc_now: Callable[[], datetime] = _default_utc_now,
        on_subjective_episode_encoded: Optional[
            Callable[[PlayerId, SubjectiveEpisode], None]
        ] = None,
    ) -> None:
        if not isinstance(candidate_store, IEpisodeCandidateStore):
            raise TypeError("candidate_store must be IEpisodeCandidateStore")
        if not isinstance(trace_resolver, ExperienceTraceBundleResolver):
            raise TypeError("trace_resolver must be ExperienceTraceBundleResolver")
        if not isinstance(subjective_episode_store, ISubjectiveEpisodeStore):
            raise TypeError("subjective_episode_store must be ISubjectiveEpisodeStore")
        if not isinstance(encoder, IEpisodeEncoder):
            raise TypeError("encoder must be IEpisodeEncoder")
        if not callable(context_provider):
            raise TypeError("context_provider must be callable")
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if max_queue_retries < 0:
            raise ValueError("max_queue_retries must be 0 or greater")
        if encoding_backoff_base_seconds <= 0:
            raise ValueError("encoding_backoff_base_seconds must be greater than 0")
        if encoding_backoff_max_seconds < encoding_backoff_base_seconds:
            raise ValueError(
                "encoding_backoff_max_seconds must be >= encoding_backoff_base_seconds"
            )
        if not callable(utc_now):
            raise TypeError("utc_now must be callable")
        if on_subjective_episode_encoded is not None and not callable(
            on_subjective_episode_encoded
        ):
            raise TypeError(
                "on_subjective_episode_encoded must be callable or None"
            )
        self._candidates = candidate_store
        self._resolver = trace_resolver
        self._episodes = subjective_episode_store
        self._encoder = encoder
        self._context_provider = context_provider
        self._max_retries = max_retries
        self._max_queue_retries = max_queue_retries
        self._backoff_base = encoding_backoff_base_seconds
        self._backoff_max = encoding_backoff_max_seconds
        self._utc_now = utc_now
        self._on_subjective_episode_encoded = on_subjective_episode_encoded

    def process_pending(
        self,
        player_id: PlayerId,
        *,
        encoding_runtime: Optional[ToolRuntimeContextDto] = None,
    ) -> int:
        """pending_encoding の候補を処理し、新規保存した SubjectiveEpisode の件数を返す。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        pending = self._candidates.list_pending_encoding(player_id, limit=100)
        encoded_count = 0
        now = self._utc_now()
        for cand in pending:
            if cand.status != "pending_encoding":
                continue
            if not self._is_due_for_retry(cand, now):
                continue
            try:
                traces = self._resolver.resolve_ordered(player_id, cand.source_trace_ids)
            except ValueError as e:
                self._mark_permanently_failed(player_id, cand, str(e))
                continue
            ctx = self._context_provider(player_id)
            if not isinstance(ctx, EpisodeEncodingContextDto):
                raise TypeError("context_provider must return EpisodeEncodingContextDto")
            episode = None
            last_err: Optional[str] = None
            for _ in range(self._max_retries):
                try:
                    episode = self._encoder.encode(
                        ctx,
                        cand,
                        traces,
                        encoding_runtime=encoding_runtime,
                    )
                    break
                except EpisodeEncodingException as e:
                    last_err = str(e)
            if episode is None:
                self._schedule_or_fail_llm_encoding(
                    player_id, cand, last_err or "Episode encoding failed"
                )
                continue
            self._episodes.put(player_id, episode)
            done = replace(
                cand,
                status="encoded",
                subjective_episode_id=episode.episode_id,
                encoding_error=None,
                encoding_retry_count=0,
                last_encoding_failure_at=None,
            )
            self._candidates.replace_candidate(player_id, done)
            encoded_count += 1
            if self._on_subjective_episode_encoded is not None:
                self._on_subjective_episode_encoded(player_id, episode)
        return encoded_count

    def _is_due_for_retry(self, cand, now: datetime) -> bool:
        if cand.last_encoding_failure_at is None:
            return True
        if cand.encoding_retry_count < 1:
            return True
        exp = min(
            self._backoff_max,
            self._backoff_base * (2.0 ** (cand.encoding_retry_count - 1)),
        )
        due_at = cand.last_encoding_failure_at + timedelta(seconds=exp)
        return now >= due_at

    def _schedule_or_fail_llm_encoding(
        self, player_id: PlayerId, cand, message: str
    ) -> None:
        short = message[:2000] if message else "unknown error"
        next_count = cand.encoding_retry_count + 1
        if next_count > self._max_queue_retries:
            self._mark_permanently_failed(player_id, cand, short)
            return
        retried = replace(
            cand,
            status="pending_encoding",
            subjective_episode_id=None,
            encoding_error=None,
            encoding_retry_count=next_count,
            last_encoding_failure_at=self._utc_now(),
        )
        self._candidates.replace_candidate(player_id, retried)

    def _mark_permanently_failed(self, player_id: PlayerId, cand, message: str) -> None:
        short = message[:2000] if message else "unknown error"
        failed = replace(
            cand,
            status="encoding_failed",
            subjective_episode_id=None,
            encoding_error=short,
            encoding_retry_count=0,
            last_encoding_failure_at=None,
        )
        self._candidates.replace_candidate(player_id, failed)
