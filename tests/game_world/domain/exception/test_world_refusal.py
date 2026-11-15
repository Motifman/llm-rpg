from __future__ import annotations

import importlib
import inspect
import pkgutil

import ai_rpg_world.game_world.domain.exception as exception_package
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException, WorldRefusal

_WORLD_REFUSALS = frozenset(
    {
        "GroundItemNotFoundException",
        "ItemAlreadyLeftWorldException",
        "ItemNotCarriedException",
        "InventoryFullException",
        "NotEnoughStockException",
        "NotEnoughItemsOfSpecException",
        "NotEnoughCountException",
        "PackIsEmptyException",
        "ItemAlreadyHeldException",
        "ItemNotHeldException",
        "ItemNotPackedException",
        "InsufficientGoldException",
        "PersonNotAliveException",
        "PersonNotDownException",
        "OutcomeAlreadyDecidedException",
        "AlreadyInGroupException",
        "AlreadyInAnotherGroupOfGroupingException",
        "NotInGroupException",
        "SectionFullException",
        "OccupantAlreadyInSectionException",
        "OccupantNotInSectionException",
        "OccupantNotAtSectionSpotException",
        "NoRouteToDestinationException",
        "PassageAlreadyRemovedException",
        "OccupantNotAtRouteStartException",
        "WorldAlreadyEndedException",
        "GroupDecisionNotOpenException",
        "GroupDecisionAlreadyOpenException",
        "NoVotersGivenException",
        "NoChoicesGivenException",
        "VoterNotInDecisionException",
        "ChoiceNotInDecisionException",
        "BallotAlreadyCastException",
        "AbstainNotAllowedException",
    }
)


def _domain_exceptions() -> dict[str, type[GameWorldDomainException]]:
    found: dict[str, type[GameWorldDomainException]] = {}
    for module_info in pkgutil.iter_modules(exception_package.__path__):
        module = importlib.import_module(f"{exception_package.__name__}.{module_info.name}")
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, GameWorldDomainException) and cls.__module__ == module.__name__:
                found[name] = cls
    return found


class TestWorldRefusalMark:
    """世界が断った例外にだけ WorldRefusal の印が付いていることを、表に対して保証する。"""

    def test_exactly_the_listed_exceptions_are_world_refusals(self) -> None:
        """WorldRefusal を継承するドメイン例外は、表に載せたものとちょうど一致する。印の付け忘れも付けすぎも落ちる。"""
        marked = {
            name
            for name, cls in _domain_exceptions().items()
            if issubclass(cls, WorldRefusal) and cls is not WorldRefusal
        }

        assert marked == _WORLD_REFUSALS
