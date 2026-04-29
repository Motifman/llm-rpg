"""Memory Reflection（主観エピソード再解釈）の同一プロセス配線。"""

from __future__ import annotations

import os
from typing import Callable, Optional, Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeEncodingContextDto,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMClient,
    ISubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.memory_reflection_processor import (
    SubjectiveMemoryReflectionProcessor,
)
from ai_rpg_world.application.llm.services.same_process_memory_reflection_scheduler import (
    SameProcessMemoryReflectionScheduler,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
from ai_rpg_world.infrastructure.llm.litellm_memory_reflection_llm_port import (
    LiteLlmMemoryReflectionLlmPort,
)

_ENV_MEMORY_REFLECTION = "MEMORY_REFLECTION"
_ENV_MEMORY_REFLECTION_JSON_SCHEMA = "MEMORY_REFLECTION_JSON_SCHEMA"


def memory_reflection_enabled_from_env() -> bool:
    """未設定時は ON。`MEMORY_REFLECTION=0` 等で無効。"""
    raw = (os.environ.get(_ENV_MEMORY_REFLECTION) or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def memory_reflection_structured_output_from_env() -> bool:
    raw = (os.environ.get(_ENV_MEMORY_REFLECTION_JSON_SCHEMA) or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def memory_reflection_after_encode_filter_from_env() -> str:
    """`off`（既定）| `high` | `all`。encoding 直後に Reflection をキューするか。

    主経路は Passive Recall 経由のため、既定では encoding 後はキューしない。
    """
    return (os.environ.get("MEMORY_REFLECTION_AFTER_ENCODE") or "off").strip().lower()


def build_same_process_memory_reflection(
    *,
    llm_client: ILLMClient,
    subjective_episode_store: ISubjectiveEpisodeStore,
    context_provider: Callable[[PlayerId], EpisodeEncodingContextDto],
) -> tuple[
    Optional[SameProcessMemoryReflectionScheduler],
    Optional[Callable[[PlayerId, SubjectiveEpisode], None]],
]:
    """Stub クライアント・無効 env・非 LiteLLM のとき (None, None)。"""
    if isinstance(llm_client, StubLlmClient):
        return None, None
    if not memory_reflection_enabled_from_env():
        return None, None
    if not isinstance(llm_client, LiteLLMClient):
        return None, None

    port = LiteLlmMemoryReflectionLlmPort(llm_client)
    processor = SubjectiveMemoryReflectionProcessor(
        subjective_episode_store=subjective_episode_store,
        llm_port=port,
        context_provider=context_provider,
        structured_json_output=memory_reflection_structured_output_from_env(),
    )
    scheduler = SameProcessMemoryReflectionScheduler(processor)
    mode = memory_reflection_after_encode_filter_from_env()

    def after_subjective_episode_encoded(
        player_id: PlayerId, episode: SubjectiveEpisode
    ) -> None:
        if mode == "all" or (mode == "high" and episode.importance == "high"):
            scheduler.maybe_enqueue_after_subjective_encode(player_id, episode)

    hook: Optional[Callable[[PlayerId, SubjectiveEpisode], None]]
    if mode == "off":
        hook = None
    else:
        hook = after_subjective_episode_encoded

    return scheduler, hook
