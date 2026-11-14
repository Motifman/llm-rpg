"""game_world のドメインイベントの種類が、刺激への変換か、知覚に出さない一覧のどちらか一方に必ず振り分けられていることを見張る。

知覚に出さない一覧 (NOT_PERCEIVED_EVENT_KINDS) に入れた種類は、誰にも知覚されない。
新しいイベントを足したら、変換を書くか、知覚に出さないと決めて一覧に入れる。
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator

import ai_rpg_world.game_world as game_world
from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.stimulus_translator import NOT_PERCEIVED_EVENT_KINDS, StimulusTranslator
from ai_rpg_world.game_world.domain.whereabouts import OccupantEnteredSpotEvent
from ai_rpg_world.game_world.domain.world_records import PersonActedEvent


def _subclasses(kind: type[DomainEvent]) -> Iterator[type[DomainEvent]]:
    for subclass in kind.__subclasses__():
        yield subclass
        yield from _subclasses(subclass)


def _game_world_event_kinds() -> frozenset[type[DomainEvent]]:
    for module in pkgutil.walk_packages(game_world.__path__, game_world.__name__ + "."):
        importlib.import_module(module.name)
    # PersonVitalsEvent のような共通の親は出されないので、子を持たない種類だけを数える。
    return frozenset(
        kind
        for kind in _subclasses(DomainEvent)
        if kind.__module__.startswith(game_world.__name__ + ".") and not kind.__subclasses__()
    )


def _names(kinds: frozenset[type[DomainEvent]]) -> list[str]:
    return sorted(kind.__name__ for kind in kinds)


def test_collecting_finds_event_kinds_of_every_layer_of_the_world() -> None:
    """数え上げは、居場所の OccupantEnteredSpotEvent と行為の記録の PersonActedEvent を見つける。"""
    kinds = _game_world_event_kinds()

    assert {OccupantEnteredSpotEvent, PersonActedEvent} <= kinds


def test_every_event_kind_is_translated_or_listed_as_not_perceived() -> None:
    """game_world のどのドメインイベントの種類も、変換か、知覚に出さない一覧のどちらかにある。"""
    unclassified = _game_world_event_kinds() - StimulusTranslator.translated_kinds() - NOT_PERCEIVED_EVENT_KINDS

    assert _names(unclassified) == []


def test_no_event_kind_is_both_translated_and_listed_as_not_perceived() -> None:
    """変換のある種類を、知覚に出さない一覧にも入れていない。"""
    assert _names(StimulusTranslator.translated_kinds() & NOT_PERCEIVED_EVENT_KINDS) == []


def test_every_classified_kind_is_an_event_kind_of_the_world() -> None:
    """変換と知覚に出さない一覧には、game_world に今ある、子を持たないドメインイベントの種類だけが入っている。"""
    classified = StimulusTranslator.translated_kinds() | NOT_PERCEIVED_EVENT_KINDS

    assert _names(classified - _game_world_event_kinds()) == []
