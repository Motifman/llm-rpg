"""直近の範囲から外す出来事を、ここまでのいきさつにまとめる、ドメインに置く抽象クラス (#1824、design_decisions D1824-11)。

文面と LLM の呼び出しと応答の読み取りはインフラが持つ。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ai_rpg_world.being.domain.short_term_memory import Backstory, Experience


@dataclass(frozen=True)
class WrittenBackstory:
    """書いたいきさつと、上限を超えて切り詰めた項目 (``flow`` / ``mood``) と切り詰める前の長さ。"""

    backstory: Backstory
    truncated: dict[str, int] = field(default_factory=dict)


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
    ) -> WrittenBackstory:
        """``experiences`` (``until_turn`` までの出来事、``recent()`` と同じ順) を、``previous`` に続くいきさつにまとめる。

        書けなければ例外を投げる。短期記憶はいきさつを待ち続け、遅れたら知らせるので、書き直される。
        """


__all__ = ["BackstoryWriter", "WrittenBackstory"]
