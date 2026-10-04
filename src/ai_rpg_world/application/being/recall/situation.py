"""想起の手がかりにする、いまの状況の 6 つの項目 (#1414)。

項目の値は名前や文で持つ。世界状態への照会、ゲームの ID、tags、cue は入れない。
環境から受け取る観測の契約とエージェント自身が持つものから組むので、環境を替えても使える。

全部の項目をつなげて 1 本で問い合わせる (design_decisions D1414-8)。項目を選んで
引く形は、確かめた 40 場面で全部の項目で引いた結果とほとんど変わらなかったので外した。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SituationField(Enum):
    """並び順が問い合わせ文の項目の順になる。"""

    PLACE = "場所"
    COUNTERPART = "相手"
    OWN_STATE = "自分の状態"
    INTENT = "やろうとしていること"
    HAPPENING = "いま起きたこと"
    UNRESOLVED = "未解決のこと"


@dataclass(frozen=True)
class Situation:
    place: tuple[str, ...] = ()
    counterpart: tuple[str, ...] = ()
    own_state: tuple[str, ...] = ()
    intent: tuple[str, ...] = ()
    happening: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in SituationField:
            texts = self.texts(field)
            if not isinstance(texts, tuple):
                raise TypeError(f"{field.name.lower()} must be tuple[str, ...]")
            for text in texts:
                if not isinstance(text, str):
                    raise TypeError(f"{field.name.lower()} must be tuple[str, ...]")
                if not text.strip():
                    raise ValueError(f"{field.name.lower()} must not contain empty text")

    def texts(self, field: SituationField) -> tuple[str, ...]:
        texts: tuple[str, ...] = getattr(self, field.name.lower())
        return texts

    def query(self) -> str:
        """全部の項目の値を、項目の決まった順に改行でつなぐ。

        改行は検索の 2 字組の区切りになるので、別々の値の境目に無い言葉は生まれない
        (design_decisions D1414-7)。
        """
        return "\n".join(text for field in SituationField for text in self.texts(field))


__all__ = ["Situation", "SituationField"]
