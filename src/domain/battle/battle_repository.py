from abc import abstractmethod
from typing import Optional
from src.domain.battle.battle import Battle
from src.domain.common.repository import Repository


class BattleRepository(Repository[Battle]):
    @abstractmethod
    def find_by_spot_id(self, spot_id: int) -> Optional[Battle]:
        pass

    @abstractmethod
    def generate_battle_id(self) -> int:
        """戦闘IDを生成"""
        pass