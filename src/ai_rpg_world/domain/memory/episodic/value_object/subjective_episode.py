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

from ai_rpg_world.domain.being.value_object.being_id import BeingId
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
    being_id: BeingId
    occurred_at: datetime
    game_time_label: str | None
    source: EpisodeSource
    location: EpisodeLocation
    action: EpisodeAction | None
    who: tuple[str, ...]
    what: str
    why: str | None
    observed: str
    expected: str | None
    outcome: str
    prediction_error: str | None
    felt: str | None
    interpreted: str | None
    cues: tuple[EpisodicCue, ...]
    recall_text: str | None = None
    recall_count: int = 0
    last_recalled_at: datetime | None = None
    # PR-M (約束清算の共在ゲート誤棄却の修正): who (= その chunk で実際に
    # structured.actor として動作した人) とは別に、chunk を閉じた時点で同じ
    # スポットに居た他プレイヤー名 (= 共在) を、エンジン由来の確定事実として
    # 保持する。who は「動いた人」しか集めないため、同席していても黙っている
    # 相手は who に入らず、約束清算の共在ゲートが fulfilled を誤棄却していた。
    # co_present を照合材料に加えることで「相手が黙っていても同席していれば
    # 清算を通す」ことができる。who と同じ正規化 (空文字拒否・tuple 検証) を
    # 持ち、既定は空タプル。既存の全構築箇所・snapshot 往復が co_present を
    # 意識せずに作っても壊れない後方互換を保つ。
    co_present: tuple[str, ...] = ()
    # 1 行見出し (#526 段階 3 後続)。読み手だった見出しの欄 (afterglow) は #1631 で
    # 消した。新規 LLM コールは
    # 増やさず、既存の主観文付与で interpreted / recall_text と同じ pass で
    # 書かせる方針のため、未指定や空文字も None として畳み込む Optional に保つ。
    heading: str | None = None
    # salience を判定する部品は消し、いまは常に "low"。保存形式に残っている
    # ので、古いエピソードを消すとき (#1631) に一緒に消す。
    salience: str = "low"

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str):
            raise TypeError("episode_id must be str")
        eid = self.episode_id.strip()
        if not eid:
            raise ValueError("episode_id must not be empty or whitespace-only")
        object.__setattr__(self, "episode_id", eid)

        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")

        if not isinstance(self.being_id, BeingId):
            raise TypeError("being_id must be BeingId")

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

        if not isinstance(self.co_present, tuple):
            raise TypeError("co_present must be tuple[str, ...]")
        co_present_norm: list[str] = []
        for idx, c in enumerate(self.co_present):
            co_present_norm.append(reject_blank(f"co_present[{idx}]", c))
        object.__setattr__(self, "co_present", tuple(co_present_norm))

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
        object.__setattr__(self, "heading", optional_non_blank("heading", self.heading))

        object.__setattr__(
            self,
            "game_time_label",
            optional_non_blank("game_time_label", self.game_time_label),
        )

        if not isinstance(self.cues, tuple):
            raise TypeError("cues must be tuple[EpisodicCue, ...]")
        for idx, cue in enumerate(self.cues):
            if not isinstance(cue, EpisodicCue):
                raise TypeError(f"cues[{idx}] must be EpisodicCue")

        if not isinstance(self.recall_count, int) or self.recall_count < 0:
            raise ValueError("recall_count must be int >= 0")
        if self.last_recalled_at is not None and not isinstance(self.last_recalled_at, datetime):
            raise TypeError("last_recalled_at must be datetime or None")

        if self.salience not in ("low", "high"):
            raise ValueError('salience must be "low" or "high"')


__all__ = ["SubjectiveEpisode"]
