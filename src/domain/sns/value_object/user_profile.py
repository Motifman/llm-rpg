from dataclasses import dataclass
from src.domain.sns.exception import (
    UserNameValidationException,
    DisplayNameValidationException,
    BioValidationException,
)


@dataclass(frozen=True)
class UserProfile:
    user_name: str
    display_name: str
    bio: str

    def __post_init__(self):
        """プロフィール情報のバリデーション"""
        if not 3 <= len(self.user_name) <= 20:
            raise UserNameValidationException(self.user_name)

        if not 1 <= len(self.display_name) <= 30:
            raise DisplayNameValidationException(self.display_name)

        if len(self.bio) > 200:
            raise BioValidationException(self.bio)

    def update_bio(self, new_bio: str) -> "UserProfile":
        """Bioを更新した新しいインスタンスを返す"""
        return UserProfile(self.user_name, self.display_name, new_bio)

    def update_display_name(self, new_display_name: str) -> "UserProfile":
        """表示名を更新した新しいインスタンスを返す"""
        return UserProfile(self.user_name, new_display_name, self.bio)