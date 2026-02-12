from dataclasses import dataclass
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.common.value_object import WorldTick


@dataclass(frozen=True)
class StatusEffect:
    """ステータス効果（バフ・デバフ）を表す値オブジェクト"""
    effect_type: StatusEffectType
    value: float  # 効果量（1.1なら10%上昇、0.9なら10%減少など）
    expiry_tick: WorldTick  # 有効期限のティック

    def is_expired(self, current_tick: WorldTick) -> bool:
        """期限切れかどうか判定"""
        return current_tick.value >= self.expiry_tick.value
