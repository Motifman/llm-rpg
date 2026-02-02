from abc import ABC, abstractmethod
from ai_rpg_world.domain.common.value_object import WorldTick

class GameTimeProvider(ABC):
    """現在のゲーム内時間を取得・管理するためのインターフェース（ポート）"""
    
    @abstractmethod
    def get_current_tick(self) -> WorldTick:
        """現在のティックを取得する"""
        pass
    
    @abstractmethod
    def advance_tick(self, amount: int = 1) -> WorldTick:
        """ティックを進め、新しいティックを返す"""
        pass
