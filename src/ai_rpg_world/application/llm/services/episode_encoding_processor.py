"""pending の EpisodeCandidate を Encoder で SubjectiveEpisode に変換する。"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from ai_rpg_world.application.llm.contracts.dtos import EpisodeEncodingContextDto
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
        self._candidates = candidate_store
        self._resolver = trace_resolver
        self._episodes = subjective_episode_store
        self._encoder = encoder
        self._context_provider = context_provider
        self._max_retries = max_retries

    def process_pending(self, player_id: PlayerId) -> int:
        """pending_encoding の候補を処理し、新規保存した SubjectiveEpisode の件数を返す。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        pending = self._candidates.list_pending_encoding(player_id, limit=100)
        encoded_count = 0
        for cand in pending:
            if cand.status != "pending_encoding":
                continue
            try:
                traces = self._resolver.resolve_ordered(player_id, cand.source_trace_ids)
            except ValueError as e:
                self._mark_failed(player_id, cand, str(e))
                continue
            ctx = self._context_provider(player_id)
            if not isinstance(ctx, EpisodeEncodingContextDto):
                raise TypeError("context_provider must return EpisodeEncodingContextDto")
            episode = None
            last_err: Optional[str] = None
            for _ in range(self._max_retries):
                try:
                    episode = self._encoder.encode(ctx, cand, traces)
                    break
                except EpisodeEncodingException as e:
                    last_err = str(e)
            if episode is None:
                self._mark_failed(
                    player_id, cand, last_err or "Episode encoding failed"
                )
                continue
            self._episodes.put(player_id, episode)
            done = replace(
                cand,
                status="encoded",
                subjective_episode_id=episode.episode_id,
            )
            self._candidates.replace_candidate(player_id, done)
            encoded_count += 1
        return encoded_count

    def _mark_failed(self, player_id: PlayerId, cand, message: str) -> None:
        short = message[:2000] if message else "unknown error"
        failed = replace(
            cand,
            status="encoding_failed",
            encoding_error=short,
        )
        self._candidates.replace_candidate(player_id, failed)
