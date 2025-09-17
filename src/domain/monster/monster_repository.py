from abc import abstractmethod
from typing import List
from src.domain.common.repository import Repository
from src.domain.monster.monster import Monster


class MonsterRepository(Repository[Monster]):
    @abstractmethod
    def find_by_spot_id(self, spot_id: int) -> List[Monster]:
        pass