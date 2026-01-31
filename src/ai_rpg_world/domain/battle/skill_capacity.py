from dataclasses import dataclass


@dataclass(frozen=True)
class SkillCapacity:
    """技習得のキャパシティを表現する値オブジェクト"""
    max_capacity: int
    
    def __post_init__(self):
        if self.max_capacity < 0:
            raise ValueError(f"max_capacity must be non-negative. max_capacity: {self.max_capacity}")
    
    def can_accommodate(self, required_capacity: int, current_usage: int) -> bool:
        """指定されたキャパシティを収容できるかどうか"""
        if required_capacity < 0:
            raise ValueError(f"required_capacity must be non-negative. required_capacity: {required_capacity}")
        if current_usage < 0:
            raise ValueError(f"current_usage must be non-negative. current_usage: {current_usage}")
        
        return current_usage + required_capacity <= self.max_capacity
    
    def calculate_remaining(self, current_usage: int) -> int:
        """残りキャパシティを計算"""
        if current_usage < 0:
            raise ValueError(f"current_usage must be non-negative. current_usage: {current_usage}")
        
        remaining = self.max_capacity - current_usage
        return max(0, remaining)
    
    def is_full(self, current_usage: int) -> bool:
        """キャパシティが満杯かどうか"""
        return current_usage >= self.max_capacity
