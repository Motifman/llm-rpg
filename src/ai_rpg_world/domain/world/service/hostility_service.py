from abc import ABC, abstractmethod
from typing import Dict, Set


class HostilityService(ABC):
    """
    アクター間の敵対関係を判定するサービスのインターフェース。
    具体的な敵対テーブルなどは実装クラスまたは外部設定から供給されることを想定。
    """

    @abstractmethod
    def is_hostile(self, actor_comp, target_comp) -> bool:
        """
        actor_comp が target_comp に対して敵対的かどうかを判定する。
        """
        pass


class ConfigurableHostilityService(HostilityService):
    """
    設定可能な敵対関係テーブルを持つ実装。
    種族(race)や勢力(faction)に基づいた判定を行う。
    """

    def __init__(
        self, 
        race_hostility_table: Dict[str, Set[str]] = None,
        faction_hostility_table: Dict[str, Set[str]] = None
    ):
        # キー: 種族, 値: その種族が敵対する種族のセット
        self._race_hostility = race_hostility_table or {}
        # キー: 勢力, 値: その勢力が敵対する勢力のセット
        self._faction_hostility = faction_hostility_table or {}

    def is_hostile(self, actor_comp, target_comp) -> bool:
        # 1. 勢力による判定 (優先)
        if actor_comp.faction in self._faction_hostility:
            if target_comp.faction in self._faction_hostility[actor_comp.faction]:
                return True
        
        # 2. 種族による判定
        if actor_comp.race in self._race_hostility:
            if target_comp.race in self._race_hostility[actor_comp.race]:
                return True
                
        return False
