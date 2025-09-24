from dataclasses import dataclass


@dataclass(frozen=True)
class UserProfile:
    user_name: str
    display_name: str 
    bio: str

    def __post_init__(self):
        if not 3 <= len(self.user_name) <= 20:
            raise ValueError("ユーザー名は3-20文字である必要があります")

        if not 1 <= len(self.display_name) <= 30:
            raise ValueError("表示名は1-30文字である必要があります")

        if len(self.bio) > 200:
            raise ValueError("Bioは200文字以内である必要があります")
            
    def update_bio(self, new_bio: str) -> "UserProfile":
        return UserProfile(self.user_name, self.display_name, new_bio)

    def update_display_name(self, new_display_name: str) -> "UserProfile":
        return UserProfile(self.user_name, new_display_name, self.bio)