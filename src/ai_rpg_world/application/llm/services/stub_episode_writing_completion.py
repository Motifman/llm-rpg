"""実 LLM を呼ばない run で、エピソードの書き起こしの配線と trace を確かめるためのスタブ。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.being.application.episode_writing import (
    EVENTS_HEADING,
    EpisodeWritingCompletion,
)

_EVENT_LINE_PREFIX = "- "


class StubEpisodeWritingCompletion(EpisodeWritingCompletion):
    """範囲の最初の出来事を本文にした 1 件を返す。"""

    def complete_episode_writing_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        events = messages[-1]["content"].split(EVENTS_HEADING, 1)[-1]
        first_event = next(
            (line for line in events.splitlines() if line.startswith(_EVENT_LINE_PREFIX)),
            "",
        ).removeprefix(_EVENT_LINE_PREFIX)
        return {
            "episodes": [
                {
                    "about": "(スタブ) 書き起こした記憶",
                    "recall_when": "(スタブ) いつでも",
                    "body": f"(スタブ) {first_event}",
                }
            ]
        }


__all__ = ["StubEpisodeWritingCompletion"]
