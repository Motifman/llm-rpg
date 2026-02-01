from typing import Optional
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException


class Spot:
    """意味的な場所（宿屋、村の広場等）"""
    def __init__(
        self,
        spot_id: SpotId,
        name: str,
        description: str,
        category: SpotCategoryEnum = SpotCategoryEnum.OTHER,
        parent_id: Optional[SpotId] = None
    ):
        if not name:
            raise SpotNameEmptyException("Spot name cannot be empty")
            
        self._spot_id = spot_id
        self._name = name
        self._description = description
        self._category = category
        self._parent_id = parent_id

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    @property
    def parent_id(self) -> Optional[SpotId]:
        return self._parent_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description
    
    @property
    def category(self) -> SpotCategoryEnum:
        return self._category
    
    def update_info(self, name: str = None, description: str = None, category: SpotCategoryEnum = None):
        if name is not None:
            if not name:
                raise SpotNameEmptyException("Spot name cannot be empty")
            self._name = name
        if description is not None:
            self._description = description
        if category is not None:
            self._category = category
