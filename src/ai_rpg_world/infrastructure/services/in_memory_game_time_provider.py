from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.domain.common.value_object import WorldTick

class InMemoryGameTimeProvider(GameTimeProvider):
    """メモリ内でティックを管理するGameTimeProviderの実装"""
    
    def __init__(self, initial_tick: int = 0):
        self._current_tick = WorldTick(initial_tick)
    
    def get_current_tick(self) -> WorldTick:
        return self._current_tick
    
    def advance_tick(self, amount: int = 1) -> WorldTick:
        if amount < 0:
            raise ValueError(f"Amount to advance must be positive: {amount}")
        self._current_tick = self._current_tick.add_duration(amount)
        return self._current_tick
