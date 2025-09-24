import re
from dataclasses import dataclass, field
from typing import List, Tuple
from src.domain.sns.sns_enum import PostVisibility


@dataclass(frozen=True)
class PostContent:
    content: str = ""
    hashtags: Tuple[str, ...] = field(default_factory=tuple)
    visibility: PostVisibility = PostVisibility.PUBLIC

    def __post_init__(self):
        if len(self.content) > 280:
            raise ValueError("content must be less than 280 characters")
        if len(self.hashtags) > 10:
            raise ValueError("hashtags must be less than 10")
        if not isinstance(self.visibility, PostVisibility):
            raise ValueError("invalid visibility")