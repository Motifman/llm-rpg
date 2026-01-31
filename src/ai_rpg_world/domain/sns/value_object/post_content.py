import re
from dataclasses import dataclass, field
from typing import List, Tuple
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.exception import ContentLengthValidationException, HashtagCountValidationException, VisibilityValidationException


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

    @classmethod
    def create(cls, content: str, visibility: PostVisibility = PostVisibility.PUBLIC) -> "PostContent":
        """コンテンツと可視性からPostContentを作成（ハッシュタグは自動抽出）"""
        hashtags = cls._extract_hashtags(content)
        return cls(content=content, hashtags=hashtags, visibility=visibility)

    @staticmethod
    def _extract_hashtags(content: str) -> Tuple[str, ...]:
        """コンテンツからハッシュタグを抽出"""
        hashtag_pattern = r'#(\w+)'
        matches = re.findall(hashtag_pattern, content)
        return tuple(matches)