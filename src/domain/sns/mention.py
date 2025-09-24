from dataclasses import dataclass


@dataclass(frozen=True)
class Mention:
    mentioned_user_name: str
    post_id: int

    def __post_init__(self):
        if self.post_id <= 0:
            raise ValueError("post_id must be positive")
        if self.mentioned_user_name is None:
            raise ValueError("mentioned_user_name must be positive")