"""出来事の並びから、Being 本人がエピソードの下書きを書く口 (#1824、design_decisions D1824-13)。

文面と LLM の呼び出しと応答の読み取りはインフラが持つ。ID と呼び名を付けて保存するのは呼ぶ側。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ai_rpg_world.being.domain.episode import EpisodeIndex


@dataclass(frozen=True)
class EpisodeDraft:
    """``truncated`` は切り詰めた項目 (応答の鍵の名前) と、切り詰める前の長さ。"""

    index: EpisodeIndex
    body: str
    truncated: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EpisodeDrafts:
    """``dropped_count`` は 1 回に書ける件数を超えて捨てた下書きの数。"""

    drafts: tuple[EpisodeDraft, ...]
    dropped_count: int = 0


class EpisodeWriter(ABC):
    @abstractmethod
    def write(self, *, self_name: str, persona: str, events_text: str) -> EpisodeDrafts:
        """``events_text`` は【直近の出来事】と同じ書き方で古い順に並べた範囲。

        書けなければ例外を投げる。応答が崩れていれば 1 件も返さない。中身の薄い記憶を混ぜないため。
        """


__all__ = ["EpisodeDraft", "EpisodeDrafts", "EpisodeWriter"]
