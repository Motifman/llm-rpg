"""直近の範囲から外す出来事を、ここまでのいきさつにまとめる口 (#1824、design_decisions D1824-11)。

文面と LLM の呼び出しと応答の読み取りはインフラが持つ。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.being.domain.short_term_memory import Backstory, Experience


class BackstoryWriter(ABC):
    @abstractmethod
    def write(
        self,
        *,
        self_name: str,
        persona: str,
        experiences: tuple[Experience, ...],
        previous: Backstory | None,
        until_turn: int,
        written_turn: int,
    ) -> Backstory:
        """``experiences`` (``until_turn`` までの出来事、``recent()`` と同じ順) を、``previous`` に続くいきさつにまとめる。

        書けなければ例外を投げる。頼みごとは残るので、短期記憶が頼み直す。
        """


__all__ = ["BackstoryWriter"]
