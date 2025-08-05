from dataclasses import dataclass, field
from typing import List


@dataclass
class PlayerContribution:
    """プレイヤーの戦闘貢献度"""
    player_id: str
    total_damage_dealt: int = 0  # 与えたダメージ
    total_damage_taken: int = 0  # 受けたダメージ
    turns_participated: int = 0  # 参加ターン数
    critical_hits: int = 0  # クリティカルヒット数
    successful_attacks: int = 0  # 成功した攻撃数
    successful_defenses: int = 0  # 成功した防御数
    status_effects_applied: int = 0  # 適用した状態異常数
    counter_attacks: int = 0  # 反撃回数
    healing_done: int = 0  # 回復量
    support_actions: int = 0  # サポート行動数
    
    def calculate_contribution_score(self) -> float:
        """貢献度スコアを計算"""
        # 基本スコア: 与えたダメージ
        base_score = self.total_damage_dealt * 1.0
        
        # ボーナス: クリティカルヒット
        critical_bonus = self.critical_hits * 10
        
        # ボーナス: 反撃
        counter_bonus = self.counter_attacks * 15
        
        # ボーナス: 状態異常適用
        status_bonus = self.status_effects_applied * 20
        
        # ボーナス: 回復・サポート
        support_bonus = (self.healing_done * 0.5) + (self.support_actions * 10)
        
        # ペナルティ: 受けたダメージ（生存している限り軽微）
        damage_penalty = self.total_damage_taken * 0.1
        
        # 参加期間ボーナス
        participation_bonus = self.turns_participated * 5
        
        total_score = base_score + critical_bonus + counter_bonus + status_bonus + support_bonus - damage_penalty + participation_bonus
        
        # 最低スコアを保証
        return max(1.0, total_score)


@dataclass
class DistributedReward:
    """分配された報酬"""
    player_id: str
    money: int = 0
    experience: int = 0
    items: List = field(default_factory=list)
    information: List[str] = field(default_factory=list)
    contribution_score: float = 0.0
    contribution_percentage: float = 0.0 