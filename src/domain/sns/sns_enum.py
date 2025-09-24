from enum import Enum


class PostVisibility(Enum):
    PUBLIC = "public"
    FOLLOWERS_ONLY = "followers_only"
    SPECIFIED_USERS = "specified_users"
    PRIVATE = "private"