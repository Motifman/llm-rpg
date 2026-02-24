"""
実効ステータス計算のドメインサービス（状態を持たない純粋関数）。

集約からは呼び出さず、アプリケーション層が集約の base_stats / active_effects を取得して
本関数に渡し、得た BaseStats を利用する。
"""
from typing import List

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType


def compute_effective_stats(
    base_stats: BaseStats,
    active_effects: List[StatusEffect],
    current_tick: WorldTick,
) -> BaseStats:
    """
    期限切れでないステータス効果を適用した実効 BaseStats を返す。
    副作用はなく、集約の active_effects は変更しない。

    Args:
        base_stats: ベースとなるステータス（成長倍率等は呼び出し元で反映済みを想定）
        active_effects: 適用する効果一覧（期限切れは計算時に除外する）
        current_tick: 現在ティック（期限切れ判定に使用）

    Returns:
        効果適用後の BaseStats
    """
    atk_mult = 1.0
    def_mult = 1.0
    spd_mult = 1.0

    for effect in active_effects:
        if effect.is_expired(current_tick):
            continue
        if effect.effect_type == StatusEffectType.ATTACK_UP:
            atk_mult *= effect.value
        elif effect.effect_type == StatusEffectType.ATTACK_DOWN:
            atk_mult *= effect.value
        elif effect.effect_type == StatusEffectType.DEFENSE_UP:
            def_mult *= effect.value
        elif effect.effect_type == StatusEffectType.DEFENSE_DOWN:
            def_mult *= effect.value
        elif effect.effect_type == StatusEffectType.SPEED_UP:
            spd_mult *= effect.value
        elif effect.effect_type == StatusEffectType.SPEED_DOWN:
            spd_mult *= effect.value

    return BaseStats(
        max_hp=base_stats.max_hp,
        max_mp=base_stats.max_mp,
        attack=int(base_stats.attack * atk_mult),
        defense=int(base_stats.defense * def_mult),
        speed=int(base_stats.speed * spd_mult),
        critical_rate=base_stats.critical_rate,
        evasion_rate=base_stats.evasion_rate,
    )
