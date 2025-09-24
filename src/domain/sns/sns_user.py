from src.domain.sns.user_profile import UserProfile


class SnsUser:
    def __init__(
        self,
        user_id: int,
        user_profile: UserProfile,
    ):
        if user_id <= 0:
            raise ValueError("user_id must be positive")

        self._user_id = user_id
        self._user_profile = user_profile
    
    @property
    def user_id(self) -> int:
        return self._user_id
    
    @property
    def user_profile(self) -> UserProfile:
        return self._user_profile

    def update_user_profile(self, user_profile: UserProfile):
        self._user_profile = user_profile