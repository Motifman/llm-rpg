import random
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate


@dataclass(frozen=True)
class CombatResult:
    """戦闘計算結果"""
    is_evaded: bool
    damage: int


class MonsterCombatService:
    """
    モンスターに関連する戦闘計算を行うドメインサービス。
    将来的に属性耐性やバフ・デバフを考慮した複雑な計算をここに集約する。
    """

    @staticmethod
    def calculate_damage(monster: "MonsterAggregate", raw_damage: int) -> CombatResult:
        """
        モンスターへのダメージを計算する。
        """
        # 回避判定
        # TODO: バフ/デバフによる回避率補正をここに追加予定
        if random.random() < monster.template.base_stats.evasion_rate:
            return CombatResult(is_evaded=True, damage=0)

        # ダメージ計算（最低1ダメージ保証）
        # TODO: 属性耐性や防御力バフをここに追加予定
        defense = monster.template.base_stats.defense
        actual_damage = max(1, raw_damage - defense)

        return CombatResult(is_evaded=False, damage=actual_damage)
