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
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPredictionDraft,
    PendingResolutionVerdict,
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
    # Afterglow index で使う 1 行見出し (#526 段階 3 後続)。新規 LLM コールは
    # 増やさず、既存の主観文付与で interpreted / recall_text と同じ pass で
    # 書かせる方針のため、未指定や空文字も None として畳み込む Optional に保つ。
    heading: str | None = None
    # U6 (予測誤差統一設計 / salience + STRUCTURED_FAILURE): 「このキャラに
    # とって予測が大きく外れた / 初めての重大事」かどうかを chunk 主観補完
    # LLM が一度だけ判定するフィールド。heading と同じく既存の主観文付与
    # pass に相乗りさせ、新規 LLM コールは増やさない。heading と違って
    # 「値が無い」状態は表現しない (常に low/high のどちらか) ため、Optional
    # ではなく既定値 "low" を持つ必須フィールドにする。
    salience: str = "low"
    # U10a (予測誤差統一設計 部品6・pending prediction): chunk 主観補完 LLM が
    # 「この chunk に将来の約束・見込みが含まれるか」を判定した抽出結果。
    # heading / salience と同じく既存の主観文付与 pass に相乗りさせ、新規
    # LLM コールは増やさない。**一時的なスクラッチフィールド**であり、chunk
    # 完了点 (EpisodicChunkCoordinator 等) で PendingPrediction 化して
    # per-Being store に書き込んだ後は用済みになる。そのため
    # ``_memory_payload_codecs.subjective_episode_to_dict`` / snapshot には
    # 含めない (= episode の snapshot 復元では常に None に戻る。既に消費済の
    # 抽出結果を再現する必要が無いため)。
    pending_prediction_draft: PendingPredictionDraft | None = None
    # U10b (予測誤差統一設計 部品6・pending prediction 清算): chunk 主観補完 LLM
    # が「再浮上中の約束のうち果たされた / 破られたもの」を判定した結果。
    # pending_prediction_draft と同じく **一時的なスクラッチフィールド** で、
    # chunk 完了点で PENDING_RESOLUTION evidence に転記し store から除いた後は
    # 用済みになる。snapshot / codec には含めない (復元時は常に空タプル)。
    pending_resolution_verdicts: Tuple[PendingResolutionVerdict, ...] = ()

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
        object.__setattr__(self, "heading", optional_non_blank("heading", self.heading))

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

        if self.salience not in ("low", "high"):
            raise ValueError('salience must be "low" or "high"')

        if self.pending_prediction_draft is not None and not isinstance(
            self.pending_prediction_draft, PendingPredictionDraft
        ):
            raise TypeError("pending_prediction_draft must be PendingPredictionDraft or None")

        if not isinstance(self.pending_resolution_verdicts, tuple):
            raise TypeError("pending_resolution_verdicts must be tuple[PendingResolutionVerdict, ...]")
        for idx, v in enumerate(self.pending_resolution_verdicts):
            if not isinstance(v, PendingResolutionVerdict):
                raise TypeError(
                    f"pending_resolution_verdicts[{idx}] must be PendingResolutionVerdict"
                )


__all__ = ["SubjectiveEpisode"]
