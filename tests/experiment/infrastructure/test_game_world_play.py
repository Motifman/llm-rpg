from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

from ai_rpg_world.being.application.choose_action import ActionChoosingReply
from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from ai_rpg_world.experiment.infrastructure.game_world_play import GameWorldPlay, GameWorldWriters
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings
from ai_rpg_world.experiment.infrastructure.game_world_run import CLOSING
from ai_rpg_world.experiment.infrastructure.murmuring_action_choosing import MurmuringActionChoosing
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.play_session.application.play_rounds import RoundLimitReached

_MINE_VILLAGE_V2 = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"


class _RecordingMurmurs(MurmuringActionChoosing):
    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []
        self._prompts_lock = threading.Lock()

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        with self._prompts_lock:
            self.prompts.append(messages[-1]["content"])
        return super().choose_action(messages, tools, reasoning_off=reasoning_off)


def _play(completion: MurmuringActionChoosing, *, round_limit: int) -> GameWorldPlay:
    return GameWorldPlay(
        scenario_path=_MINE_VILLAGE_V2,
        scenario=load_scenario(_MINE_VILLAGE_V2),
        scenario_hash=hashlib.sha256(_MINE_VILLAGE_V2.read_bytes()).hexdigest(),
        settings=GameWorldPlaySettings(),
        writers=GameWorldWriters(
            action_choosing=completion,
            episode_writer=ScriptedEpisodeWriter(),
            backstory_writer=ScriptedBackstoryWriter(),
        ),
        round_limit=round_limit,
        closing=CLOSING,
    )


class TestGameWorldPlay:
    """GameWorldPlay が、本番の部品で廃坑の山村 v2 を組み、世界で起きたことを Being の次の場面まで届けることを保証する。"""

    def test_what_someone_said_reaches_the_others_next_prompt(self) -> None:
        """1 巡り目に全員がふつうの声で「ふむ」と言うと、2 巡り目のだれかのプロンプトの【直近の出来事】に、ほかの人の「ふむ」が届いている。"""
        completion = _RecordingMurmurs()

        result = _play(completion, round_limit=2).play()

        assert isinstance(result.stopped, RoundLimitReached)
        second_round = completion.prompts[4:]
        assert any("が「ふむ」と言った。" in prompt for prompt in second_round)

    def test_last_tick_and_turns_are_counted_after_the_play(self) -> None:
        """2 巡り回すと、最後の tick は 2 で、4 人ぶん 8 ターンを終えたと数える。"""
        result = _play(MurmuringActionChoosing(), round_limit=2).play()

        assert (result.last_tick.value, result.finished_turns) == (2, 8)
