from dataclasses import dataclass

@dataclass(frozen=True)
class StartHarvestCommand:
    """採集開始コマンド"""
    actor_id: str
    target_id: str
    spot_id: str
    current_tick: int

@dataclass(frozen=True)
class FinishHarvestCommand:
    """採集完了コマンド"""
    actor_id: str
    target_id: str
    spot_id: str
    current_tick: int
