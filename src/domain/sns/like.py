from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Like:
    user_id: int
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")

    def __hash__(self):
        return hash(self.user_id)