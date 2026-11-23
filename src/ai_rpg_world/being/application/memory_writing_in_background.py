"""裏で書いているいきさつとエピソードを、その Being の記憶に入れる口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.being.domain.being_id import BeingId


class MemoryWritingInBackground(ABC):
    @abstractmethod
    def take_in_finished(self, being_id: BeingId) -> None:
        """書きかけは待たない。書き終わるまで出来事は短期記憶から外れないので、待たなくても見えるものは欠けない。"""

    @abstractmethod
    def finish(self, being_id: BeingId) -> bool:
        """書きかけを上限の時間まで待ってから入れ、書きかけが残らなかったかを返す。"""


__all__ = ["MemoryWritingInBackground"]
