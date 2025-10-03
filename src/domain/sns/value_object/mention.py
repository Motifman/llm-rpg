from dataclasses import dataclass
from src.domain.sns.value_object.post_id import PostId
from src.domain.sns.exception import MentionValidationException


@dataclass(frozen=True)
class Mention:
    mentioned_user_name: str
    post_id: PostId

    def __post_init__(self):
        if self.mentioned_user_name == "":
            raise MentionValidationException("")