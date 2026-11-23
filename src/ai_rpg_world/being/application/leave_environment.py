"""環境を離れるとき、裏の書き起こしを待ち、まだまとめていない出来事もエピソードにする (#2271)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.application.memory_writing_in_background import MemoryWritingInBackground
from ai_rpg_world.being.application.write_episodes_on_leaving import (
    EpisodesOnLeaving,
    WriteEpisodesOnLeaving,
    WriteEpisodesOnLeavingCommand,
)
from ai_rpg_world.being.application.writing_circumstances import CircumstancesOfBeings
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader


@dataclass(frozen=True)
class LeaveEnvironmentCommand:
    being_id: BeingId


@dataclass(frozen=True)
class EnvironmentLeft:
    """``background_finished`` が False なら、上限の時間までに書き終わらなかった書き起こしがあった。"""

    background_finished: bool
    episodes: EpisodesOnLeaving


class LeaveEnvironment:
    def __init__(
        self,
        *,
        writing_in_background: MemoryWritingInBackground,
        write_episodes: WriteEpisodesOnLeaving,
        circumstances: CircumstancesOfBeings,
        turn_reader: MemoryTurnReader,
    ) -> None:
        self._writing_in_background = writing_in_background
        self._write_episodes = write_episodes
        self._circumstances = circumstances
        self._turn_reader = turn_reader

    def execute(self, command: LeaveEnvironmentCommand) -> EnvironmentLeft:
        being_id = command.being_id
        # 裏で書いた範囲が記憶に入ってから残りを書く。先に書くと、裏の範囲と残りの境目がずれる
        finished = self._writing_in_background.finish(being_id)
        circumstances = self._circumstances.circumstances_of(being_id)
        episodes = self._write_episodes.execute(
            WriteEpisodesOnLeavingCommand(
                being_id=being_id,
                persona=self._circumstances.persona_of(being_id),
                persona_text=circumstances.persona_text,
                environment_name=circumstances.environment_name,
                written_turn=self._turn_reader.current_turn(being_id),
            )
        )
        return EnvironmentLeft(background_finished=finished, episodes=episodes)


__all__ = ["EnvironmentLeft", "LeaveEnvironment", "LeaveEnvironmentCommand"]
