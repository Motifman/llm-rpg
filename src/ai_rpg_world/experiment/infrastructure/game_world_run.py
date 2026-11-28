from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from typing_extensions import assert_never

from ai_rpg_world.application.llm.contracts.aux_llm_call import AuxLlmCall
from ai_rpg_world.application.llm.wiring._llm_client_factory import create_llm_client_from_config
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.being.infrastructure.llm_backstory_writer import LlmBackstoryWriter
from ai_rpg_world.being.infrastructure.llm_episode_writer import LlmEpisodeWriter
from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from ai_rpg_world.experiment.infrastructure.game_world_play import (
    AuxCallsForwarded,
    GameWorldPlay,
    GameWorldPlayResult,
    GameWorldWriters,
)
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import LITELLM, GameWorldPlaySettings
from ai_rpg_world.experiment.infrastructure.llm_call_capture import (
    CapturedEpisodeWriting,
    LlmCallCapture,
    captured_backstory_writing,
)
from ai_rpg_world.experiment.infrastructure.murmuring_action_choosing import MurmuringActionChoosing
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
from ai_rpg_world.play_session.application.play_rounds import ChoosingKeptFailing, RoundLimitReached, WorldEnded

GAME_WORLD = "game_world"


def prepare_game_world_play(
    *, scenario_path: Path, scenario_hash: str, settings: GameWorldPlaySettings, round_limit: int
) -> GameWorldPlay:
    capture = LlmCallCapture()
    return GameWorldPlay(
        scenario_path=scenario_path,
        scenario=load_scenario(scenario_path),
        scenario_hash=scenario_hash,
        settings=settings,
        writers=game_world_writers(settings, capture),
        round_limit=round_limit,
        capture=capture,
    )


def run_summary(result: GameWorldPlayResult) -> dict[str, Any]:
    reasons: list[str] | None = None
    discarded = 0
    match result.stopped:
        case WorldEnded():
            outcome = "WORLD_ENDED"
            discarded = len(result.stopped.discarded)
        case RoundLimitReached():
            outcome = "ROUND_LIMIT_REACHED"
        case ChoosingKeptFailing():
            outcome = "CHOOSING_KEPT_FAILING"
            reasons = list(result.stopped.reasons)
            discarded = len(result.stopped.discarded)
        case _:
            assert_never(result.stopped)
    return {
        "world": GAME_WORLD,
        "outcome": outcome,
        "stop_reasons": reasons,
        "last_tick": result.last_tick.value,
        "finished_turns": result.finished_turns,
        "failed_choices": list(result.failed_choices),
        "discarded_choices": discarded,
        "memory_writing_failures": dict(sorted(result.writing_failures.items())),
        "llm_calls_recorded": result.llm_calls_recorded,
        "llm_calls_not_recorded": result.llm_calls_not_recorded,
    }


def game_world_writers(settings: GameWorldPlaySettings, capture: LlmCallCapture) -> GameWorldWriters:
    if settings.llm_client != LITELLM:
        return GameWorldWriters(
            action_choosing=MurmuringActionChoosing(),
            episode_writer=ScriptedEpisodeWriter(),
            backstory_writer=ScriptedBackstoryWriter(),
        )
    config = ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_CLIENT": LITELLM, **settings.llm_values})
    aux_calls = AuxCallsForwarded()
    client = create_llm_client_from_config(config, aux_call_sink=aux_calls)
    if not isinstance(client, LiteLLMClient):
        raise RuntimeError(f"LLM_CLIENT=litellm built {type(client).__name__}")
    # キーが無いと、run を始めてから全員の選択と書き起こしが落ち続ける
    if not client.can_call():
        raise ValueError("OPENAI_API_KEY is not set. The game world needs it to call the LLM")
    return GameWorldWriters(
        action_choosing=client,
        episode_writer=LlmEpisodeWriter(CapturedEpisodeWriting(client, capture)),
        backstory_writer=LlmBackstoryWriter(captured_backstory_writing(client, capture)),
        aux_calls=aux_calls,
    )


def aux_call_payload(call: AuxLlmCall) -> dict[str, Any]:
    return {**dataclasses.asdict(call), "component": call.component.value}
