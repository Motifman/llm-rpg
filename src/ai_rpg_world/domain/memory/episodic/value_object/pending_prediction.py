"""PendingPrediction / PendingPredictionDraft — 保留中の予測 (約束) VO。

U10a (予測誤差統一設計 部品6): 「木の下で会う約束」のように、結果がすぐに
出ない予測 (= 約束・遅延予測) を保持し、解決 cue (いつ / どこ / 誰) が
そろったときに再浮上させるための VO 2 種。

- ``PendingPredictionDraft``: chunk 主観補完 LLM が 1 chunk に対して抽出する
  「まだ pending_id / created_tick が確定していない」生の抽出結果。
  ``SubjectiveEpisode.pending_prediction_draft`` に一時的に載せて chunk
  完了点まで運ぶ (heading / salience と同じ「同じ pass に相乗りさせる」設計)。
- ``PendingPrediction``: chunk 完了点で draft から起こす、per-Being store に
  実際に保持する確定版。``pending_id`` / ``origin_episode_id`` / ``created_tick``
  が確定している。

## tick_offset と tick_from/tick_to の関係

chunk 主観補完 LLM には「現在の絶対 tick」が渡っていない (プロンプトには
occurred_at / game_time_label はあるが tick 整数は無い)。そのため LLM には
「今から何 tick 後に解決が見込まれるか」という **相対オフセット**
(``tick_offset_from`` / ``tick_offset_to``) だけを書かせ、chunk 完了点
(= 実際の現在 tick が分かる場所) で ``created_tick`` を足して絶対 tick
範囲 (``tick_from`` / ``tick_to``) に変換する。「夕方」のような自然言語時刻を
tick へ写像する語彙は本 PR (U10a) のスコープ外 (計画書の不確実性 (b) 参照)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.memory.episodic.exception.episodic_exception import (
    PendingPredictionValidationException,
)

_VALID_CUE_PREFIXES = ("spot:", "player:")


def _validate_resolution_cues(cues: Tuple[str, ...]) -> Tuple[str, ...]:
    """resolution_cues の形式を検証し、正規化した tuple を返す。

    各要素は ``"spot:<spot_id>"`` または ``"player:<相手の名前>"`` の
    いずれかの形式で、1 件以上必要 (解決条件の無い pending prediction は
    絶対に再浮上しないので意味を持たない)。
    """
    if not isinstance(cues, tuple):
        raise PendingPredictionValidationException(
            "resolution_cues must be tuple[str, ...]",
            field="resolution_cues",
            value=cues,
        )
    if not cues:
        raise PendingPredictionValidationException(
            "resolution_cues must not be empty (a pending prediction must "
            "have at least one resolution condition)",
            field="resolution_cues",
        )
    normalized: list[str] = []
    for idx, cue in enumerate(cues):
        if not isinstance(cue, str) or not cue.strip():
            raise PendingPredictionValidationException(
                f"resolution_cues[{idx}] must be non-empty str",
                field="resolution_cues",
                index=idx,
            )
        stripped = cue.strip()
        prefix = next((p for p in _VALID_CUE_PREFIXES if stripped.startswith(p)), None)
        if prefix is None or not stripped[len(prefix):].strip():
            raise PendingPredictionValidationException(
                f"resolution_cues[{idx}] must start with one of "
                f"{_VALID_CUE_PREFIXES} and have a non-empty suffix, "
                f"got {cue!r}",
                field="resolution_cues",
                index=idx,
                value=cue,
            )
        normalized.append(stripped)
    return tuple(normalized)


def _validate_tick_range(
    *, tick_from: int, tick_to: int, from_field: str, to_field: str
) -> None:
    if not isinstance(tick_from, int) or isinstance(tick_from, bool):
        raise PendingPredictionValidationException(
            f"{from_field} must be int", field=from_field, value=tick_from
        )
    if not isinstance(tick_to, int) or isinstance(tick_to, bool):
        raise PendingPredictionValidationException(
            f"{to_field} must be int", field=to_field, value=tick_to
        )
    if tick_from < 0:
        raise PendingPredictionValidationException(
            f"{from_field} must be >= 0", field=from_field, value=tick_from
        )
    if tick_to < tick_from:
        raise PendingPredictionValidationException(
            f"{to_field} must be >= {from_field}",
            field=to_field,
            value=tick_to,
        )


@dataclass(frozen=True)
class PendingPredictionDraft:
    """chunk 主観補完 LLM が抽出した、未確定の pending prediction 1 件分。"""

    text: str
    resolution_cues: Tuple[str, ...]
    tick_offset_from: int
    tick_offset_to: int

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise PendingPredictionValidationException(
                "text must be non-empty str", field="text", value=self.text
            )
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(
            self, "resolution_cues", _validate_resolution_cues(self.resolution_cues)
        )
        _validate_tick_range(
            tick_from=self.tick_offset_from,
            tick_to=self.tick_offset_to,
            from_field="tick_offset_from",
            to_field="tick_offset_to",
        )


@dataclass(frozen=True)
class PendingPrediction:
    """per-Being store に保持する、確定版の pending prediction 1 件分。"""

    pending_id: str
    text: str
    resolution_cues: Tuple[str, ...]
    tick_from: int
    tick_to: int
    origin_episode_id: str
    created_tick: int

    def __post_init__(self) -> None:
        if not isinstance(self.pending_id, str) or not self.pending_id.strip():
            raise PendingPredictionValidationException(
                "pending_id must be non-empty str",
                field="pending_id",
                value=self.pending_id,
            )
        object.__setattr__(self, "pending_id", self.pending_id.strip())

        if not isinstance(self.text, str) or not self.text.strip():
            raise PendingPredictionValidationException(
                "text must be non-empty str", field="text", value=self.text
            )
        object.__setattr__(self, "text", self.text.strip())

        object.__setattr__(
            self, "resolution_cues", _validate_resolution_cues(self.resolution_cues)
        )

        if not isinstance(self.origin_episode_id, str) or not self.origin_episode_id.strip():
            raise PendingPredictionValidationException(
                "origin_episode_id must be non-empty str",
                field="origin_episode_id",
                value=self.origin_episode_id,
            )
        object.__setattr__(self, "origin_episode_id", self.origin_episode_id.strip())

        if not isinstance(self.created_tick, int) or isinstance(self.created_tick, bool):
            raise PendingPredictionValidationException(
                "created_tick must be int",
                field="created_tick",
                value=self.created_tick,
            )
        if self.created_tick < 0:
            raise PendingPredictionValidationException(
                "created_tick must be >= 0",
                field="created_tick",
                value=self.created_tick,
            )

        _validate_tick_range(
            tick_from=self.tick_from,
            tick_to=self.tick_to,
            from_field="tick_from",
            to_field="tick_to",
        )


__all__ = ["PendingPrediction", "PendingPredictionDraft"]
