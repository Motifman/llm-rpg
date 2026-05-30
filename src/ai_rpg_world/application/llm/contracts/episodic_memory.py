"""MVP 用エピソード記憶の契約型（ルール由来・決定論的 cue を前提とする）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Tuple


def _reject_blank(field_label: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_label} must be str")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_label} must not be empty or whitespace-only")
    return stripped


def _optional_non_blank(field_label: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_label} must be str or None")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_label} must be None or a non-empty str; blank strings are rejected")
    return stripped


class EpisodicCueSource(str, Enum):
    """cue がゲーム構造化入力から付いたことを示す（LLM 自由生成ではない）。"""

    RUNTIME_CONTEXT = "runtime_context"
    TOOL = "tool"
    OBSERVATION_STRUCTURED = "observation_structured"
    # Issue #283 後続: 観測 prose を WorldNounMatcher で走査し、含まれる固有名詞
    # から自動付与された cue (例: SNS で「書架A」と言及されると place_spot:3 が立つ)。
    # 構造化されていない自由文経由なので別 source として区別する。
    OBSERVATION_FREETEXT = "observation_freetext"


@dataclass(frozen=True)
class EpisodicCue:
    """
    型付き想起手がかり。canonical は索引・マッチ用の安定キー（axis:value）。
    """

    axis: str
    value: str
    source: EpisodicCueSource

    def __post_init__(self) -> None:
        if not isinstance(self.source, EpisodicCueSource):
            raise TypeError("source must be EpisodicCueSource")
        axis_stripped = _reject_blank("axis", self.axis)
        value_stripped = _reject_blank("value", self.value)
        if ":" in axis_stripped:
            raise ValueError("axis must not contain ':'")
        object.__setattr__(self, "axis", axis_stripped.lower())
        object.__setattr__(self, "value", value_stripped)

    def to_canonical(self) -> str:
        return f"{self.axis}:{self.value}"


@dataclass(frozen=True)
class EpisodeSource:
    """
    エピソードの材料となったイベント ID の参照集合。
    不変フィールドとして扱い、後続処理で書き換えないことを前提とする。
    MVP では追跡可能性のため event_ids は最低 1 件必須。
    """

    event_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.event_ids, tuple):
            raise TypeError("event_ids must be a tuple[str, ...]")
        if len(self.event_ids) == 0:
            raise ValueError("event_ids must contain at least one id")
        normalized: list[str] = []
        for idx, raw in enumerate(self.event_ids):
            if not isinstance(raw, str):
                raise TypeError(f"event_ids[{idx}] must be str")
            rid = raw.strip()
            if not rid:
                raise ValueError(f"event_ids[{idx}] must not be empty or whitespace-only")
            normalized.append(rid)
        object.__setattr__(self, "event_ids", tuple(normalized))


@dataclass(frozen=True)
class EpisodeLocation:
    """構造化された「どこで」（タイル／スポットグラフ双方を許容）。"""

    spot_id: int | None = None
    tile_area_ids: Tuple[int, ...] = ()
    sub_location_id: int | None = None
    x: int | None = None
    y: int | None = None
    z: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tile_area_ids, tuple):
            raise TypeError("tile_area_ids must be tuple[int, ...]")
        for idx, aid in enumerate(self.tile_area_ids):
            if not isinstance(aid, int):
                raise TypeError(f"tile_area_ids[{idx}] must be int")
        for name, val in (
            ("spot_id", self.spot_id),
            ("sub_location_id", self.sub_location_id),
            ("x", self.x),
            ("y", self.y),
            ("z", self.z),
        ):
            if val is not None and not isinstance(val, int):
                raise TypeError(f"{name} must be int or None")


@dataclass(frozen=True)
class EpisodeAction:
    """どう行動したか（ツール名と正規化済み引数の要約）。"""

    tool_name: str
    canonical_arguments_text: str | None = None

    def __post_init__(self) -> None:
        tn = _reject_blank("tool_name", self.tool_name)
        object.__setattr__(self, "tool_name", tn)
        cat = _optional_non_blank("canonical_arguments_text", self.canonical_arguments_text)
        object.__setattr__(self, "canonical_arguments_text", cat)


@dataclass(frozen=True)
class SubjectiveEpisode:
    """
    主観エピソード記憶の MVP 形。
    observed と EpisodeSource.event_ids はソース・オブ・トゥルース側の不変参照として扱う。
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
            who_norm.append(_reject_blank(f"who[{idx}]", w))
        object.__setattr__(self, "who", tuple(who_norm))

        object.__setattr__(self, "what", _reject_blank("what", self.what))
        object.__setattr__(self, "why", _optional_non_blank("why", self.why))
        object.__setattr__(self, "observed", _reject_blank("observed", self.observed))
        object.__setattr__(self, "expected", _optional_non_blank("expected", self.expected))
        object.__setattr__(self, "outcome", _reject_blank("outcome", self.outcome))
        object.__setattr__(self, "prediction_error", _optional_non_blank("prediction_error", self.prediction_error))
        object.__setattr__(self, "felt", _optional_non_blank("felt", self.felt))
        object.__setattr__(self, "interpreted", _optional_non_blank("interpreted", self.interpreted))
        object.__setattr__(self, "recall_text", _optional_non_blank("recall_text", self.recall_text))

        if self.game_time_label is not None:
            if not isinstance(self.game_time_label, str):
                raise TypeError("game_time_label must be str or None")
            gl = self.game_time_label.strip()
            if not gl:
                raise ValueError("game_time_label must be None or non-empty after strip")
            object.__setattr__(self, "game_time_label", gl)

        if not isinstance(self.cues, tuple):
            raise TypeError("cues must be tuple[EpisodicCue, ...]")
        for idx, c in enumerate(self.cues):
            if not isinstance(c, EpisodicCue):
                raise TypeError(f"cues[{idx}] must be EpisodicCue")

        if not isinstance(self.recall_count, int) or self.recall_count < 0:
            raise ValueError("recall_count must be int >= 0")
        if self.last_recalled_at is not None and not isinstance(self.last_recalled_at, datetime):
            raise TypeError("last_recalled_at must be datetime or None")
