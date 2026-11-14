"""game_world の集約と帳簿のすべてに、memento と JSON の変換が登録されていることを見張る (#2091)。"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import get_type_hints

from ai_rpg_world.game_world import domain
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS

_ADDED_LATER = frozenset(
    {
        "Weather",
        "WorldEnding",
        "WorldStage",
        "LatestActions",
        "MissedNotices",
        "ScenarioProgress",
    }
)


def _aggregates_with_memento() -> dict[str, type]:
    found: dict[str, type] = {}
    for module_info in pkgutil.walk_packages(domain.__path__, domain.__name__ + "."):
        module = importlib.import_module(module_info.name)
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and hasattr(cls, "memento") and hasattr(cls, "from_memento"):
                found[name] = cls
    return found


def _memento_type(aggregate: type) -> type:
    memento_type: type = get_type_hints(getattr(aggregate, "memento"))["return"]
    return memento_type


def test_registered_aggregates_are_found() -> None:
    """集約を探す処理が、変換を登録済みの WorldClock と WorldFlags を見つける (探し方が壊れて空振りしないため)。"""
    assert {"WorldClock", "WorldFlags"} <= _aggregates_with_memento().keys()


def test_every_aggregate_has_a_codec_or_is_listed_as_added_later() -> None:
    """変換を登録していない集約が「あとで足す」一覧にも無いとき、その名前を挙げて落ちる。"""
    registered = GAME_WORLD_CODECS.memento_types()

    missing = sorted(
        name
        for name, aggregate in _aggregates_with_memento().items()
        if _memento_type(aggregate) not in registered and name not in _ADDED_LATER
    )

    assert missing == []


def test_added_later_lists_only_aggregates_without_a_codec() -> None:
    """「あとで足す」一覧に、変換を登録済みの集約や、もう無い集約の名前が残っていると落ちる。"""
    registered = GAME_WORLD_CODECS.memento_types()
    aggregates = _aggregates_with_memento()

    stale = sorted(
        name for name in _ADDED_LATER if name not in aggregates or _memento_type(aggregates[name]) in registered
    )

    assert stale == []
