"""Memory Reflection: LLM 再解釈を実行し SubjectiveEpisode にジャーナルを追記する。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeEncodingContextDto,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IMemoryReflectionLlmPort,
    ISubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.exceptions import MemoryReflectionException
from ai_rpg_world.application.llm.services.llm_json_memory_reflection import (
    build_memory_reflection_user_prompt,
    memory_reflection_response_json_schema,
    memory_reflection_system_prompt,
    parse_memory_reflection_llm_text,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

AFTER_SUBJECTIVE_ENCODE_TRIGGER = "after_subjective_encode"
PASSIVE_RECALL_TRIGGER = "passive_recall"
DEFAULT_SITUATION_AFTER_ENCODE = (
    "主観エピソード encoding 直後。当該ターンの文脈は current_agent_context に含まれる。"
)
DEFAULT_SITUATION_PASSIVE = (
    "ターン中にルールベースの Passive Recall で関連エピソードが想起された直後。"
    " situation_text に当該ターンの状況が含まれる。"
)

_ENV_PASSIVE_COOLDOWN = "MEMORY_REFLECTION_PASSIVE_COOLDOWN_SECONDS"


def _passive_cooldown_seconds() -> float:
    raw = (os.environ.get(_ENV_PASSIVE_COOLDOWN) or "300").strip()
    try:
        v = float(raw)
    except ValueError:
        return 300.0
    return max(0.0, v)


def _default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MemoryReflectionJob:
    player_id: PlayerId
    episode_id: str
    trigger: str
    correlation_id: str
    situation_text: str = ""


class SubjectiveMemoryReflectionProcessor:
    """同一プロセス内ワーカーから呼ばれ、1 ジョブ分の Reflection を実行する。"""

    def __init__(
        self,
        *,
        subjective_episode_store: ISubjectiveEpisodeStore,
        llm_port: IMemoryReflectionLlmPort,
        context_provider: Callable[[PlayerId], EpisodeEncodingContextDto],
        structured_json_output: bool = True,
        utc_now: Callable[[], datetime] = _default_utc_now,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if not isinstance(subjective_episode_store, ISubjectiveEpisodeStore):
            raise TypeError("subjective_episode_store must be ISubjectiveEpisodeStore")
        if not isinstance(llm_port, IMemoryReflectionLlmPort):
            raise TypeError("llm_port must be IMemoryReflectionLlmPort")
        if not callable(context_provider):
            raise TypeError("context_provider must be callable")
        if not callable(utc_now):
            raise TypeError("utc_now must be callable")
        self._episodes = subjective_episode_store
        self._llm = llm_port
        self._context_provider = context_provider
        self._structured_json_output = structured_json_output
        self._utc_now = utc_now
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def run_once(self, job: MemoryReflectionJob) -> bool:
        """ジョブを 1 件処理する。スキップ（冪等）なら False、ジャーナル追記したら True。"""
        if not isinstance(job, MemoryReflectionJob):
            raise TypeError("job must be MemoryReflectionJob")
        player_id = job.player_id
        base_extra = {
            "component": "memory_reflection",
            "correlation_id": job.correlation_id,
            "player_id": player_id.value,
            "episode_id": job.episode_id,
            "trigger": job.trigger,
            "phase": "started",
        }
        self._logger.info("memory_reflection_job_started", extra=base_extra)

        episode = self._episodes.get_by_episode_id(player_id, job.episode_id)
        if episode is None:
            self._logger.warning(
                "memory_reflection_episode_missing",
                extra={**base_extra, "phase": "abandoned_missing_episode"},
            )
            return False

        if job.trigger == AFTER_SUBJECTIVE_ENCODE_TRIGGER and any(
            e.trigger == AFTER_SUBJECTIVE_ENCODE_TRIGGER
            for e in episode.memory_reflection_journal
        ):
            self._logger.info(
                "memory_reflection_skip_idempotent",
                extra={**base_extra, "phase": "skipped_already_reflected"},
            )
            return False

        if job.trigger == PASSIVE_RECALL_TRIGGER:
            cooldown = _passive_cooldown_seconds()
            if cooldown > 0:
                last_passive: Optional[datetime] = None
                for e in reversed(episode.memory_reflection_journal):
                    if e.trigger == PASSIVE_RECALL_TRIGGER:
                        last_passive = e.created_at
                        break
                if last_passive is not None:
                    now = self._utc_now()
                    delta = (now - last_passive).total_seconds()
                    if delta < cooldown:
                        self._logger.info(
                            "memory_reflection_skip_passive_cooldown",
                            extra={
                                **base_extra,
                                "phase": "skipped_passive_cooldown",
                                "cooldown_seconds": cooldown,
                                "elapsed_seconds": delta,
                            },
                        )
                        return False

        ctx = self._context_provider(player_id)
        if not isinstance(ctx, EpisodeEncodingContextDto):
            raise TypeError("context_provider must return EpisodeEncodingContextDto")

        if job.trigger == PASSIVE_RECALL_TRIGGER:
            default_situation = DEFAULT_SITUATION_PASSIVE
        else:
            default_situation = DEFAULT_SITUATION_AFTER_ENCODE
        situation = (
            job.situation_text if job.situation_text.strip() else default_situation
        )
        user_prompt = build_memory_reflection_user_prompt(
            episode, ctx, situation_text=situation
        )
        system_prompt = memory_reflection_system_prompt()
        response_format = None
        if self._structured_json_output:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "memory_reflection",
                    "strict": True,
                    "schema": memory_reflection_response_json_schema(),
                },
            }

        raw = self._llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
        )
        if not isinstance(raw, str) or not raw.strip():
            raise MemoryReflectionException(
                "empty LLM output",
                episode_id=job.episode_id,
                correlation_id=job.correlation_id,
            )

        created_at = self._utc_now()
        entry = parse_memory_reflection_llm_text(
            raw,
            correlation_id=job.correlation_id,
            trigger=job.trigger,
            created_at=created_at,
        )

        fresh = self._episodes.get_by_episode_id(player_id, job.episode_id)
        if fresh is None:
            self._logger.warning(
                "memory_reflection_episode_vanished",
                extra={**base_extra, "phase": "abandoned_concurrent"},
            )
            return False

        if job.trigger == AFTER_SUBJECTIVE_ENCODE_TRIGGER and any(
            e.trigger == AFTER_SUBJECTIVE_ENCODE_TRIGGER
            for e in fresh.memory_reflection_journal
        ):
            self._logger.info(
                "memory_reflection_race_skip",
                extra={**base_extra, "phase": "skipped_race"},
            )
            return False

        updated = replace(
            fresh,
            memory_reflection_journal=fresh.memory_reflection_journal + (entry,),
        )
        self._episodes.put(player_id, updated)
        self._logger.info(
            "memory_reflection_committed",
            extra={
                **base_extra,
                "phase": "committed",
                "journal_entry_id": entry.entry_id,
                "payload_digest": entry.raw_payload_digest,
            },
        )
        return True
