from abc import abstractmethod
from typing import Optional
from src.domain.battle.battle import Battle
from src.domain.common.repository import Repository


class BattleRepository(Repository[Battle]):
    @abstractmethod
    def find_by_spot_id(self, spot_id: int) -> Optional[Battle]:
        pass