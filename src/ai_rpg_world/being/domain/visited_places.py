"""Being が訪れた場所の記録。初めて着いた場所を本人が見分けるために持つ (#2267)。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.exception.being_exceptions import VisitedPlacesValidationException


@dataclass(frozen=True)
class VisitedPlace:
    """場所の名前は環境の中でだけ通じるので、環境の名前と組にする。"""

    environment_name: str
    place: str

    def __post_init__(self) -> None:
        for field_name in ("environment_name", "place"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise VisitedPlacesValidationException(f"{field_name} must be non-blank str")


class VisitedPlaces:
    """Being ごとに 1 つ。"""

    def __init__(self, being_id: BeingId, places: tuple[VisitedPlace, ...] = ()) -> None:
        if not isinstance(being_id, BeingId):
            raise VisitedPlacesValidationException("being_id must be BeingId")
        if not all(isinstance(p, VisitedPlace) for p in places) or len(set(places)) != len(places):
            raise VisitedPlacesValidationException("places must be distinct VisitedPlace items")
        self._being_id = being_id
        self._places = tuple(places)

    @classmethod
    def empty(cls, being_id: BeingId) -> VisitedPlaces:
        return cls(being_id)

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def places(self) -> tuple[VisitedPlace, ...]:
        """訪れた順。"""
        return self._places

    def visit(self, *, environment_name: str, place: str) -> None:
        visited = VisitedPlace(environment_name=environment_name, place=place)
        if visited not in self._places:
            self._places = (*self._places, visited)

    def has_visited(self, *, environment_name: str, place: str) -> bool:
        return VisitedPlace(environment_name=environment_name, place=place) in self._places


class VisitedPlacesRepository(ABC):
    @abstractmethod
    def get(self, being_id: BeingId) -> VisitedPlaces:
        """まだどこも訪れていない Being には空の記録を返す。返した集約を書き換えても、``save`` するまで保存先は変わらない。"""

    @abstractmethod
    def save(self, places: VisitedPlaces) -> None: ...

    @abstractmethod
    def replace_all_by_being(self, places: VisitedPlaces) -> None:
        """snapshot から戻すときに使う。"""


__all__ = ["VisitedPlace", "VisitedPlaces", "VisitedPlacesRepository"]
