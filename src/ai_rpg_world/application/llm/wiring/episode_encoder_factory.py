"""Episode Encoder を LLM クライアントから組み立てる。"""

from __future__ import annotations

import os

from ai_rpg_world.application.llm.contracts.interfaces import IEpisodeEncoder, ILLMClient
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.llm_json_episode_encoder import LlmJsonEpisodeEncoder
from ai_rpg_world.application.llm.services.stub_episode_encoder import StubEpisodeEncoder
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
from ai_rpg_world.infrastructure.llm.litellm_episode_encoding_llm_port import (
    LiteLlmEpisodeEncodingLlmPort,
)

_ENV_EPISODE_ENCODING_JSON_SCHEMA = "EPISODE_ENCODING_JSON_SCHEMA"


def episode_encoding_structured_output_from_env() -> bool:
    """未設定時は ON（1）。`0` / `false` / `off` で structured output を切る。"""
    raw = (os.environ.get(_ENV_EPISODE_ENCODING_JSON_SCHEMA) or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def build_episode_encoder(llm_client: ILLMClient) -> IEpisodeEncoder:
    """stub クライアントなら StubEpisodeEncoder。LiteLLM なら LlmJsonEpisodeEncoder（既定で JSON Schema）。"""
    if isinstance(llm_client, StubLlmClient):
        return StubEpisodeEncoder()
    if isinstance(llm_client, LiteLLMClient):
        port = LiteLlmEpisodeEncodingLlmPort(llm_client)
        return LlmJsonEpisodeEncoder(
            port,
            structured_json_output=episode_encoding_structured_output_from_env(),
        )
    return StubEpisodeEncoder()
