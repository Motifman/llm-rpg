"""食料劣化tick command用repository束。"""

from typing import Protocol

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository


class FoodSpoilageCommandRepositoryProviderPort(Protocol):
    """食料劣化stageへ、同じ確定境界のitem repositoryだけを公開する。"""

    @property
    def items(self) -> ItemRepository: ...


__all__ = ["FoodSpoilageCommandRepositoryProviderPort"]
