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

    def set_current_tick(self, tick: int) -> None:
        """world tick を直接セットする (= snapshot restore 専用)。

        Phase 9-2 (Issue #470): world snapshot からの復元時に「tick=30 から
        続行」を実現するため、保存された tick を直接書き込む経路。通常の
        simulation flow では使わない (= ``advance_tick`` のみ使う)。

        負の値は ``ValueError``。tick の単調増加性は呼出側 (= restore service)
        が保証する。
        """
        if not isinstance(tick, int) or isinstance(tick, bool):
            raise TypeError(f"tick must be int, got {type(tick).__name__}")
        if tick < 0:
            raise ValueError(f"tick must be non-negative: {tick}")
        self._current_tick = WorldTick(tick)
