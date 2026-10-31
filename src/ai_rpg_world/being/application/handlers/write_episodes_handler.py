"""短期記憶の範囲が埋まったとき、その範囲のエピソードを書いて記憶に加える (#1824、design_decisions D1824-19)。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory, AddEpisodesToMemoryCommand
from ai_rpg_world.being.application.write_episodes import WriteEpisodes, WriteEpisodesCommand
from ai_rpg_world.being.domain.episode_writer import EpisodeWriter
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRangeFilledEvent
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.eventing import AsyncEventHandler


@dataclass(frozen=True)
class EpisodeWritingCircumstances:
    """書き起こす本人の名前と人格の文と、いま居る環境の名前。"""

    self_name: str
    persona: str
    environment_name: str


class WriteEpisodesHandler(
    AsyncEventHandler[ShortTermMemoryRangeFilledEvent, WriteEpisodesCommand, AddEpisodesToMemoryCommand]
):
    """範囲が埋まったときだけ受ける。いきさつが遅れた (``ShortTermMemoryBackstoryOverdueEvent``) ときは受けない。同じ範囲のエピソードを 2 回書かないため (design_decisions D1824-11)。

    ``circumstances_of`` は、Being の ``Persona`` に移すまで (#1469)、ゲームの側がプレイヤーを走査して引く関数を渡す。
    保存先を走査するので、ターンを進めるスレッドで動く ``prepare`` で呼ぶ。
    """

    def __init__(
        self,
        *,
        writer: EpisodeWriter,
        add_episodes: AddEpisodesToMemory,
        circumstances_of: Callable[[BeingId], EpisodeWritingCircumstances],
    ) -> None:
        self._write = WriteEpisodes(writer)
        self._add = add_episodes
        self._circumstances_of = circumstances_of

    def prepare(self, event: ShortTermMemoryRangeFilledEvent) -> WriteEpisodesCommand:
        circumstances = self._circumstances_of(event.being_id)
        return WriteEpisodesCommand(
            being_id=event.being_id,
            self_name=circumstances.self_name,
            persona=circumstances.persona,
            experiences=event.experiences,
            environment_name=circumstances.environment_name,
            written_turn=event.turn,
        )

    def handle(self, command: WriteEpisodesCommand) -> AddEpisodesToMemoryCommand:
        return AddEpisodesToMemoryCommand(
            being_id=command.being_id,
            contents=self._write.execute(command),
            environment_name=command.environment_name,
            written_turn=command.written_turn,
        )

    def apply(self, result: AddEpisodesToMemoryCommand) -> None:
        self._add.add(result)


__all__ = ["EpisodeWritingCircumstances", "WriteEpisodesHandler"]
