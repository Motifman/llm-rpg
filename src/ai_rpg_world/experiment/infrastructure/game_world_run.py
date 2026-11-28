from __future__ import annotations

from pathlib import Path
from typing import Any

from typing_extensions import assert_never

from ai_rpg_world.being.domain.working_memory import Closing
from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from ai_rpg_world.experiment.infrastructure.game_world_play import GameWorldPlay, GameWorldPlayResult, GameWorldWriters
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings
from ai_rpg_world.experiment.infrastructure.murmuring_action_choosing import MurmuringActionChoosing
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.play_session.application.play_rounds import ChoosingKeptFailing, RoundLimitReached, WorldEnded

GAME_WORLD = "game_world"
CLOSING = Closing(instruction="利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。")


def prepare_game_world_play(
    *, scenario_path: Path, scenario_hash: str, settings: GameWorldPlaySettings, round_limit: int
) -> GameWorldPlay:
    return GameWorldPlay(
        scenario_path=scenario_path,
        scenario=load_scenario(scenario_path),
        scenario_hash=scenario_hash,
        settings=settings,
        writers=_stub_writers(),
        round_limit=round_limit,
        closing=CLOSING,
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
        "discarded_choices": discarded,
        "memory_writing_failures": dict(sorted(result.writing_failures.items())),
    }


def _stub_writers() -> GameWorldWriters:
    return GameWorldWriters(
        action_choosing=MurmuringActionChoosing(),
        episode_writer=ScriptedEpisodeWriter(),
        backstory_writer=ScriptedBackstoryWriter(),
    )
