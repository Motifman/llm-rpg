"""SubjectiveEpisode — 主観エピソード記憶 MVP 形。

DDD 再編 (Issue #470 Phase 1 PR2): 元 ``application/llm/contracts/episodic_memory.py``
から domain に昇格。

`observed` と `EpisodeSource.event_ids` はソース・オブ・トゥルース側の不変参照
として扱う (= 後続処理で書き換えない)。

TODO (Issue #470 Phase 2):
    `recall_count` / `last_recalled_at` / `recall_text` / `interpreted` は
    `dataclasses.replace()` で更新される **ライフサイクル field**。frozen VO 内に
    抱えているが、概念上は集約 root であり、Phase 2 で
    ``domain/memory/episodic/aggregate/`` への昇格を検討する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

from ai_rpg_world.domain.memory.episodic.value_object._validators import (
    optional_non_blank,
    reject_blank,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import (
    EpisodeAction,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
    EpisodeLocation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import (
    EpisodeSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import (
    EpisodicCue,
)


@dataclass(frozen=True)
class SubjectiveEpisode:
    """主観エピソード記憶の MVP 形。

    `observed` と `EpisodeSource.event_ids` はソース・オブ・トゥルース側の
    不変参照として扱う。
    """

    episode_id: str
    player_id: int
    occurred_at: datetime
    game_time_label: str | None
    source: EpisodeSource
    location: EpisodeLocation
    action: EpisodeAction | None
    who: Tuple[str, ...]
    what: str
    why: str | None
    observed: str
    expected: str | None
    outcome: str
    prediction_error: str | None
    felt: str | None
    interpreted: str | None
    cues: Tuple[EpisodicCue, ...]
    recall_text: str | None = None
    recall_count: int = 0
    last_recalled_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str):
            raise TypeError("episode_id must be str")
        eid = self.episode_id.strip()
        if not eid:
            raise ValueError("episode_id must not be empty or whitespace-only")
        object.__setattr__(self, "episode_id", eid)

        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")

        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")

        if not isinstance(self.source, EpisodeSource):
            raise TypeError("source must be EpisodeSource")
        if not isinstance(self.location, EpisodeLocation):
            raise TypeError("location must be EpisodeLocation")
        if self.action is not None and not isinstance(self.action, EpisodeAction):
            raise TypeError("action must be EpisodeAction or None")

        if not isinstance(self.who, tuple):
            raise TypeError("who must be tuple[str, ...]")
        who_norm: list[str] = []
        for idx, w in enumerate(self.who):
            who_norm.append(reject_blank(f"who[{idx}]", w))
        object.__setattr__(self, "who", tuple(who_norm))

        object.__setattr__(self, "what", reject_blank("what", self.what))
        object.__setattr__(self, "why", optional_non_blank("why", self.why))
        object.__setattr__(self, "observed", reject_blank("observed", self.observed))
        object.__setattr__(self, "expected", optional_non_blank("expected", self.expected))
        object.__setattr__(self, "outcome", reject_blank("outcome", self.outcome))
        object.__setattr__(
            self, "prediction_error", optional_non_blank("prediction_error", self.prediction_error)
        )
        object.__setattr__(self, "felt", optional_non_blank("felt", self.felt))
        object.__setattr__(self, "interpreted", optional_non_blank("interpreted", self.interpreted))
        object.__setattr__(self, "recall_text", optional_non_blank("recall_text", self.recall_text))

        object.__setattr__(
            self,
            "game_time_label",
            optional_non_blank("game_time_label", self.game_time_label),
        )

        if not isinstance(self.cues, tuple):
            raise TypeError("cues must be tuple[EpisodicCue, ...]")
        for idx, c in enumerate(self.cues):
            if not isinstance(c, EpisodicCue):
                raise TypeError(f"cues[{idx}] must be EpisodicCue")

        if not isinstance(self.recall_count, int) or self.recall_count < 0:
            raise ValueError("recall_count must be int >= 0")
        if self.last_recalled_at is not None and not isinstance(self.last_recalled_at, datetime):
            raise TypeError("last_recalled_at must be datetime or None")


__all__ = ["SubjectiveEpisode"]
