"""Being がこのターンに頭に置いているものの一覧 (#1630)。

中身はそれぞれの持ち主 (短期記憶、メモ帳、エピソード、知り合い) と環境が持つ。作業記憶は
毎ターン組み直す値で、区画を書き換わりにくい順に並べることだけを受け持つ。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum

from ai_rpg_world.being.contract import Description, Orientation, Scene
from ai_rpg_world.domain.being.exception.being_exceptions import WorkingMemoryOrderException

#: システムプロンプトの冒頭の一文。
OPENING = "あなたは【ペルソナ】に書かれた人物として行動するキャラクターである。"
RECENT_EVENTS_PREAMBLE = "観測（世界から届いた事象）と、あなた自身の行動の結果が時系列に並びます。"
NO_RECENT_EVENTS = "（なし）"
GOAL_HEADING = "現在の目的"
KNOWN_PEOPLE_HEADING = "知っている人"
BACKSTORY_HEADING = "ここまでのいきさつ"
RECENT_EVENTS_HEADING = "直近の出来事"
EPISODE_INDEX_HEADING = "思い出せる出来事"
MEMO_HEADING = "メモ"


class Steadiness(IntEnum):
    """区画の書き換わりにくさ。値の小さいほうが書き換わりにくい。"""

    FIXED = 1
    """書き換わらない (冒頭の一文、作法)。"""
    ON_ENTRY = 2
    """入るときに決まる (案内、課された目的)。"""
    GROWING = 3
    """末尾に足していく (知っている人、いきさつ、直近の出来事)。いきさつは、直近の出来事の古い分が外れるときに一緒に変わる。"""
    OCCASIONAL = 4
    """ときどき置き換わる (目次、メモ)。"""
    EVERY_TURN = 5
    """毎ターン置き換わる (場面)。"""


@dataclass(frozen=True, kw_only=True)
class Section:
    """``heading`` が None の区画は見出しの行を持たない。"""

    heading: str | None
    lines: tuple[str, ...]
    steadiness: Steadiness


@dataclass(frozen=True, kw_only=True)
class Closing:
    """区画の外に置く、行動を選ばせる締めの一文。``warning`` は同じ手を続けたときに環境が添える一文。"""

    instruction: str
    warning: str | None = None


@dataclass(frozen=True, kw_only=True)
class MemoryTexts:
    """Being の記憶の持ち主がそれぞれ作った、区画の本文。空なら区画を出さない (直近の出来事を除く)。"""

    known_people: str = ""
    backstory: str = ""
    recent_events: str = ""
    episode_index: str = ""
    memo: str = ""


@dataclass(frozen=True, kw_only=True)
class WorkingMemory:
    """システムプロンプトと毎ターンのメッセージを別々の並びとして持ち、それぞれの中で書き換わりにくい順を守る。

    入るときまでに決まる区画 (FIXED と ON_ENTRY) はシステムプロンプトに、それより後に変わる区画は
    メッセージに置く。ターンをまたいでシステムプロンプトが変わらないので、キャッシュが切れない。
    ``notices`` (場面に付く知らせ) と ``closing`` は、メッセージの区画の後ろに付く。
    """

    system: tuple[Section, ...]
    message: tuple[Section, ...]
    notices: tuple[Section, ...] = field(default_factory=tuple)
    closing: Closing | None = None

    def __post_init__(self) -> None:
        for part, sections in (("system", self.system), ("message", self.message)):
            steadiness = [s.steadiness for s in sections]
            if steadiness != sorted(steadiness):
                raise WorkingMemoryOrderException(f"{part} sections must go from steadier to less steady: {steadiness}")
        if any(s.steadiness > Steadiness.ON_ENTRY for s in self.system):
            raise WorkingMemoryOrderException("system sections must be FIXED or ON_ENTRY")
        if any(s.steadiness <= Steadiness.ON_ENTRY for s in self.message):
            raise WorkingMemoryOrderException("message sections must change after entry (GROWING or later)")
        if any(n.steadiness is not Steadiness.EVERY_TURN for n in self.notices):
            raise WorkingMemoryOrderException("notices must be EVERY_TURN sections")

    @staticmethod
    def system_sections(orientation: Orientation, conduct: str, imposed_goal: str | None) -> tuple[Section, ...]:
        """システムプロンプトの区画。冒頭の一文、作法、案内、課された目的の順で、ターンをまたいで変わらない。

        ``conduct`` は Being の作法の文。見出しを持つ節が並んだ 1 つの区画にする。
        """
        return (
            Section(heading=None, lines=(OPENING,), steadiness=Steadiness.FIXED),
            Section(heading=None, lines=tuple(conduct.split("\n")), steadiness=Steadiness.FIXED),
            *_from_descriptions(orientation.descriptions, Steadiness.ON_ENTRY),
            *_present(((GOAL_HEADING, (imposed_goal or "").strip(), Steadiness.ON_ENTRY),)),
        )

    @classmethod
    def compose(
        cls,
        *,
        orientation: Orientation,
        conduct: str,
        imposed_goal: str | None,
        memory: MemoryTexts,
        scene: Scene,
        closing: Closing,
    ) -> WorkingMemory:
        system = cls.system_sections(orientation, conduct, imposed_goal)
        optional = (
            (KNOWN_PEOPLE_HEADING, memory.known_people.strip(), Steadiness.GROWING),
            (BACKSTORY_HEADING, memory.backstory.strip(), Steadiness.GROWING),
        )
        trailing = (
            (EPISODE_INDEX_HEADING, memory.episode_index.rstrip(), Steadiness.OCCASIONAL),
            (MEMO_HEADING, memory.memo.rstrip(), Steadiness.OCCASIONAL),
        )
        recent = Section(
            heading=RECENT_EVENTS_HEADING,
            lines=(RECENT_EVENTS_PREAMBLE, *(memory.recent_events.strip() or NO_RECENT_EVENTS).split("\n")),
            steadiness=Steadiness.GROWING,
        )
        message = (
            *_present(optional),
            recent,
            *_present(trailing),
            *_from_descriptions(scene.descriptions, Steadiness.EVERY_TURN),
        )
        return cls(
            system=system,
            message=message,
            notices=_from_descriptions(scene.notices, Steadiness.EVERY_TURN),
            closing=closing,
        )

    def with_scene(self, scene: Scene) -> WorkingMemory:
        """場面だけを差し替えた作業記憶。出すツールが決まって候補表が場面に入ったときに使う。"""
        steadier = tuple(s for s in self.message if s.steadiness is not Steadiness.EVERY_TURN)
        return WorkingMemory(
            system=self.system,
            message=(*steadier, *_from_descriptions(scene.descriptions, Steadiness.EVERY_TURN)),
            notices=_from_descriptions(scene.notices, Steadiness.EVERY_TURN),
            closing=self.closing,
        )

    def section(self, heading: str) -> Section | None:
        """システムプロンプトとメッセージの区画を見出しで引く。無ければ None。"""
        return next((s for s in (*self.system, *self.message) if s.heading == heading), None)


def _present(candidates: Sequence[tuple[str, str, Steadiness]]) -> tuple[Section, ...]:
    return tuple(
        Section(heading=heading, lines=tuple(text.split("\n")), steadiness=steadiness)
        for heading, text, steadiness in candidates
        if text.strip()
    )


def _from_descriptions(descriptions: Sequence[Description], steadiness: Steadiness) -> tuple[Section, ...]:
    return tuple(
        Section(heading=d.heading, lines=tuple(d.text.split("\n")), steadiness=steadiness) for d in descriptions
    )
