from src.domain.sns.value_object import UserProfile, UserId


class SnsUser:
    def __init__(
        self,
        user_id: UserId,
        user_profile: UserProfile,
    ):
        self._user_id = user_id
        self._user_profile = user_profile

    @property
    def user_id(self) -> UserId:
        return self._user_id

    @property
    def user_profile(self) -> UserProfile:
        return self._user_profile

    def update_user_profile(self, user_profile: UserProfile):
        self._user_profile = user_profile