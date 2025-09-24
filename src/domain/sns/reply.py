from typing import Set
from src.domain.sns.post import Post
from src.domain.sns.post_content import PostContent
from src.domain.sns.like import Like
from src.domain.sns.mention import Mention


class Reply(Post):
    def __init__(self, post_id: int, author_user_id: int, post_content: PostContent, likes: Set[Like], mentions: Set[Mention], parent_post_id: int):
        super().__init__(post_id, author_user_id, post_content, likes, mentions)
        self._parent_post_id = parent_post_id
    
    @property
    def parent_post_id(self) -> int:
        return self._parent_post_id
    
    def add_reply(self, reply: "Reply"):
        self._replies.append(reply)
