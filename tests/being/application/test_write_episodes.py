from __future__ import annotations

from ai_rpg_world.being.application.write_episodes import WriteEpisodes, WriteEpisodesCommand
from ai_rpg_world.being.contract import UNKNOWN, AgentMove, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.episode import EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeContent, EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import Attempt, Perception
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_p1")
CONTENTS = EpisodeContents(
    contents=(
        EpisodeContent(index=EpisodeIndex(summary="鐘の記憶", recall_when="鐘の話が出たとき"), body="鐘が鳴った。"),
    )
)


def _seen(turn: int, body: str) -> Perception:
    observation = Observation(
        body=body,
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )
    return Perception(turn=turn, observation=observation)


class _Writer(EpisodeWriter):
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        self.calls.append({"persona": persona, "persona_text": persona_text, "events_text": events_text})
        return CONTENTS


def _command(*experiences: object) -> WriteEpisodesCommand:
    return WriteEpisodesCommand(
        being_id=ADA,
        persona=Persona(name="エイダ"),
        persona_text="慎重",
        experiences=experiences,  # type: ignore[arg-type]
        environment_name="廃坑の山村",
        written_turn=20,
    )


class TestWriteEpisodes:
    """WriteEpisodes が、まとめる出来事を【直近の出来事】と同じ行にしてエピソードの中身を書くことを保証する。"""

    def test_experiences_are_written_as_lines_with_name_and_persona(self) -> None:
        """出来事を【直近の出来事】と同じ行にして、名前と人格の文とともに書き手に渡し、書き手が返した中身を返す。"""
        writer = _Writer()

        contents = WriteEpisodes(writer).execute(_command(_seen(1, "鐘が鳴った"), _seen(2, "扉が開いた")))

        assert writer.calls == [
            {
                "persona": Persona(name="エイダ"),
                "persona_text": "慎重",
                "events_text": "- [1日目 朝] 鐘が鳴った\n- [1日目 朝] 扉が開いた",
            }
        ]
        assert contents == CONTENTS

    def test_range_without_lines_is_not_written(self) -> None:
        """出来事が結果の来ない 1 手だけで行にならなければ、書き手を呼ばず、中身の無い EpisodeContents を返す。"""
        writer = _Writer()

        contents = WriteEpisodes(writer).execute(
            _command(Attempt(turn=1, move=AgentMove(call_id="call-1", tool_name="interact", arguments={})))
        )

        assert (writer.calls, contents) == ([], EpisodeContents(contents=()))
