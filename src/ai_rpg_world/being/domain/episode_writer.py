"""出来事の並びから、Being 本人がエピソードの中身を書く口 (#1824、design_decisions D1824-13)。

文面と LLM の呼び出しと応答の読み取りはインフラが持つ。ID と呼び名を付けて記憶に加えるのは呼ぶ側。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ai_rpg_world.being.domain.episode import EpisodeIndex
from ai_rpg_world.being.domain.persona import Persona


@dataclass(frozen=True)
class EpisodeContent:
    """LLM が書いたエピソードの中身。ID も呼び名も持たない。

    ``truncated`` は切り詰めた項目 (応答の鍵の名前) と、切り詰める前の長さ。
    """

    index: EpisodeIndex
    body: str
    truncated: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EpisodeContents:
    """``dropped_count`` は 1 回に書ける件数を超えて捨てた中身の数。``rewritten`` は、崩れた応答のあとに書き直させた中身か。"""

    contents: tuple[EpisodeContent, ...]
    dropped_count: int = 0
    rewritten: bool = False


class EpisodeWriter(ABC):
    @abstractmethod
    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        """``events_text`` は【直近の出来事】と同じ書き方で古い順に並べた範囲。

        ``persona`` から名前と一人称を書き手に伝える。``persona_text`` は人格の文で、まだゲームの側の ``persona_prompt``
        から来る (#1339 / #1548 で ``Persona`` に移す)。

        書けなければ例外を投げる。崩れた応答からは 1 件も拾わない。中身の薄い記憶を混ぜないため。
        """


__all__ = ["EpisodeContent", "EpisodeContents", "EpisodeWriter"]
