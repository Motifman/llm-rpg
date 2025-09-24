import re
from dataclasses import dataclass, field
from typing import List
from src.domain.sns.sns_enum import PostVisibility


@dataclass(frozen=True)
class PostContent:
    content: str = ""
    hashtags: List[str] = field(default_factory=list)
    visibility: PostVisibility = PostVisibility.PUBLIC

    def __post_init__(self):
        if len(self.content) > 280:
            raise ValueError("content must be less than 280 characters")
        if len(self.hashtags) > 10:
            raise ValueError("hashtags must be less than 10")
        if self.visibility not in PostVisibility:
            raise ValueError("invalid visibility")