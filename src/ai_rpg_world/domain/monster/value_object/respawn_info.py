from dataclasses import dataclass
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRespawnValidationException


@dataclass(frozen=True)
class RespawnInfo:
    """モンスターのリスポーン設定"""
    respawn_interval_ticks: int
    is_auto_respawn: bool = True

    def __post_init__(self):
        if self.respawn_interval_ticks < 0:
            raise MonsterRespawnValidationException(
                f"Respawn interval cannot be negative: {self.respawn_interval_ticks}"
            )
