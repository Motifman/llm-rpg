from dataclasses import dataclass


@dataclass(frozen=True)
class ActionMastery:
    """技の習熟度を表現する値オブジェクト"""
    action_id: int
    experience: int = 0
    level: int = 1
    
    def __post_init__(self):
        if self.action_id <= 0:
            raise ValueError(f"action_id must be positive. action_id: {self.action_id}")
        if self.experience < 0:
            raise ValueError(f"experience must be non-negative. experience: {self.experience}")
        if self.level <= 0:
            raise ValueError(f"level must be positive. level: {self.level}")
    
    def gain_experience(self, exp: int) -> "ActionMastery":
        """経験値を獲得した新しいActionMasteryを返す"""
        if exp < 0:
            raise ValueError(f"exp must be non-negative. exp: {exp}")
        
        new_experience = self.experience + exp
        return ActionMastery(self.action_id, new_experience, self.level)
    
    def level_up(self) -> "ActionMastery":
        """レベルアップした新しいActionMasteryを返す"""
        return ActionMastery(self.action_id, self.experience, self.level + 1)
    
    def can_evolve(self, required_experience: int, required_level: int) -> bool:
        """進化可能かどうかを判定"""
        if required_experience < 0:
            raise ValueError(f"required_experience must be non-negative. required_experience: {required_experience}")
        if required_level <= 0:
            raise ValueError(f"required_level must be positive. required_level: {required_level}")
        
        return self.experience >= required_experience and self.level >= required_level
    
    def reset_for_evolution(self) -> "ActionMastery":
        """進化時の習熟度リセット（新しいaction_idで新しいインスタンスを作る前提）"""
        return ActionMastery(self.action_id, 0, 1)
