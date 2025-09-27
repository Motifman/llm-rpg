import re
from dataclasses import dataclass, field
from typing import List, Tuple
from src.domain.sns.enum import PostVisibility
from src.domain.sns.exception import ContentLengthValidationException, HashtagCountValidationException, VisibilityValidationException


@dataclass(frozen=True)
class PostContent:
    content: str = ""
    hashtags: Tuple[str, ...] = field(default_factory=tuple)
    visibility: PostVisibility = PostVisibility.PUBLIC

    def __post_init__(self):
        if len(self.content) > 280:
            raise ContentLengthValidationException(self.content, 280)
        if len(self.hashtags) > 10:
            raise HashtagCountValidationException(len(self.hashtags), 10)
        if not isinstance(self.visibility, PostVisibility):
            raise VisibilityValidationException(str(self.visibility))